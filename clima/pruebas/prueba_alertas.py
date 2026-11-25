# SOS Galápagos · © 2026 Universidad San Francisco de Quito (USFQ) · Autor: Julián Maya <jamaya@usfq.edu.ec>
# Licencia Apache 2.0 (ver LICENSE y NOTICE): puede reutilizarse dando crédito.
"""Pruebas del mar, los boletines oficiales y las alertas por tema. Sin red: todo se simula."""
import json
from datetime import datetime, timedelta, timezone

import pytest

from clima import alertas, mar, oficiales
from clima.models import AvisoEnviado, Boletin, Corrida, MareaExtremo, MarHora, PronosticoEmitido, PronosticoOficial
from reportes.models import SuscripcionPush

pytestmark = pytest.mark.django_db
AHORA = datetime.now(timezone.utc)

TABLA = """<table><tr><td colspan=2>22/11/2026<br>Domingo</td></tr><tr><th>Hora (hh:mm)</th><th>Altura (metros)</th></tr>
<tr><td>00:23</td><td>1.83 P</td></tr><tr><td>06:47</td><td>0.38 B</td></tr><tr><td>ND</td><td>ND</td></tr>
<tr><td colspan=2>23/11/2026Lunes</td></tr><tr><td>01:09</td><td>1.94 P</td></tr></table>"""


@pytest.fixture
def enviados(monkeypatch, settings):
    """Captura lo que se mandaría a cada teléfono."""
    from reportes import avisos

    settings.PUSH_PUBLICA = settings.PUSH_PRIVADA = "x"
    lista = []
    monkeypatch.setattr(avisos, "_entregar", lambda s, carga: lista.append((s.direccion, json.loads(carga))) or True)
    # Estas pruebas corren a cualquier hora: salvo que una pida la noche, es de día.
    monkeypatch.setattr(alertas, "es_de_noche", lambda ahora: False)
    return lista


def suscribir(nombre, temas=None, zonas=None):
    return SuscripcionPush.objects.create(direccion=f"https://push.test/{nombre}", p256dh="k", auth="a", temas=temas or [], zonas=zonas or [])


# ── Mar ──────────────────────────────────────────────────────────────────────
def prueba_lee_la_tabla_oficial_de_mareas_en_hora_de_galapagos():
    extremos = mar.leer_tabla_inocar(TABLA)
    assert [(e[1], e[2]) for e in extremos] == [("P", 1.83), ("B", 0.38), ("P", 1.94)]
    assert extremos[0][0] == datetime(2026, 11, 22, 6, 23, tzinfo=timezone.utc)  # 00:23 de Galápagos
    assert mar.guardar_mareas("san-cristobal", extremos, "inocar", "MLWS") == 3
    mar.guardar_mareas("san-cristobal", extremos, "inocar", "MLWS")  # repetir no duplica
    assert MareaExtremo.objects.count() == 3


def prueba_stormglass_respeta_el_cupo_y_cambia_de_llave(settings, monkeypatch):
    settings.CLIMA_STORMGLASS_API, settings.CLIMA_STORMGLASS_LLAVES = "https://api.test/v2", "llave-a, llave-b"
    usadas = []

    def falso(url, cabeceras=None, espera=30):
        usadas.append(cabeceras["Authorization"])
        if "tide" in url:
            return json.dumps({"data": [{"time": (AHORA + timedelta(hours=3)).isoformat(), "type": "high", "height": 0.8}], "meta": {"datum": "MSL"}}).encode()
        return json.dumps({"hours": [{"time": (AHORA + timedelta(hours=1)).replace(minute=0, second=0, microsecond=0).isoformat(), "waveHeight": {"sg": 2.8}, "swellPeriod": {"sg": 14}}]}).encode()

    monkeypatch.setattr(mar, "_bajar", falso)
    assert mar.actualizar_stormglass_mareas(("san-cristobal",)) == 1 and mar.actualizar_stormglass_mar(("san-cristobal",)) == 1
    assert MareaExtremo.objects.get().datum == "MSL" and MarHora.objects.get().ola_m == 2.8
    assert usadas == ["llave-a", "llave-a"] and Corrida.objects.filter(fuente="stormglass_1").count() == 2
    for _ in range(mar.CUPO_DIARIO):  # la primera llave agota su día
        Corrida.objects.create(fuente="stormglass_1", ts=datetime.now(timezone.utc), ok=True)
    mar.actualizar_stormglass_mareas(("isabela",))
    assert usadas[-1] == "llave-b"
    for _ in range(mar.CUPO_DIARIO):
        Corrida.objects.create(fuente="stormglass_2", ts=datetime.now(timezone.utc), ok=True)
    antes = len(usadas)
    assert mar.actualizar_stormglass_mareas(("isabela",)) == 0 and len(usadas) == antes  # sin cupo no se llama


def prueba_el_resumen_del_mar_prefiere_la_tabla_oficial(client):
    mar.guardar_mareas("san-cristobal", [(AHORA + timedelta(hours=2), "P", 1.9)], "inocar", "MLWS")
    mar.guardar_mareas("san-cristobal", [(AHORA + timedelta(hours=2), "P", 0.8)], "stormglass", "MSL")
    mar.guardar_mareas("isabela", [(AHORA + timedelta(hours=2), "P", 0.7)], "stormglass", "MSL")
    puertos = {p["puerto"]: p for p in client.get("/riesgos/api/clima/mar").json()["puertos"]}
    assert puertos["san-cristobal"]["mareas"]["referencia"] == "MLWS" and puertos["san-cristobal"]["mareas"]["extremos"][0]["altura_m"] == 1.9
    assert "Stormglass" in puertos["isabela"]["mareas"]["fuente"]


# ── Oficiales ────────────────────────────────────────────────────────────────
def prueba_guarda_el_pronostico_del_inamhi_de_las_tres_islas(settings, monkeypatch):
    settings.CLIMA_INAMHI_PRONOSTICO_URL, settings.CLIMA_INAMHI_LLUVIA_HORAS_URL = "https://a.test/p", "https://a.test/h"
    dia = {"items": [{"locality_name": "Santa Cruz", "date": "2026-11-22", "min_temperature": "26.0", "max_temperature": "31.0", "periods": [{"period_name": "Noche", "condition_name": "Tormenta"}]},
                     {"locality_name": "Quito", "date": "2026-11-22", "min_temperature": "10", "max_temperature": "20", "periods": []}]}
    horas = {"ciudades": {"Santa Cruz|-0.639_-90.337": {"ok": True, "horas": [{"h": 1, "mm": 3.2}]}}}
    monkeypatch.setattr(oficiales, "_bajar", lambda url, **k: json.dumps(horas if url.endswith("/h") else dia).encode())
    assert oficiales.actualizar_pronostico_inamhi() == 1
    p = PronosticoOficial.objects.get()
    assert p.isla == "santa-cruz" and p.maxima_c == 31.0 and p.periodos[0]["condicion"] == "Tormenta" and p.lluvia_horas == [{"h": 1, "mm": 3.2}]


def prueba_un_boletin_nuevo_se_lee_con_el_modelo_y_no_se_repite(settings):
    from pydantic_ai.models.test import TestModel

    settings.IA_MODELO = TestModel(custom_output_args={"numero": "89", "titulo": "Advertencia meteorológica", "vigente_hasta": "2026-11-24T10:00:00-05:00",
                                                       "afecta_galapagos": True, "nivel_galapagos": "muy alto", "resumen": "Lluvias y tormentas de nivel muy alto en Galápagos hasta el 24 de noviembre."})
    b = oficiales.registrar("inamhi", "advertencia", b"%PDF-contenido", "application/pdf", "https://inamhi.test/advertencia.pdf", "advertencia")
    assert b.numero == "89" and b.afecta_galapagos and b.nivel == "muy alto" and b.vigente_hasta.astimezone(timezone.utc).hour == 15 and b.extraido_con
    assert oficiales.registrar("inamhi", "advertencia", b"%PDF-contenido", "application/pdf", "https://inamhi.test/advertencia.pdf", "advertencia") is None
    assert Boletin.objects.count() == 1


def prueba_sin_modelo_el_boletin_se_guarda_sin_inventar(settings):
    settings.IA_MODELO = ""
    b = oficiales.registrar("inocar", "oleaje", b"imagen", "image/png", "https://inocar.test/b.png", "oleaje", "Condiciones de oleaje del 20 al 23")
    assert b.titulo.startswith("Condiciones") and not b.afecta_galapagos and b.resumen == "" and not b.extraido_con


# ── Alertas por tema ─────────────────────────────────────────────────────────
def prueba_cada_quien_recibe_solo_sus_temas_y_sus_islas(enviados):
    suscribir("todo")                                                   # sin elegir: los de siempre, todas las islas
    suscribir("mar-isabela", temas=["mar"], zonas=["isabela"])
    suscribir("lluvia-sc", temas=["lluvia"], zonas=["santa-cruz"])
    a = alertas.emitir("lluvia", "santa-cruz", "lluvia:la-cascada:alto:x", "Lluvia peligrosa", "cuerpo", "/clima/")
    assert a.entregados == 2 and {d for d, _ in enviados} == {"https://push.test/todo", "https://push.test/lluvia-sc"}
    assert alertas.emitir("lluvia", "santa-cruz", "lluvia:la-cascada:alto:x", "Lluvia peligrosa", "cuerpo") is None  # la misma no sale dos veces
    enviados.clear()
    alertas.emitir("mar", "isabela", "mar:isabela:hoy", "Oleaje fuerte", "cuerpo")
    assert [d for d, _ in enviados] == ["https://push.test/mar-isabela"]   # «mar» no es de los temas por defecto
    assert not AvisoEnviado.objects.filter(retenido=True).exists()
    assert AvisoEnviado.objects.count() == 2


def _zonas(monkeypatch, *zonas):
    from reportes import clima as panel

    monkeypatch.setattr(panel, "estado", lambda: {"inundacion": {"zonas": list(zonas)}})


def prueba_la_lluvia_se_avisa_solo_si_esta_lloviendo_ahora(enviados, monkeypatch):
    suscribir("a")
    # Lo de la madrugada del 22-nov: el nivel seguía «muy alto» por lo acumulado, pero ya no llovía. No es motivo de aviso.
    _zonas(monkeypatch, {"id": "la-cascada", "zona": "La Cascada (Puerto Ayora)", "nivel": "muy alto", "nivel_instantaneo": "alto", "R": {"R1h": 0.0, "R3h": 0.0, "R24h": 231}})
    assert alertas.revisar() == [] and enviados == []
    # Llueve ahora en dos zonas de la misma isla: un solo aviso, con la que más llueve, y dice lo medido sin asustar.
    _zonas(monkeypatch, {"id": "santa-cruz-alta", "zona": "Parte alta de Santa Cruz", "nivel": "alto", "nivel_instantaneo": "alto", "R": {"R1h": 12.2, "R3h": 20, "R24h": 60}},
           {"id": "la-cascada", "zona": "La Cascada (Puerto Ayora)", "nivel": "muy alto", "nivel_instantaneo": "muy alto", "R": {"R1h": 31.6, "R3h": 48.2, "R24h": 233.4}},
           {"id": "san-cristobal", "zona": "San Cristóbal", "nivel": "medio", "nivel_instantaneo": "medio", "R": {"R1h": 6}})
    emitidos = alertas.revisar()
    assert len(emitidos) == 1 and emitidos[0].zona == "santa-cruz" and emitidos[0].urgente
    assert emitidos[0].titulo == "Llueve muy fuerte en Santa Cruz" and "32 mm en la última hora y 48 en tres horas" in emitidos[0].cuerpo
    assert "peligros" not in (emitidos[0].titulo + emitidos[0].cuerpo).lower() and "Aléjate" not in emitidos[0].cuerpo and "Evita" not in emitidos[0].cuerpo and "no oficial" in emitidos[0].cuerpo
    assert alertas.revisar() == []  # cinco minutos después no se repite


def prueba_de_noche_no_se_manda_nada_y_a_las_seis_sale_un_resumen(enviados, monkeypatch):
    monkeypatch.undo()   # aquí sí cuenta la hora
    from reportes import avisos

    monkeypatch.setattr(avisos, "_entregar", lambda s, carga: enviados.append((s.direccion, json.loads(carga))) or True)
    suscribir("dormido")
    despierto = suscribir("despierto")
    despierto.de_noche = True
    despierto.save()
    noche = datetime(2026, 11, 23, 8, 19, tzinfo=timezone.utc)      # 02:19 en Galápagos
    assert alertas.es_de_noche(noche) and alertas.es_de_noche(noche.replace(hour=3)) and not alertas.es_de_noche(noche.replace(hour=12)) and not alertas.es_de_noche(noche.replace(hour=2, minute=59))
    # Algo que no es urgente: nadie lo recibe, queda retenido.
    a = alertas.emitir("oficiales", "", "boletin:x", "Advertencia del INAMHI n.º 90", "cuerpo", ahora=noche)
    assert a.retenido and a.entregados == 0 and enviados == []
    # Lo urgente (llueve muy fuerte ahora): solo a quien pidió que lo despierten.
    b = alertas.emitir("lluvia", "santa-cruz", "lluvia:santa-cruz:muy alto:x", "Llueve muy fuerte en Santa Cruz", "cuerpo", urgente=True, ahora=noche)
    assert b.retenido and b.entregados == 1 and [d for d, _ in enviados] == ["https://push.test/despierto"]
    AvisoEnviado.objects.update(creado=noche)
    enviados.clear()
    # A las cinco y pico todavía no; a las seis, un solo resumen para todos, con la hora de cada cosa.
    assert alertas._resumen_de_la_noche(noche.replace(hour=11, minute=55)) == []
    resumen = alertas._resumen_de_la_noche(noche.replace(hour=12, minute=0))
    assert len(resumen) == 1 and resumen[0].titulo == "Esta noche en Galápagos" and resumen[0].entregados == 2
    assert "02:19 Advertencia del INAMHI n.º 90" in resumen[0].cuerpo and "02:19 Llueve muy fuerte" in resumen[0].cuerpo and resumen[0].enlace == "/riesgos/informe/"
    assert alertas._resumen_de_la_noche(noche.replace(hour=12, minute=5)) == [] and len(enviados) == 2   # no se repite
    # Una noche tranquila no manda resumen.
    assert alertas._resumen_de_la_noche(noche.replace(hour=12) + timedelta(days=1)) == []


def prueba_un_peligro_de_vida_confirmado_es_lo_unico_de_reportes_que_suena_de_noche(enviados, monkeypatch):
    from django.contrib.gis.geos import Point

    from reportes import avisos, reglas
    from reportes.models import Fuente, TipoRiesgo

    monkeypatch.setattr(alertas, "es_de_noche", lambda ahora: True)
    d = suscribir("despierto")
    d.de_noche = True
    d.save()
    suscribir("dormido")
    tipo = TipoRiesgo.objects.get(codigo="agua_via")
    leve = reglas.crear_reporte(tipo=tipo, punto=Point(-90.31, -0.74, srid=4326), huella="c1", fuente=Fuente.COORDINADOR, gravedad="no_pasar").reporte
    grave = reglas.crear_reporte(tipo=tipo, punto=Point(-90.33, -0.70, srid=4326), huella="c2", fuente=Fuente.COORDINADOR, gravedad="peligro_vida").reporte
    assert avisos.de_reporte(leve) == 0 and avisos.de_reporte(grave) == 1
    assert [d for d, _ in enviados] == ["https://push.test/despierto"] and AvisoEnviado.objects.filter(retenido=True).count() == 2


def prueba_oleaje_fuerte_y_boletin_oficial_avisan(enviados, monkeypatch):
    from reportes import clima as panel

    monkeypatch.setattr(panel, "estado", lambda: {})
    suscribir("a", temas=["mar", "oficiales"])
    MarHora.objects.create(puerto="isabela", hora=AHORA + timedelta(hours=5), ola_m=3.1, obtenido=AHORA)
    MarHora.objects.create(puerto="santa-cruz", hora=AHORA + timedelta(hours=5), ola_m=1.2, obtenido=AHORA)
    Boletin.objects.create(fuente="inamhi", tipo="advertencia", huella="h" * 64, numero="89", afecta_galapagos=True, resumen="Lluvias de nivel muy alto.", enlace="https://inamhi.test/a.pdf")
    Boletin.objects.create(fuente="inocar", tipo="erfen", huella="e" * 64, afecta_galapagos=False, resumen="No nombra a Galápagos.")
    titulos = sorted(a.titulo for a in alertas.revisar())
    assert titulos == ["Advertencia del INAMHI n.º 89", "Oleaje fuerte en Puerto Villamil (Isabela)"]
    # El aviso abre el visor del sitio (con botón de volver), no el PDF de la institución, y no da instrucciones.
    assert enviados[-1][1]["enlace"] == f"/riesgos/boletin/{Boletin.objects.get(numero='89').pk}/" and "Lee el documento" not in enviados[-1][1]["cuerpo"]


def prueba_el_pronostico_de_manana_avisa_por_la_tarde(enviados):
    suscribir("a", temas=["pronostico"])
    tarde = datetime(2026, 11, 22, 23, 0, tzinfo=timezone.utc)  # 17:00 en Galápagos
    PronosticoEmitido.objects.create(punto="cascada-alta", emitido=tarde, fecha="2026-11-23", anticipacion=1, prob20=0.62, nivel="alta")
    PronosticoEmitido.objects.create(punto="puerto-baquerizo", emitido=tarde, fecha="2026-11-23", anticipacion=1, prob20=0.1, nivel="sin_senal")
    assert alertas._pronostico(tarde - timedelta(hours=6)) == []  # por la mañana no
    emitidos = alertas._pronostico(tarde)
    assert len(emitidos) == 1 and emitidos[0].zona == "santa-cruz" and "62 %" in emitidos[0].cuerpo


def prueba_elegir_temas_e_islas_desde_el_telefono(client, monkeypatch):
    from reportes import tareas

    monkeypatch.setattr(tareas, "avisar_bienvenida", type("Tarea", (), {"enqueue": staticmethod(lambda pk: None)}))
    client.defaults["HTTP_ORIGIN"] = "http://testserver"
    enviar = lambda datos: client.post("/riesgos/avisos/suscribir/", json.dumps(datos), content_type="application/json").json()  # noqa: E731
    base = {"endpoint": "https://push.test/tel", "keys": {"p256dh": "k", "auth": "a"}}
    assert enviar(base)["temas"] == ["peligros", "lluvia", "oficiales"]
    assert enviar({"endpoint": base["endpoint"], "temas": ["mar", "inventado"], "zonas": ["isabela", "marte"]}) == {"suscrito": True, "temas": ["mar"], "zonas": ["isabela"]}
    assert enviar({"endpoint": base["endpoint"], "consulta": True}) == {"suscrito": True, "temas": ["mar"], "zonas": ["isabela"], "de_noche": False}
    # De noche no llega nada, salvo que la persona lo pida.
    assert enviar({"endpoint": base["endpoint"], "temas": ["mar"], "zonas": [], "de_noche": True})["de_noche"] is True
    assert enviar({"endpoint": base["endpoint"], "consulta": True})["de_noche"] is True
    temas = client.get("/riesgos/api/clima/alertas").json()
    assert [t["id"] for t in temas["temas"]] == ["peligros", "lluvia", "pronostico", "mar", "oficiales"] and len(temas["zonas"]) == 3


# ── Nivel de lluvia peligrosa calculado en Django ────────────────────────────
def _lluvia(clave, ahora, mm_cada_5min, horas=3, hasta_hace_min=5):
    from clima.models import Estacion, Observacion

    fuente, codigo = clave.split("/")
    e, _ = Estacion.objects.get_or_create(fuente=fuente, codigo=codigo, defaults={"nombre": codigo})
    fin = ahora - timedelta(minutes=hasta_hace_min)
    Observacion.objects.bulk_create([Observacion(estacion=e, variable="lluvia_mm", ts=fin - timedelta(minutes=5 * i), valor=mm_cada_5min) for i in range(horas * 12)])
    return e


def prueba_el_nivel_sube_con_la_lluvia_y_sin_estaciones_dice_sin_datos():
    from clima import nivel

    ahora = datetime(2026, 11, 21, 12, 0, tzinfo=timezone.utc)
    _lluvia("inamhi/M0191", ahora, 5.0)      # 60 mm por hora en Puerto Ayora
    _lluvia("inamhi/M0221", ahora, 0.0)      # San Cristóbal, seco
    zonas = {z["id"]: z for z in nivel.calcular(ahora, recoleccion_ok=lambda f, t: True)["zonas"]}
    assert zonas["la-cascada"]["nivel"] == "muy alto" and zonas["la-cascada"]["R"]["R1h"] == 60.0
    assert zonas["san-cristobal"]["nivel"] == "bajo"
    assert zonas["isabela"]["nivel"] == "sin datos"       # nunca «bajo» por falta de datos
    usadas = [e for e in zonas["la-cascada"]["estaciones"] if e.get("usada")]
    assert len(usadas) == 1 and len(zonas["la-cascada"]["historial_72h"]) == 72


def prueba_un_sensor_danado_no_cuenta_y_un_reporte_de_campo_solo_sube():
    from clima import nivel
    from clima.models import EstacionDanada, NivelManual

    ahora = datetime(2026, 11, 21, 12, 0, tzinfo=timezone.utc)
    e = _lluvia("inamhi/M0191", ahora, 5.0)
    _lluvia("inamhi/M0221", ahora, 0.0)
    EstacionDanada.objects.create(estacion=e, variable="lluvia_mm", desde=ahora - timedelta(days=10), motivo="marca lluvias imposibles")
    NivelManual.objects.create(zona="san-cristobal", nivel="alto", desde=ahora - timedelta(hours=1), hasta=ahora + timedelta(hours=5), motivo="Reporte de campo")
    zonas = {z["id"]: z for z in nivel.calcular(ahora, recoleccion_ok=lambda f, t: True)["zonas"]}
    assert zonas["la-cascada"]["nivel"] == "sin datos" and any(x.get("danada") for x in zonas["la-cascada"]["estaciones"])
    assert zonas["san-cristobal"]["nivel"] == "alto" and zonas["san-cristobal"]["manual"]["motivo"] == "Reporte de campo"
    assert zonas["san-cristobal"]["nivel_instantaneo"] == "bajo"   # lo medido sigue a la vista


def prueba_cada_pasada_guarda_el_nivel_y_su_historia(monkeypatch, client):
    from clima import nivel, niveles
    from clima.models import NivelZona
    from reportes import clima as mapa

    ahora = datetime.now(timezone.utc).replace(second=0, microsecond=0)
    _lluvia("inamhi/M0191", ahora, 5.0)
    monkeypatch.setattr(nivel, "_recoleccion_viva", lambda desde: {"inamhi": {(ahora - timedelta(minutes=m)).strftime("%Y-%m-%dT%H") for m in range(0, 6000, 30)}})
    r = niveles.actualizar(ahora)
    assert r["zonas"] == 4 and NivelZona.objects.count() == 4
    assert NivelZona.objects.get(zona="la-cascada").nivel == "muy alto" and NivelZona.objects.get(zona="isabela").nivel == "sin datos"
    datos = client.get("/riesgos/api/clima/nivel").json()
    assert len(datos["zonas"]) == 4 and "no es una alerta oficial" in datos["aviso"].lower()
    # La franja del mapa lee el nivel de esta misma base, no de un archivo.
    assert mapa.nivel("la-cascada")["nivel"] == "muy alto"

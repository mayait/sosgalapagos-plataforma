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
    assert AvisoEnviado.objects.count() == 2


def prueba_la_lluvia_medida_dispara_un_aviso_por_zona(enviados, monkeypatch):
    from reportes import clima as panel

    suscribir("a")
    monkeypatch.setattr(panel, "estado", lambda: {"inundacion": {"zonas": [
        {"id": "santa-cruz-alta", "zona": "Parte alta", "nivel": "alto", "R": {"R24h": 120}},
        {"id": "la-cascada", "zona": "La Cascada", "nivel": "muy alto", "R": {"R24h": 233.4}}, {"id": "san-cristobal", "zona": "San Cristóbal", "nivel": "medio"}]}})
    emitidos = alertas.revisar()
    # Dos zonas de la misma isla en alerta: un solo aviso, con la peor.
    assert len(emitidos) == 1 and "muy alto" in emitidos[0].titulo and "233 mm" in emitidos[0].cuerpo and emitidos[0].zona == "santa-cruz"
    assert alertas.revisar() == []  # cinco minutos después no se repite


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
    assert enviados[-1][1]["enlace"] in ("https://inamhi.test/a.pdf", "/clima/")


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
    assert enviar({"endpoint": base["endpoint"], "consulta": True}) == {"suscrito": True, "temas": ["mar"], "zonas": ["isabela"]}
    temas = client.get("/riesgos/api/clima/alertas").json()
    assert [t["id"] for t in temas["temas"]] == ["peligros", "lluvia", "pronostico", "mar", "oficiales"] and len(temas["zonas"]) == 3

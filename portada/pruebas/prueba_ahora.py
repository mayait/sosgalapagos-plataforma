# SOS Galápagos · © 2026 Universidad San Francisco de Quito (USFQ) · Autor: Julián Maya <jamaya@usfq.edu.ec>
# Licencia Apache 2.0 (ver LICENSE y NOTICE): puede reutilizarse dando crédito.
"""Pruebas de «Ahora» en la portada: la hora del dato, el dato viejo, la zona sin datos, la línea de causa y los peligros."""
from datetime import datetime, timedelta, timezone

import pytest
from django.contrib.gis.geos import Point, Polygon

from portada import ahora as lectura

UTC = timezone.utc
AHORA = datetime(2026, 11, 23, 14, 40, tzinfo=UTC)  # 08:40 en Galápagos


def _estado(**por_zona):
    base = {
        "la-cascada": {"nivel": "bajo", "R": {"R1h": 0.0, "R3h": 0.0, "R24h": 12.0, "R72h": 40.0}, "factor": 1.0},
        "santa-cruz-alta": {"nivel": "medio", "R": {"R1h": 2.0, "R3h": 5.0, "R24h": 55.0, "R72h": 90.0}, "factor": 1.0},
        "san-cristobal": {"nivel": "bajo", "R": {"R1h": 1.0, "R3h": 2.0, "R24h": 32.0, "R72h": 50.0}, "factor": 1.0},
        "isabela": {"nivel": "sin datos", "R": {}},
    }
    for k, v in por_zona.items():
        base[k.replace("_", "-")].update(v)
    return {"zonas": [{"id": k, **v} for k, v in base.items()]}


def _filas(estado=None, edad_min=10, ultimas=None):
    dato = AHORA - timedelta(minutes=edad_min)
    u = ultimas if ultimas is not None else {"la-cascada": dato, "santa-cruz-alta": dato, "san-cristobal": dato, "isabela": None}
    r = lectura.filas(estado or _estado(), dato, u, AHORA)
    return r, {f["id"]: f for f in r["filas"]}


def prueba_las_cuatro_zonas_con_los_nombres_de_clima():
    r, _ = _filas()
    assert [(f["nombre"], f["lugar"]) for f in r["filas"]] == [
        ("La Cascada", "Puerto Ayora"), ("Parte alta de Santa Cruz", ""), ("San Cristóbal", ""), ("Isabela", "Puerto Villamil")]


def prueba_dato_reciente_con_cifras_y_hora_del_dato():
    r, f = _filas(edad_min=10)
    assert r["hora"] == "08:30"  # la del dato, no la de la página (08:40)
    assert f["la-cascada"]["estado"] == "vivo"
    assert f["la-cascada"]["cifras"] == "0 mm en la última hora · 12 mm en 24 h"
    assert f["la-cascada"]["nivel"] == "bajo" and f["la-cascada"]["tramos"] == 1 and f["la-cascada"]["tono"] == "bajo"
    assert f["santa-cruz-alta"]["tono"] == "medio" and f["santa-cruz-alta"]["tramos"] == 2


def prueba_dato_de_mas_de_30_min_va_en_gris_y_con_la_hora():
    _, f = _filas(edad_min=95)
    z = f["la-cascada"]
    assert z["estado"] == "viejo"
    assert z["hora"] == "07:05" and z["hace"] == "hace 1 hora y 35 minutos"
    assert z["cifras"]  # entre 30 min y 3 h, las cifras siguen, en gris


def prueba_dato_de_mas_de_3_h_sin_cifras():
    _, f = _filas(edad_min=200)
    z = f["la-cascada"]
    assert z["estado"] == "mudo" and z["cifras"] == "" and z["tramos"] == 0
    assert z["texto"] == "Las estaciones no han enviado datos desde las 05:20"
    assert "mm" not in z["texto"] and z["nivel"] != "bajo"


def prueba_zona_sin_datos_nunca_dice_0_mm_ni_bajo():
    _, f = _filas()
    isa = f["isabela"]
    assert isa["estado"] == "sin-estaciones" and isa["nivel"] == "sin estaciones"
    assert "0 mm" not in isa["cifras"] + isa["texto"] and "bajo" not in isa["nivel"]
    # Una zona con estaciones pero calladas: «sin datos».
    _, f = _filas(_estado(san_cristobal={"nivel": "sin datos", "R": {}}))
    sc = f["san-cristobal"]
    assert sc["estado"] == "sin-datos" and sc["nivel"] == "sin datos" and sc["cifras"] == ""
    assert "0 mm" not in sc["texto"] and "bajo" not in sc["texto"]
    # Sin ninguna medición conocida de sus estaciones, tampoco hay cifras.
    _, f = _filas(ultimas={"la-cascada": None, "santa-cruz-alta": None, "san-cristobal": None, "isabela": None})
    assert all(x["cifras"] == "" for x in f.values())


def prueba_linea_de_causa_por_la_lluvia_de_3_dias():
    # Parte alta: umbral propio de 72 h (alto = 200 mm). 229 mm en 3 días, 0,3 mm en la última hora.
    _, f = _filas(_estado(santa_cruz_alta={"nivel": "alto", "R": {"R1h": 0.3, "R3h": 0.8, "R24h": 20.0, "R72h": 229.0}}))
    z = f["santa-cruz-alta"]
    assert z["cifras"].startswith("0,3 mm en la última hora")
    assert z["causa"] == "Sigue alto por lo que llovió en 3 días (229 mm): el suelo está saturado."
    assert z["tono"] == "alto" and z["tramos"] == 3


def prueba_linea_de_causa_solo_cuando_corresponde():
    # Lloviendo fuerte ahora: no hace falta explicar.
    _, f = _filas(_estado(santa_cruz_alta={"nivel": "alto", "R": {"R1h": 31.0, "R3h": 40.0, "R24h": 60.0, "R72h": 229.0}}))
    assert f["santa-cruz-alta"]["causa"] is None
    # Nivel medio: no hay línea.
    _, f = _filas()
    assert all(x["causa"] is None for x in f.values())
    # Alto por 24 h (La Cascada no tiene umbral de 72 h): no se dice «3 días».
    _, f = _filas(_estado(la_cascada={"nivel": "alto", "R": {"R1h": 0.0, "R3h": 0.0, "R24h": 104.0, "R72h": 300.0}}))
    assert f["la-cascada"]["causa"] == "Sigue alto por lo que llovió en 24 h (104 mm)."
    # Lo sostiene la persistencia (ninguna ventana supera el umbral): no se culpa a la lluvia de 3 días.
    _, f = _filas(_estado(la_cascada={"nivel": "muy alto", "R": {"R1h": 0.2, "R3h": 3.0, "R24h": 40.0, "R72h": 60.0}}))
    assert "3 días" not in f["la-cascada"]["causa"] and "8 h" in f["la-cascada"]["causa"]
    assert f["la-cascada"]["tono"] == "muy-alto" and f["la-cascada"]["tramos"] == 4


def prueba_nivel_sin_estaciones_validas_no_se_esconde():
    # La coordinación subió el nivel por reportes de campo y las estaciones no tienen datos válidos.
    _, f = _filas(_estado(la_cascada={"nivel": "alto", "R": {}, "manual": {"nivel": "alto", "motivo": "x"}}))
    z = f["la-cascada"]
    assert z["nivel"] == "alto" and z["tramos"] == 3 and z["cifras"] == "" and "sin datos" not in z["nivel"]
    assert z["causa"] == "Lo subió la coordinación por reportes de campo." and "0 mm" not in (z["causa"] + z["texto"])
    # Lo sostiene la persistencia.
    _, f = _filas(_estado(la_cascada={"nivel": "muy alto", "R": {}}))
    assert f["la-cascada"]["tramos"] == 4 and "8 h" in f["la-cascada"]["causa"]


def prueba_silencio_en_lluvia_fuerte_no_es_bajo():
    _, f = _filas(_estado(la_cascada={"nivel": "muy alto", "silencio": True, "R": {}}))
    z = f["la-cascada"]
    assert z["estado"] == "silencio" and z["nivel"] == "sin datos en lluvia fuerte" and z["cifras"] == ""


def prueba_sin_calculo_la_seccion_queda_vacia():
    r = lectura.filas(None, None, {}, AHORA)
    assert r == {"filas": [], "hora": "", "vacio": True}


def prueba_mm_con_coma_decimal():
    assert lectura.mm(0.3) == "0,3 mm" and lectura.mm(12) == "12 mm" and lectura.mm(229.4) == "229 mm" and lectura.mm(0) == "0 mm"


# ── Con la base ─────────────────────────────────────────────────────────────

@pytest.mark.django_db
def prueba_la_portada_lee_el_nivel_guardado(client):
    from django.utils import timezone as dj

    from clima.models import Estacion, Estado

    ahora = dj.now()
    Estacion.objects.create(fuente="ambient", codigo="miconia", nombre="Miconia", ultima=ahora - timedelta(minutes=5))
    Estacion.objects.create(fuente="ambient", codigo="evolucion", nombre="Evolución", ultima=ahora - timedelta(minutes=95))
    Estado.objects.create(clave="inundacion", generado=ahora - timedelta(minutes=2), datos=_estado(
        santa_cruz_alta={"nivel": "alto", "R": {"R1h": 0.3, "R3h": 0.8, "R24h": 20.0, "R72h": 229.0}}))
    pagina = client.get("/").content.decode()
    assert "Sigue alto por lo que llovió en 3 días (229 mm): el suelo está saturado." in pagina
    assert "es-viejo" in pagina and "hace 1 hora y 35 minutos" in pagina  # La Cascada: su última medición es de hace 95 min
    assert "sin estaciones" in pagina and "Ver la lluvia en vivo en cada estación" in pagina
    assert "No es una alerta oficial" not in pagina  # el aviso de la API no se copia a la portada


@pytest.mark.django_db
def prueba_sin_datos_del_clima_la_seccion_se_ve_limpia(client):
    pagina = client.get("/").content.decode()
    assert "Todavía no hay datos de lluvia de las estaciones." in pagina and 'href="/clima/"' in pagina
    assert "0 mm" not in pagina


def _reporte(gravedad="no_pasar", fuente="vecino", horas=2, zona=None, nota=""):
    from django.utils import timezone as dj

    from reportes.models import Reporte, TipoRiesgo

    return Reporte.objects.create(tipo=TipoRiesgo.objects.get(codigo="agua_via"), gravedad=gravedad, fuente=fuente, zona=zona, nota=nota,
                                  punto=Point(-90.3145, -0.7435, srid=4326), visto_en=dj.now() - timedelta(hours=horas))


@pytest.mark.django_db
def prueba_sin_puntos_vivos_da_el_texto_exacto(client):
    _reporte(horas=50)
    _reporte(fuente="anterior", horas=1)
    pagina = client.get("/").content.decode()
    assert "Todavía no hay puntos en el mapa. Si ves algo, repórtalo." in pagina


@pytest.mark.django_db
def prueba_cuenta_todos_los_puntos_del_mapa_por_clase_y_zona_sin_texto_libre(client):
    from zonas.models import Zona

    cascada = Zona.objects.create(nombre="La Cascada", isla="Santa Cruz", geometria=Polygon.from_bbox((-90.32, -0.75, -90.31, -0.74)))
    _reporte(zona=cascada, nota="Texto libre de un vecino que no debe salir")
    _reporte(gravedad="cuidado", zona=cascada)
    _reporte(fuente="anterior", zona=cascada)
    pagina = client.get("/").content.decode()
    assert "2 puntos en el mapa</b>: 2 peligros" in pagina and "La Cascada" in pagina
    assert "Texto libre de un vecino" not in pagina
    assert "zona segura" not in pagina.lower() and "sin riesgo" not in pagina.lower()


@pytest.mark.django_db
def prueba_los_botones_dicen_reportar_un_punto_y_hay_boton_de_clima(client):
    pagina = client.get("/").content.decode()
    assert "Reportar un punto" in pagina and "Reportar un peligro" not in pagina
    assert 'class="pt-boton pt-boton-clima" href="/clima/"' in pagina

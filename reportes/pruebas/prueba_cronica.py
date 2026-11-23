# SOS Galápagos · © 2026 Universidad San Francisco de Quito (USFQ) · Autor: Julián Maya <jamaya@usfq.edu.ec>
# Licencia Apache 2.0 (ver LICENSE y NOTICE): puede reutilizarse dando crédito.
"""Pruebas de la línea del tiempo (sucesos sin punto en el mapa), de las observaciones y de la duración de los daños."""
from datetime import timedelta

import pytest
from django.utils import timezone

from reportes.models import Reporte, Suceso, TipoRiesgo

pytestmark = pytest.mark.django_db


def prueba_los_sucesos_reunen_avisos_boletines_y_lo_escrito_a_mano(client):
    from clima.models import AvisoEnviado, Boletin

    ahora = timezone.now()
    AvisoEnviado.objects.create(clave="lluvia:santa-cruz:alto:x", tema="lluvia", zona="santa-cruz", titulo="Llueve fuerte en Santa Cruz", cuerpo="12 mm en la última hora.", enlace="/clima/", entregados=3)
    AvisoEnviado.objects.create(clave="pronostico:isabela:x", tema="pronostico", zona="isabela", titulo="Mañana puede llover fuerte en Isabela", cuerpo="c", enlace="/clima/", retenido=True)
    AvisoEnviado.objects.create(clave="boletin:abc", tema="oficiales", zona="", titulo="Advertencia del INAMHI n.º 89", cuerpo="c", enlace="https://inamhi.test/a.pdf", entregados=3)  # sale como boletín, no dos veces
    AvisoEnviado.objects.create(clave="viejo", tema="lluvia", zona="", titulo="(ya avisado en este bloque, con la clave anterior)", cuerpo="", enlace="")
    Boletin.objects.create(fuente="inamhi", tipo="advertencia", huella="h" * 64, numero="89", afecta_galapagos=True, resumen="Lluvias de nivel muy alto.", enlace="https://inamhi.test/a.pdf", vigente_hasta=ahora + timedelta(days=1))
    Boletin.objects.create(fuente="inocar", tipo="erfen", huella="e" * 64, afecta_galapagos=False, resumen="No nombra a Galápagos.")
    Suceso.objects.create(clase="noticia", titulo="Reabren la vía a Baltra", fuente="Radio de las islas", enlace="https://medio.test/n", zona="sc-alta", ocurrido=ahora - timedelta(hours=2))
    Suceso.objects.create(clase="oficial", titulo="El COE suspende clases", fuente="COE cantonal", zona="santa-cruz", hasta=ahora + timedelta(days=2), ocurrido=ahora - timedelta(hours=1))
    Suceso.objects.create(clase="nota", titulo="Borrador", visible=False)
    Suceso.objects.create(clase="nota", titulo="Muy viejo", ocurrido=ahora - timedelta(days=90))

    sucesos = client.get("/riesgos/api/sucesos.json").json()["sucesos"]
    por_titulo = {s["titulo"]: s for s in sucesos}
    assert set(por_titulo) == {"Llueve fuerte en Santa Cruz", "Mañana puede llover fuerte en Isabela", "Advertencia del INAMHI n.º 89", "Reabren la vía a Baltra", "El COE suspende clases"}
    lluvia = por_titulo["Llueve fuerte en Santa Cruz"]
    assert lluvia["clase"] == "aviso" and lluvia["zonas"] == ["sc", "sc-alta"] and lluvia["detalle"] == "enviado a 3 teléfonos" and not lluvia["retenido"]
    retenido = por_titulo["Mañana puede llover fuerte en Isabela"]
    assert retenido["retenido"] and retenido["zonas"] == ["is"] and "era de noche" in retenido["detalle"]
    oficial = por_titulo["Advertencia del INAMHI n.º 89"]
    assert oficial["clase"] == "oficial" and oficial["fuente"] == "INAMHI" and oficial["zonas"] == [] and "documento oficial" in oficial["detalle"] and oficial["enlace"].startswith("https://inamhi")
    assert por_titulo["Reabren la vía a Baltra"]["zonas"] == ["sc-alta"] and por_titulo["Reabren la vía a Baltra"]["fuente"] == "Radio de las islas"
    assert por_titulo["El COE suspende clases"]["zonas"] == ["sc", "sc-alta"] and "vigente hasta" in por_titulo["El COE suspende clases"]["detalle"]
    assert [s["t"] for s in sucesos] == sorted((s["t"] for s in sucesos), reverse=True)
    pagina = client.get("/riesgos/informe/").content.decode()
    assert "/riesgos/api/sucesos.json" in pagina and "comunicados oficiales" in pagina


def prueba_un_dano_en_infraestructura_dura_lo_que_dice_quien_avisa(client):
    base = {"tipo": "dano_infraestructura", "lat": "-0.7435", "lon": "-90.3145"}
    con = Reporte.objects.get(id_publico=client.post("/riesgos/reportar/", {**base, "dura_dias": "30"}).json()["id"])
    assert 29.9 < (con.vence_en - con.visto_en).total_seconds() / 86400 < 30.1
    sin = Reporte.objects.get(id_publico=client.post("/riesgos/reportar/", {**base, "lat": "-0.76"}).json()["id"])
    assert (sin.vence_en - sin.visto_en).days == 14                        # sin dato: el plazo del tipo
    raro = Reporte.objects.get(id_publico=client.post("/riesgos/reportar/", {**base, "lat": "-0.77", "dura_dias": "9999"}).json()["id"])
    assert (raro.vence_en - raro.visto_en).days == 14                      # fuera de rango: se ignora
    # En otro tipo la duración no se pregunta ni se acepta.
    agua = Reporte.objects.get(id_publico=client.post("/riesgos/reportar/", {"tipo": "agua_via", "lat": "-0.78", "lon": "-90.3145", "dura_dias": "30"}).json()["id"])
    assert (agua.vence_en - agua.visto_en).total_seconds() == 6 * 3600
    ficha = client.get(f"/riesgos/r/{con.id_publico}/").content.decode()
    assert "Durará" in ficha and "según quien avisó" in ficha
    assert "¿Cuánto tiempo va a estar así?" in client.get("/riesgos/reportar/").content.decode()


def prueba_se_puede_decir_que_aqui_no_paso_nada_para_mejorar_el_mapa(client):
    tipos = {t.codigo: t for t in TipoRiesgo.objects.filter(clase="observa")}
    assert set(tipos) == {"aqui_se_inundo", "aqui_no_paso", "zona_de_riesgo"} and tipos["zona_de_riesgo"].plazo_horas == 720
    r = client.post("/riesgos/reportar/", {"tipo": "aqui_no_paso", "lat": "-0.7408", "lon": "-90.3152", "nota": "El agua llegó al bordillo y no entró"})
    assert r.status_code == 201
    reporte = Reporte.objects.get(id_publico=r.json()["id"])
    assert reporte.tipo.clase == "observa" and (reporte.vence_en - reporte.visto_en).days == 3
    datos = client.get("/riesgos/api/reportes/vivos.geojson").json()["features"][0]["properties"]
    assert datos["clase"] == "observa" and datos["icono"] == "seco"
    pagina = client.get("/riesgos/reportar/").content.decode()
    assert "Ayúdanos a mejorar el mapa" in pagina and "Aquí siempre se inunda" in pagina and 'id="i-seco"' in pagina and 'id="i-alerta"' in pagina and 'id="i-marca"' in pagina


@pytest.mark.parametrize("texto,tipo", [
    ("aquí en mi barrio todo está bien, no entró el agua", "aqui_no_paso"),
    ("por aquí no se inundó, todo tranquilo en La Cascada", "aqui_no_paso"),
    ("en esta esquina siempre se inunda cuando llueve, barrio El Edén", "zona_de_riesgo"),
    ("anoche se inundó la calle Marchena, llegó a la rodilla", "aqui_se_inundo"),
])
def prueba_por_whatsapp_tambien_se_avisa_que_no_paso_o_que_ya_paso(texto, tipo):
    from entradas import filtro, ia

    assert filtro.evaluar(texto).es_material
    assert ia.por_reglas([texto]).tipo == tipo


def prueba_por_whatsapp_un_dano_lleva_su_duracion(settings):
    from entradas import ia

    e = ia.Extraccion(es_reporte=True, tipo="dano_infraestructura", duracion_dias=30)
    assert e.duracion_dias == 30
    with pytest.raises(Exception):
        ia.Extraccion(es_reporte=True, duracion_dias=5000)
    assert "duracion_dias" in ia.INSTRUCCIONES and "aqui_no_paso" in ia.INSTRUCCIONES

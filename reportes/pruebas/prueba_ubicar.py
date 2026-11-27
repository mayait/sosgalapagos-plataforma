# SOS Galápagos · © 2026 Universidad San Francisco de Quito (USFQ) · Autor: Julián Maya <jamaya@usfq.edu.ec>
# Licencia Apache 2.0 (ver LICENSE y NOTICE): puede reutilizarse dando crédito.
"""Pruebas de «Ayúdanos a ubicar»: la regla de coincidencia, los puntos y lo que se ve."""
import re
from datetime import timedelta
from io import BytesIO

import pytest
from django.contrib.gis.geos import Point
from django.core.files.base import ContentFile
from django.utils import timezone
from PIL import Image

from reportes import reglas
from reportes.models import Colaborador, EstadoUbicar, PorUbicar, Reporte

pytestmark = pytest.mark.django_db

AQUI = Point(-90.3145, -0.7435, srid=4326)
A_40_M = Point(-90.3145, -0.74386, srid=4326)   # unos 40 m al sur
A_300_M = Point(-90.3145, -0.7462, srid=4326)   # unos 300 m al sur


def jpeg():
    salida = BytesIO()
    Image.new("RGB", (400, 300), "steelblue").save(salida, "JPEG")
    return ContentFile(salida.getvalue(), name="foto.jpg")


def por_ubicar(**campos):
    item = PorUbicar(visto_en=campos.pop("visto_en", timezone.now() - timedelta(hours=1)), texto=campos.pop("texto", "Así está la calle"), **campos)
    item.foto.save("foto.jpg", jpeg(), save=False)
    item.save()
    return item


def prueba_una_sola_persona_no_basta():
    item = por_ubicar()
    r = reglas.proponer_ubicacion(item, AQUI, "h1", nombre="Gaviota")
    assert not r.aceptada and r.faltan == 1 and r.puntos == 1
    item.refresh_from_db()
    assert item.estado == EstadoUbicar.PENDIENTE
    assert Colaborador.objects.get(huella="h1").nombre == "Gaviota"


def prueba_dos_personas_cerca_la_pasan_al_mapa():
    item = por_ubicar()
    reglas.proponer_ubicacion(item, AQUI, "h1")
    r = reglas.proponer_ubicacion(item, A_40_M, "h2")
    assert r.aceptada and r.reporte
    item.refresh_from_db()
    assert item.estado == EstadoUbicar.UBICADO and item.reporte == r.reporte
    reporte = Reporte.objects.get(pk=r.reporte.pk)
    # El punto es el medio de las dos propuestas y lleva la hora del mensaje, no la de ahora.
    assert reporte.punto.y == pytest.approx((AQUI.y + A_40_M.y) / 2)
    assert reporte.visto_en == item.visto_en
    assert reporte.foto and reporte.nota == "Así está la calle"
    # Las dos ganan el premio y una foto ubicada.
    for h in ("h1", "h2"):
        c = Colaborador.objects.get(huella=h)
        assert c.ubicados == 1 and c.puntos == 1 + 5


def prueba_dos_personas_lejos_no_coinciden():
    item = por_ubicar()
    reglas.proponer_ubicacion(item, AQUI, "h1")
    r = reglas.proponer_ubicacion(item, A_300_M, "h2")
    assert not r.aceptada
    assert PorUbicar.objects.get(pk=item.pk).estado == EstadoUbicar.PENDIENTE


def prueba_la_misma_persona_dos_veces_no_cuenta_doble():
    item = por_ubicar()
    reglas.proponer_ubicacion(item, AQUI, "h1")
    r = reglas.proponer_ubicacion(item, A_40_M, "h1")  # corrige su propia propuesta
    assert not r.aceptada and r.puntos == 0
    assert item.ubicaciones.count() == 1
    assert Colaborador.objects.get(huella="h1").puntos == 1


def prueba_coordinacion_la_pasa_sola():
    item = por_ubicar()
    r = reglas.proponer_ubicacion(item, AQUI, "coord", de_coordinacion=True)
    assert r.aceptada
    assert Reporte.objects.get(pk=r.reporte.pk).punto.equals_exact(AQUI, 1e-9)


def prueba_ya_ubicada_no_acepta_mas():
    item = por_ubicar()
    reglas.proponer_ubicacion(item, AQUI, "coord", de_coordinacion=True)
    r = reglas.proponer_ubicacion(item, AQUI, "h9")
    assert r.error and not r.aceptada


def prueba_el_texto_de_quien_ayuda_oculta_los_numeros():
    item = por_ubicar()
    reglas.proponer_ubicacion(item, AQUI, "h1", texto="frente a la tienda, llamen al 0991234567")
    assert "0991234567" not in item.ubicaciones.get().texto


def prueba_la_linea_del_tiempo_dice_cuantas_esperan(client):
    por_ubicar()
    por_ubicar(estado=EstadoUbicar.REVISION)  # no cuenta: no es pública
    pagina = client.get("/riesgos/informe/").content.decode()
    assert "Ayúdanos a ubicar" in pagina
    assert 'href="/riesgos/ubicar/"' in pagina
    assert client.get("/riesgos/informe/").context["por_ubicar"] == 1


def prueba_la_lista_no_muestra_lo_que_esta_en_revision(client):
    visible = por_ubicar(texto="Se ve la quebrada")
    oculta = por_ubicar(texto="Foto con una cara", estado=EstadoUbicar.REVISION)
    pagina = client.get("/riesgos/ubicar/").content.decode()
    assert visible.id_publico in pagina and oculta.id_publico not in pagina
    assert client.get(f"/riesgos/ubicar/{oculta.id_publico}/").status_code == 404


def prueba_ubicar_desde_la_pagina(client):
    item = por_ubicar()
    assert client.get(f"/riesgos/ubicar/{item.id_publico}/").status_code == 200
    r = client.post(f"/riesgos/ubicar/{item.id_publico}/", {"lat": "-0.7435", "lon": "-90.3145", "nombre": "Piquero"})
    assert r.status_code == 201 and r.json()["faltan"] == 1
    otro = client.__class__()
    r = otro.post(f"/riesgos/ubicar/{item.id_publico}/", {"lat": "-0.74352", "lon": "-90.31452"})
    assert r.json()["aceptada"] and r.json()["enlace"].startswith("/riesgos/?r=")
    # Quien ayudó aparece en la tabla de quién ha ubicado más.
    assert "Piquero" in client.get("/riesgos/ubicar/").content.decode()


def prueba_ubicar_fuera_de_galapagos_no_vale(client):
    item = por_ubicar()
    assert client.post(f"/riesgos/ubicar/{item.id_publico}/", {"lat": "-2.19", "lon": "-79.88"}).status_code == 400


def prueba_coordinacion_aprueba_una_foto_en_revision():
    item = por_ubicar(estado=EstadoUbicar.REVISION, motivo_revision="persona en primer plano")
    reglas.aprobar_por_ubicar(item)
    assert PorUbicar.objects.get(pk=item.pk).estado == EstadoUbicar.PENDIENTE


def prueba_lo_viejo_deja_de_pedirse():
    por_ubicar(visto_en=timezone.now() - timedelta(days=30))
    assert PorUbicar.objects.publicos().count() == 0


def prueba_lo_publico_no_dice_de_donde_vino(client):
    """Privacidad: ni el origen, ni la huella, ni números largos en lo que se publica."""
    item = por_ubicar(texto="Calle inundada", id_origen="wa:abc123def456", huella="f" * 64,
                      clasificacion={"grupo": "no debería verse"})
    for url in ("/riesgos/ubicar/", f"/riesgos/ubicar/{item.id_publico}/", "/riesgos/informe/"):
        pagina = client.get(url).content.decode()
        assert "abc123def456" not in pagina and "f" * 64 not in pagina and "no debería verse" not in pagina
        texto_visible = re.sub(r"<script.*?</script>|<[^>]*>", " ", pagina, flags=re.S)
        assert not re.search(r"\d{7,}", texto_visible)

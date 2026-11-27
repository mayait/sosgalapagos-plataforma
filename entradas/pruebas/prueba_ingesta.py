# SOS Galápagos · © 2026 Universidad San Francisco de Quito (USFQ) · Autor: Julián Maya <jamaya@usfq.edu.ec>
# Licencia Apache 2.0 (ver LICENSE y NOTICE): puede reutilizarse dando crédito.
"""Pruebas de lo que sube la Mac cada hora (POST /riesgos/api/ingesta/whatsapp)."""
from datetime import timedelta
from io import BytesIO

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone
from PIL import Image

from reportes import fotos
from reportes.models import EstadoUbicar, PorUbicar, Reporte

pytestmark = pytest.mark.django_db
URL = "/riesgos/api/ingesta/whatsapp"
LLAVE = "llave-de-prueba"


@pytest.fixture(autouse=True)
def llave(settings):
    settings.INGESTA_LLAVE = LLAVE


def foto(color="seagreen", gps=False):
    imagen = Image.new("RGB", (400, 300), color)
    salida = BytesIO()
    if gps:
        exif = imagen.getexif()
        g = exif.get_ifd(fotos.ETIQUETA_GPS)
        g[1], g[2], g[3], g[4] = "S", (0, 44, 36.6), "W", (90, 18, 52.2)
        exif[fotos.ETIQUETA_GPS] = g
        imagen.save(salida, "JPEG", exif=exif)
    else:
        imagen.save(salida, "JPEG")
    return SimpleUploadedFile("foto.jpg", salida.getvalue(), content_type="image/jpeg")


def subir(client, llave=LLAVE, **campos):
    datos = {"id_origen": "wa:0123456789abcdef", "visto_en": (timezone.now() - timedelta(hours=2)).isoformat(), "texto": "Se desbordó la quebrada", **campos}
    return client.post(URL, datos, headers={"X-Llave": llave})


def prueba_sin_llave_no_entra(client):
    assert subir(client, llave="otra", foto=foto()).status_code == 403
    assert not PorUbicar.objects.exists()


def prueba_sin_ubicacion_va_a_ayudanos_a_ubicar(client):
    r = subir(client, foto=foto(), tipo="quebrada")
    assert r.status_code == 200 and r.json()["destino"] == "ubicar"
    item = PorUbicar.objects.get()
    assert item.estado == EstadoUbicar.PENDIENTE and item.foto and not item.reporte
    assert item in PorUbicar.objects.publicos()


def prueba_con_ubicacion_segura_va_al_mapa(client):
    r = subir(client, foto=foto(), lat="-0.7435", lon="-90.3145", tipo="agua_via")
    assert r.json()["destino"] == "mapa"
    reporte = Reporte.objects.get(id_publico=r.json()["reporte"])
    assert reporte.fuente == "whatsapp" and reporte.foto and reporte.contenido_visible
    assert reporte.nota == "Se desbordó la quebrada"


def prueba_dos_veces_lo_mismo_no_duplica(client):
    subir(client, foto=foto())
    r = subir(client, foto=foto())
    assert r.json()["ya"] is True
    assert PorUbicar.objects.count() == 1


def prueba_foto_que_pide_revision_no_se_publica(client):
    r = subir(client, foto=foto(), revisar="1", motivo="persona en primer plano")
    assert r.json()["destino"] == "revision"
    assert PorUbicar.objects.publicos().count() == 0


def prueba_con_ubicacion_y_revision_sale_el_punto_sin_la_foto(client):
    r = subir(client, foto=foto(), lat="-0.7435", lon="-90.3145", revisar="1", motivo="menor")
    reporte = Reporte.objects.get(id_publico=r.json()["reporte"])
    assert not reporte.foto
    item = PorUbicar.objects.get()
    assert item.estado == EstadoUbicar.REVISION and item.reporte == reporte


def prueba_el_servidor_vuelve_a_limpiar(client):
    subir(client, foto=foto(gps=True), texto="Llamen al 0991234567, está feo")
    item = PorUbicar.objects.get()
    assert "0991234567" not in item.texto
    item.foto.open("rb")
    from PIL import Image as I

    assert not I.open(item.foto).getexif()  # la foto se guarda sin metadatos


def prueba_la_misma_foto_de_otro_grupo_no_se_pide_dos_veces(client):
    subir(client, foto=foto("tomato"))
    r = subir(client, foto=foto("tomato"), id_origen="wa:fedcba9876543210")
    assert r.json()["destino"] == "repetida"
    assert PorUbicar.objects.publicos().count() == 1


@pytest.mark.parametrize("campos", [
    {"id_origen": "NO VALE"},
    {"visto_en": "ayer"},
    {"lat": "-2.19", "lon": "-79.88"},
    {"texto": "", "foto": None},
])
def prueba_lo_que_no_vale_se_rechaza(client, campos):
    datos = {"foto": foto(), **campos}
    if datos.get("foto") is None:
        datos.pop("foto")
    assert subir(client, **datos).status_code == 400


def prueba_limite_por_hora(client, settings):
    settings.INGESTA_LIMITE_HORA = 1
    subir(client, foto=foto())
    assert subir(client, foto=foto("navy"), id_origen="wa:1111111111111111").status_code == 429

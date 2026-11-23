# SOS Galápagos · © 2026 Universidad San Francisco de Quito (USFQ) · Autor: Julián Maya <jamaya@usfq.edu.ec>
# Licencia Apache 2.0 (ver LICENSE y NOTICE): puede reutilizarse dando crédito.
"""Fotos de los reportes: se lee la ubicación y se guardan sin metadatos."""
from io import BytesIO

from django.core.files.base import ContentFile
from PIL import Image, ImageOps

LADO_MAXIMO = 1600
ETIQUETA_GPS = 0x8825


def _a_grados(valor, referencia):
    grados, minutos, segundos = (float(x) for x in valor)
    decimal = grados + minutos / 60 + segundos / 3600
    return -decimal if referencia in ("S", "W") else decimal


def ubicacion_de(imagen):
    """(lat, lon) de los metadatos de la foto, o None si no trae."""
    try:
        gps = imagen.getexif().get_ifd(ETIQUETA_GPS)
        return _a_grados(gps[2], gps[1]), _a_grados(gps[4], gps[3])
    except Exception:
        return None


def procesar(archivo):
    """Devuelve (foto limpia lista para guardar, ubicación o None).

    La imagen se vuelve a codificar desde los píxeles: no queda ningún metadato
    (ubicación, modelo del teléfono, fecha) en lo que se guarda.
    """
    imagen = Image.open(archivo)
    ubicacion = ubicacion_de(imagen)
    imagen = ImageOps.exif_transpose(imagen).convert("RGB")  # endereza antes de quitar los metadatos
    imagen.thumbnail((LADO_MAXIMO, LADO_MAXIMO))
    salida = BytesIO()
    imagen.save(salida, "JPEG", quality=82, optimize=True)
    return ContentFile(salida.getvalue(), name="foto.jpg"), ubicacion

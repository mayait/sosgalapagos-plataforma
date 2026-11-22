# SOS Galápagos · © 2026 Universidad San Francisco de Quito (USFQ) · Autor: Julián Maya <jamaya@usfq.edu.ec>
# Todos los derechos reservados. Usar, copiar, modificar o derivar de este código requiere permiso escrito del autor (ver LICENSE).
"""Filtros de plantilla: edades y distancias dichas como las diría una persona."""
import os

from django import template
from django.contrib.staticfiles import finders
from django.templatetags.static import static

register = template.Library()


@register.simple_tag
def propio(ruta):
    """URL de un archivo propio (estaticos/mapa/…) con su versión: ?v=<fecha de modificación>.

    Sin paso de compilación los nombres no cambian, y el navegador puede seguir usando
    un JavaScript viejo. Con la versión en la URL, un archivo que cambia se vuelve a pedir.
    """
    archivo = finders.find(ruta)
    version = int(os.path.getmtime(archivo)) if archivo else 0
    return f"{static(ruta)}?v={version}"


def _duracion(segundos):
    minutos = int(segundos // 60)
    if minutos < 1:
        return "menos de 1 min"
    if minutos < 60:
        return f"{minutos} min"
    horas = minutos // 60
    if horas < 24:
        resto = minutos % 60
        return f"{horas} h" if resto < 5 or horas >= 6 else f"{horas} h {resto} min"
    dias = horas // 24
    return f"{dias} día" if dias == 1 else f"{dias} días"


@register.filter
def hace(fecha, ahora):
    """«hace 25 min»"""
    return "hace " + _duracion((ahora - fecha).total_seconds())


@register.filter
def falta(fecha, ahora):
    """«en 3 h»"""
    segundos = (fecha - ahora).total_seconds()
    return "en " + _duracion(segundos) if segundos > 0 else "ya"


@register.filter
def metros(valor):
    valor = float(valor)
    if valor < 950:
        return f"{round(valor / 10) * 10:.0f} m"
    return f"{valor / 1000:.1f} km".replace(".", ",")

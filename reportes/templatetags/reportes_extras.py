"""Filtros de plantilla: edades y distancias dichas como las diría una persona."""
from django import template

register = template.Library()


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

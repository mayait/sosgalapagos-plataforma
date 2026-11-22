"""Sensores marcados como dañados (se marcan en el admin).

Sus datos crudos se siguen guardando; desde la fecha «desde», las variables marcadas no se usan
para el nivel de lluvia ni se publican en el panel.
"""
import datetime as dt

UTC = dt.timezone.utc


def vigentes(ahora=None):
    """{clave de estación: {desde, desde_dt, variables, motivo}} de los daños que siguen abiertos."""
    from .models import EstacionDanada

    ahora = ahora or dt.datetime.now(UTC)
    salida = {}
    for d in EstacionDanada.objects.select_related("estacion").exclude(hasta__lte=ahora):
        x = salida.setdefault(d.estacion.clave, {"desde_dt": d.desde, "variables": [], "motivo": d.motivo})
        x["variables"].append(d.variable)
        x["desde_dt"] = min(x["desde_dt"], d.desde)
    for x in salida.values():
        x["desde"] = x["desde_dt"].astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    return salida


def danada(marcas, clave, variable="lluvia_mm", cuando=None):
    x = marcas.get(clave)
    if not x or variable not in x["variables"]:
        return None
    if cuando is not None and cuando < x["desde_dt"]:
        return None
    return x


def publica(marcas, clave):
    x = marcas.get(clave)
    return None if not x else {"desde": x["desde"], "variables": x["variables"], "motivo": x.get("motivo")}

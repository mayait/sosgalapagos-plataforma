"""Sensores marcados como dañados. Misma interfaz que el módulo original, pero lee del admin de Django.

Los datos crudos se siguen guardando; desde la fecha «desde», las variables marcadas no se usan
para el nivel de lluvia ni se publican en el panel.
"""
import datetime as dt


def _cargar():
    from clima.models import EstacionDanada

    ahora = dt.datetime.now(dt.timezone.utc)
    salida = {}
    for d in EstacionDanada.objects.select_related("estacion").exclude(hasta__lte=ahora):
        x = salida.setdefault(d.estacion.clave, {"desde": d.desde.astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "desde_dt": d.desde, "variables": [], "motivo": d.motivo})
        x["variables"].append(d.variable)
        if d.desde < x["desde_dt"]:
            x["desde_dt"], x["desde"] = d.desde, d.desde.astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    return salida


class _Perezoso(dict):
    """Se llena al primer uso y se puede refrescar: los registros cambian en el admin sin reiniciar nada."""

    def refrescar(self):
        self.clear()
        self.update(_cargar())


DANADAS = _Perezoso()


def danada(clave, variable="lluvia_mm", cuando=None):
    x = DANADAS.get(clave)
    if not x or variable not in x["variables"]:
        return None
    if cuando is not None and cuando < x["desde_dt"]:
        return None
    return x


def publica(clave):
    x = DANADAS.get(clave)
    return None if not x else {"desde": x["desde"], "variables": x["variables"], "motivo": x.get("motivo")}

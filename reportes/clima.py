# SOS Galápagos · © 2026 Universidad San Francisco de Quito (USFQ) · Autor: Julián Maya <jamaya@usfq.edu.ec>
# Licencia Apache 2.0 (ver LICENSE y NOTICE): puede reutilizarse dando crédito.
"""El nivel de lluvia y la lluvia por hora para el mapa y la línea del tiempo.

Salen de esta misma base (la app `clima`). Solo en una Mac de desarrollo, donde no se recoge
clima, se leen los archivos públicos de sosgalapagos.org (CLIMA_ESTADO y CLIMA_HORARIO).
"""
import json
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen

from django.conf import settings
from django.core.cache import cache


def _leer(origen=None):
    origen = origen or settings.CLIMA_ESTADO
    if origen.startswith("http"):
        pedido = Request(origen, headers={"User-Agent": "sosgalapagos-plataforma (desarrollo local)"})
        with urlopen(pedido, timeout=8) as respuesta:
            return json.load(respuesta)
    return json.loads(Path(origen).read_text())


def estado():
    datos = cache.get("clima_estado")
    if datos is None:
        from clima.models import Estado

        guardado = Estado.objects.filter(clave="inundacion").first()
        if guardado:
            datos = {"inundacion": guardado.datos}
        else:  # desarrollo local, sin clima propio
            try:
                datos = _leer()
            except Exception:
                datos = {}
        cache.set("clima_estado", datos, 60)
    return datos


def zona_por_punto(lon, lat):
    """Zona de /clima que corresponde a un punto. Hoy /clima solo tiene cuatro zonas."""
    if lon < -90.7:
        return "isabela"
    if lon > -89.9:
        return "san-cristobal"
    return "santa-cruz-alta" if lat > -0.70 else "la-cascada"


def nivel(zona_id):
    """Resumen para la franja superior del mapa, o None si no hay dato fresco."""
    datos = estado()
    inundacion = datos.get("inundacion") or {}
    zona = next((z for z in inundacion.get("zonas", []) if z.get("id") == zona_id), None)
    if not zona:
        return None
    calculado = datetime.fromisoformat(inundacion["calculado"].replace("Z", "+00:00"))
    edad_min = (datetime.now(timezone.utc) - calculado).total_seconds() / 60
    if edad_min > settings.CLIMA_MAX_EDAD_MIN:
        return None
    lluvia = zona.get("R") or {}
    return {
        "zona": zona_id,
        "nombre": zona.get("zona", ""),
        "nivel": zona.get("nivel", ""),
        "color": zona.get("color", "#666666"),
        "lluvia_1h": lluvia.get("R1h"),
        "lluvia_24h": lluvia.get("R24h"),
        "hace_min": round(edad_min),
    }


def horario():
    """Lluvia por hora de cada estación, tal como la publica /clima. Se guarda 5 minutos en memoria."""
    datos = cache.get("clima_horario")
    if datos is None:
        try:
            datos = _leer(settings.CLIMA_HORARIO)
        except Exception:
            datos = {}
        cache.set("clima_horario", datos, 300)
    return datos


def _en_base():
    """True si hay clima en esta base. En una Mac de desarrollo, sin recolección, no."""
    from clima.models import Horaria

    return Horaria.objects.filter(variable="lluvia_mm").exists()


def estaciones_con_lluvia():
    """Estaciones que tienen serie horaria de lluvia: [{id, nombre, isla}], ordenadas por isla y nombre."""
    if _en_base():
        from clima.models import Estacion, EstacionDanada

        danadas = set(EstacionDanada.objects.filter(variable="lluvia_mm", hasta__isnull=True).values_list("estacion_id", flat=True))
        con_lluvia = Estacion.objects.filter(horarias__variable="lluvia_mm").exclude(fuente="goes").exclude(pk__in=danadas).distinct()
        return sorted(({"id": e.clave, "nombre": e.nombre or e.codigo, "isla": e.isla} for e in con_lluvia), key=lambda x: (x["isla"], x["nombre"]))
    series = (horario().get("series") or {})
    nombres = {f"{e.get('fuente')}/{e.get('estacion')}": e for e in estado().get("estaciones", [])}
    lista = []
    for clave, serie in series.items():
        if "lluvia_mm" not in serie:
            continue
        e = nombres.get(clave, {})
        lista.append({"id": clave, "nombre": e.get("nombre") or clave.split("/")[-1], "isla": e.get("isla") or ""})
    return sorted(lista, key=lambda x: (x["isla"], x["nombre"]))


def lluvia_por_hora(estacion, desde, hasta):
    """Lluvia (mm) por hora de una estación entre dos instantes UTC. None = sin dato en esa hora.

    Devuelve (inicio de la primera hora, lista). No se suman ni se promedian estaciones:
    se muestra la serie de una, como la publica /clima.
    """
    if _en_base():
        from clima import consultas

        d = consultas.serie(estacion, "lluvia_mm", desde, hasta, "hora")
        return (d["inicio"], d["valores"]) if d and d["valores"] else (None, [])
    datos = horario()
    serie = ((datos.get("series") or {}).get(estacion) or {}).get("lluvia_mm")
    if not serie or not datos.get("inicio"):
        return None, []
    inicio = datetime.fromisoformat(datos["inicio"].replace("Z", "+00:00"))
    i = max(0, int((desde - inicio).total_seconds() // 3600))
    j = min(len(serie), int((hasta - inicio).total_seconds() // 3600) + 1)
    if i >= j:
        return None, []
    from datetime import timedelta

    return inicio + timedelta(hours=i), serie[i:j]

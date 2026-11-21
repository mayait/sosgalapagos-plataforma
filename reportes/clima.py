"""Lee el nivel de lluvia que publica /clima (estado.json). Solo lectura.

En el servidor CLIMA_ESTADO es la ruta del archivo; en la Mac, la URL pública.
"""
import json
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen

from django.conf import settings
from django.core.cache import cache


def _leer():
    origen = settings.CLIMA_ESTADO
    if origen.startswith("http"):
        pedido = Request(origen, headers={"User-Agent": "sosgalapagos-plataforma (desarrollo local)"})
        with urlopen(pedido, timeout=8) as respuesta:
            return json.load(respuesta)
    return json.loads(Path(origen).read_text())


def estado():
    datos = cache.get("clima_estado")
    if datos is None:
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

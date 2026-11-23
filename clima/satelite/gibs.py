# SOS Galápagos · © 2026 Universidad San Francisco de Quito (USFQ) · Autor: Julián Maya <jamaya@usfq.edu.ec>
# Licencia Apache 2.0 (ver LICENSE y NOTICE): puede reutilizarse dando crédito.
"""Fondo animado del mapa del satélite: imágenes GeoColor de GOES-East (NOAA) servidas por NASA GIBS.

GeoColor es la imagen del satélite tal cual: en color de día y en infrarrojo de noche, cada 10 min,
con unos 60 min de retraso. Es una IMAGEN, no un dato de lluvia.

El navegador baja las teselas directamente; la plataforma solo le dice qué horas existen. Para eso
pregunta a GIBS por el dominio de tiempo de la capa en las últimas horas (unos cientos de bytes,
no el GetCapabilities completo de varios MB) y lo guarda unos minutos en memoria.

La raíz WMTS (EPSG:3857, «best») va en CLIMA_GIBS_WMTS; aquí no se escribe ningún endpoint.
Solo biblioteca estándar.
"""
from __future__ import annotations

import datetime as dt
import os
import re
import threading
import time
import urllib.parse
import urllib.request

UTC = dt.timezone.utc
UA = "sosgalapagos-clima-satelite/0.1"
CAPA = "GOES-East_ABI_GeoColor"
MATRIZ = "GoogleMapsCompatible_Level7"
ZOOM_MAX = 7
HORAS = 3
CACHE_S = 300
TIMEOUT_S = 5
ATRIBUCION = "Imágenes: NASA GIBS / NOAA GOES-East"

_cache = {"t": 0.0, "datos": None}
_cerrojo = threading.Lock()


def raiz() -> str:
    return os.environ.get("CLIMA_GIBS_WMTS", "").rstrip("/")


def plantilla(r: str) -> str:
    """Plantilla de tesela para Leaflet ({t} = hora ISO; {z}/{y}/{x} como siempre)."""
    return f"{r}/{CAPA}/default/{{t}}/{MATRIZ}/{{z}}/{{y}}/{{x}}.png"


def _iso(t: dt.datetime) -> str:
    return t.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _t(s: str) -> dt.datetime:
    return dt.datetime.fromisoformat(s.strip().replace("Z", "+00:00"))


def _paso(p: str) -> dt.timedelta:
    """Duración ISO sencilla (PT10M, PT1H, P1D)."""
    m = re.fullmatch(r"P(?:(\d+)D)?(?:T(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?)?", p.strip())
    if not m:
        raise ValueError(f"paso desconocido: {p}")
    d, h, mi, s = (int(x or 0) for x in m.groups())
    return dt.timedelta(days=d, hours=h, minutes=mi, seconds=s)


def expandir(dominio: str, desde: dt.datetime, hasta: dt.datetime, limite: int = 200) -> list[str]:
    """Horas ISO de un dominio WMTS («ini/fin/PT10M,ini/fin/PT10M,…» o una hora suelta) entre desde y hasta."""
    salida = set()
    for trozo in re.split(r"[,\s]+", dominio.strip()):
        if not trozo:
            continue
        partes = trozo.split("/")
        ini = _t(partes[0])
        fin = _t(partes[1]) if len(partes) > 1 else ini
        paso = _paso(partes[2]) if len(partes) > 2 else dt.timedelta(minutes=10)
        if fin < desde or ini > hasta or paso <= dt.timedelta(0):
            continue
        if ini < desde:  # salta al primer instante del rango que cae dentro de la ventana
            ini += paso * -(-(desde - ini) // paso)
        t = ini
        while t <= min(fin, hasta) and len(salida) < limite:
            salida.add(_iso(t))
            t += paso
    return sorted(salida)[-limite:]


def dominio_remoto(r: str, desde: dt.datetime, hasta: dt.datetime) -> str:
    q = urllib.parse.urlencode({"SERVICE": "WMTS", "REQUEST": "DescribeDomains", "VERSION": "1.0.0", "LAYER": CAPA,
                                "TILEMATRIXSET": MATRIZ, "TIME": f"{_iso(desde)}/{_iso(hasta)}"}, safe=":/")  # GIBS no acepta «:» ni «/» codificados
    with urllib.request.urlopen(urllib.request.Request(f"{r}/wmts.cgi?{q}", headers={"User-Agent": UA}), timeout=TIMEOUT_S) as resp:
        xml = resp.read(200_000).decode("utf-8", "replace")
    dominios = re.findall(r"<DimensionDomain>.*?<ows:Identifier>\s*time\s*</ows:Identifier>.*?<Domain>(.*?)</Domain>", xml, re.S | re.I)
    return ",".join(dominios)


def capas(ahora: dt.datetime | None = None, pedir=None) -> dict:
    """Lo que necesita el panel para animar el fondo. Nunca falla: sin GIBS, `tiempos` queda vacío."""
    r = raiz()
    base = {"capa": CAPA, "nombre": "GOES-East GeoColor (NOAA)", "zoom_max": ZOOM_MAX, "horas": HORAS,
            "atribucion": ATRIBUCION, "plantilla": plantilla(r) if r else None, "tiempos": [],
            "nota": "Imagen del satélite: en color de día, infrarrojo de noche. No es un dato de lluvia."}
    if not r:
        return {**base, "error": "sin configurar"}
    with _cerrojo:
        if _cache["datos"] is not None and time.time() - _cache["t"] < CACHE_S and pedir is None:
            return _cache["datos"]
        ahora = ahora or dt.datetime.now(UTC)
        desde = ahora - dt.timedelta(hours=HORAS)
        try:
            tiempos = expandir((pedir or dominio_remoto)(r, desde - dt.timedelta(hours=2), ahora), desde - dt.timedelta(hours=2), ahora)
            datos = {**base, "tiempos": tiempos[-(HORAS * 6):], "generado": _iso(ahora)}
        except Exception as e:  # GIBS caído o lento: se conserva lo último bueno
            if _cache["datos"] is not None:
                return {**_cache["datos"], "aviso": "no se pudo actualizar la lista de imágenes"}
            return {**base, "error": f"{type(e).__name__}"}
        _cache.update(t=time.time(), datos=datos)
        return datos

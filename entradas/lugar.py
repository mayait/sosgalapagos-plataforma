# SOS Galápagos · © 2026 Universidad San Francisco de Quito (USFQ) · Autor: Julián Maya <jamaya@usfq.edu.ec>
# Licencia Apache 2.0 (ver LICENSE y NOTICE): puede reutilizarse dando crédito.
"""Sacar un punto del mapa de lo que la persona manda por WhatsApp.

Por orden de confianza: la ubicación de WhatsApp, un enlace de Google Maps (u otro mapa)
y, si no hay más, una dirección o un barrio que esté en el diccionario de zonas.
"""
import re
import urllib.request
from urllib.parse import unquote, urlparse

from .filtro import ENLACE_MAPA, sin_tildes

ANFITRIONES_CORTOS = {"maps.app.goo.gl", "goo.gl"}
# lat,lon tal como aparecen en los enlaces de mapas: @-0.74,-90.31 · ?q=-0.74,-90.31 · !3d-0.74!4d-90.31
PARES = [
    re.compile(r"!3d(-?\d{1,2}\.\d+)!4d(-?\d{1,3}\.\d+)"),
    re.compile(r"[?&](?:q|query|ll|sll|daddr|destination|center)=(?:loc:)?(-?\d{1,2}\.\d+)(?:,|%2C)\s*(-?\d{1,3}\.\d+)", re.I),
    re.compile(r"@(-?\d{1,2}\.\d+),(-?\d{1,3}\.\d+)"),
    re.compile(r"/(?:place|search|dir)/(-?\d{1,2}\.\d+),\s*(-?\d{1,3}\.\d+)"),
]
COORDENADAS = re.compile(r"(?<![\d.])(-?[0-2]\.\d{3,})\s*[,; ]\s*(-?(?:8[89]|9[0-2])\.\d{3,})(?![\d.])")


def en_galapagos(lat, lon):
    return lat is not None and lon is not None and -2 <= lat <= 2 and -92.5 <= lon <= -88.5


def _par(texto):
    for patron in PARES:
        m = patron.search(texto)
        if m and en_galapagos(float(m.group(1)), float(m.group(2))):
            return float(m.group(1)), float(m.group(2))
    return None


def _seguir(url, tope=4):
    """Sigue las redirecciones de un enlace corto de mapas y devuelve la dirección final.

    Solo se piden direcciones de los servicios de mapas conocidos: nunca un enlace cualquiera.
    """
    class SinSeguir(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, *a, **k):
            return None

    abridor = urllib.request.build_opener(SinSeguir)
    for _ in range(tope):
        if not ENLACE_MAPA.match(url):
            return url
        pedido = urllib.request.Request(url, method="GET", headers={"User-Agent": "Mozilla/5.0 (compatible; sosgalapagos)"})
        try:
            with abridor.open(pedido, timeout=8) as r:
                return r.geturl()
        except urllib.error.HTTPError as e:
            destino = e.headers.get("Location")
            if e.code in (301, 302, 303, 307, 308) and destino:
                url = destino
                continue
            return url
        except Exception:
            return url
    return url


def de_enlace(texto, seguir=_seguir):
    """(lat, lon) del primer enlace de mapas del texto, o None."""
    m = ENLACE_MAPA.search(texto or "")
    if not m:
        return None
    url = m.group(0).rstrip(").,;")
    par = _par(unquote(url))
    if par:
        return par
    if urlparse(url).hostname in ANFITRIONES_CORTOS:
        return _par(unquote(seguir(url)))
    return None


def de_coordenadas(texto):
    m = COORDENADAS.search(texto or "")
    if m and en_galapagos(float(m.group(1)), float(m.group(2))):
        return float(m.group(1)), float(m.group(2))
    return None


def de_zona(texto):
    """(zona, lat, lon) de la zona del diccionario que el texto nombra, o None.

    Gana el nombre más largo («La Cascada» antes que «Cascada»). Es una ubicación
    aproximada: el centro del barrio, no el lugar exacto.
    """
    from zonas.models import AliasZona, Zona

    t = f" {sin_tildes(texto)} "
    candidatos = [(z.nombre, z) for z in Zona.objects.all()] + [(a.nombre, a.zona) for a in AliasZona.objects.select_related("zona")]
    mejor = None
    for nombre, zona in candidatos:
        n = sin_tildes(nombre).strip()
        if len(n) >= 5 and re.search(rf"(?<![a-z0-9]){re.escape(n)}(?![a-z0-9])", t) and (not mejor or len(n) > len(mejor[0])):
            mejor = (n, zona)
    if not mejor:
        return None
    centro = mejor[1].geometria.point_on_surface
    return mejor[1], centro.y, centro.x

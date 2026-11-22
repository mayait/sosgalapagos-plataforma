"""Weather Underground: estaciones particulares. Se lee la página pública de cada estación.

La página trae el valor actual y la lluvia acumulada del día: se guarda el acumulado y la
lluvia de cada intervalo por diferencia (ver acumulado.py). La «Key» de la estación es la
contraseña de subida y no sirve para leer.

En el entorno: CLIMA_WU_PAGINA (raíz de la página pública) y CLIMA_WU_ESTACIONES
("identificador_de_la_estación:código[,…]").
Casa Marina se publica con su nombre y ubicación exacta: lo autorizó Julián el 6-nov-2026.
"""
import datetime as dt
import os
import re
import ssl
import urllib.request

from . import base
from .acumulado import MAX_EDAD_S, anterior, lluvia_por_diferencia

FUENTE = "wunderground"
ESTACIONES = {"casa_marina": ("Puerto Ayora (Casa Marina)", "Santa Cruz", -0.746458, -90.312935, 3)}  # código: (nombre, isla, lat, lon, altitud)
# Conversión según la unidad con que la página muestre cada dato:
# m = métrico (°C, km/h, hPa, mm), e = inglés (°F, mph, inHg, in), h = híbrido (°C, mph, hPa, mm)
UNIDADES = {
    "temp": {"m": lambda x: x, "h": lambda x: x, "e": lambda x: (x - 32) / 1.8},
    "viento": {"m": lambda x: x / 3.6, "h": lambda x: x * 0.44704, "e": lambda x: x * 0.44704},
    "presion": {"m": lambda x: x, "h": lambda x: x, "e": lambda x: x * 33.8639},
    "lluvia": {"m": lambda x: x, "h": lambda x: x, "e": lambda x: x * 25.4},
}
CAMPOS = (("lluvia_dia_mm", "rain", "precip-total", "lluvia"), ("temp_c", "temp", "temp", "temp"), ("hr_pct", "humidity", "humidity", None),
          ("presion_hpa", "pressure", "pressure", "presion"), ("viento_ms", "wind", "wind-speed", "viento"))


def _configuradas():
    salida = {}
    for par in os.environ.get("CLIMA_WU_ESTACIONES", "").split(","):
        if ":" in par:
            identificador, cod = par.strip().split(":", 1)
            if cod in ESTACIONES:
                salida[identificador] = cod
    if not salida:
        raise RuntimeError("Falta CLIMA_WU_ESTACIONES en el entorno")
    return salida


def _atributos(pagina, nombre):
    m = re.search(rf"<{nombre}-widget-view\b([^>]*)>", pagina)
    return dict(re.findall(r'data-([a-z-]+)="([^"]*)"', m.group(1))) if m else {}


def leer(pagina):
    """Lectura actual de la página: {ts, lluvia_dia_mm, temp_c, hr_pct, presion_hpa, viento_ms}, o None."""
    m = re.search(r'data-obs-time-utc="([A-Z][a-z]{2} [A-Z][a-z]{2} \d{2} \d{4} \d{2}:\d{2}:\d{2} GMT[+-]\d{4})', pagina)
    if not m:
        return None
    salida = {"ts": dt.datetime.strptime(m.group(1), "%a %b %d %Y %H:%M:%S GMT%z").astimezone(base.UTC)}
    for clave, parte, atributo, conversion in CAMPOS:
        w = _atributos(pagina, parte)
        if w.get("status") != "connected":
            continue
        try:
            valor = float(w[atributo])
        except (KeyError, ValueError):
            continue
        if conversion:
            f = UNIDADES[conversion].get(w.get("unit"))
            if f is None:
                continue  # unidad desconocida: mejor sin dato que un dato mal convertido
            valor = f(valor)
        salida[clave] = round(valor, 2)
    return salida


def _bajar(url):
    pedido = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (sosgalapagos-clima)"})
    # La página rechaza (403) la lista de cifrados del Python de la imagen; con la de OpenSSL por defecto responde.
    tls = ssl.create_default_context()
    tls.set_ciphers("DEFAULT")
    with urllib.request.urlopen(pedido, timeout=60, context=tls) as r:
        return r.read().decode("utf-8", "replace")


def recoger(ahora=None):
    ahora = ahora or dt.datetime.now(base.UTC)
    raiz = base.endpoint("CLIMA_WU_PAGINA")
    filas, activas, errores = [], 0, []
    for identificador, cod in _configuradas().items():
        try:
            d = leer(_bajar(f"{raiz}/{identificador}"))
        except Exception as e:  # una estación caída no detiene a las demás
            errores.append(f"{cod}: {e}")
            continue
        if not d or "lluvia_dia_mm" not in d:
            continue  # desconectada o sin pluviómetro
        t = d["ts"]
        if (ahora - t).total_seconds() > MAX_EDAD_S:
            continue  # inactiva: no se registra ni se publica
        activas += 1
        base.estacion(FUENTE, cod, *ESTACIONES[cod], "Weather Underground")
        if base.existe(FUENTE, cod, en=t):
            continue  # sin dato nuevo
        acumulado = d["lluvia_dia_mm"]
        mm = lluvia_por_diferencia(t, acumulado, anterior(FUENTE, cod, t))
        filas.append((cod, "lluvia_dia_acum_mm", t, acumulado))
        if mm is not None:
            filas.append((cod, "lluvia_mm", t, mm))
        filas += [(cod, v, t, d[v]) for v in ("temp_c", "hr_pct", "presion_hpa", "viento_ms") if v in d]
    if not activas and errores:
        raise RuntimeError("; ".join(errores)[:400])
    return base.guardar(FUENTE, filas)

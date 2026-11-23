# SOS Galápagos · © 2026 Universidad San Francisco de Quito (USFQ) · Autor: Julián Maya <jamaya@usfq.edu.ec>
# Licencia Apache 2.0 (ver LICENSE y NOTICE): puede reutilizarse dando crédito.
"""WeatherLink: estaciones particulares con mapa público.

El mapa solo da el valor actual y la lluvia acumulada del día. Se guarda el acumulado tal
cual (lluvia_dia_acum_mm) y la lluvia de cada intervalo por diferencia (ver acumulado.py).

Estaciones: CLIMA_WEATHERLINK_ESTACIONES = "identificador_del_mapa:código[,…]". Los
identificadores no van en el repositorio. La estación de Erna, en Puerto Ayora, se publica
con su nombre y ubicación exacta: lo autorizó Julián el 2-nov-2026.

Respaldo de la estación de Erna: la misma consola transmite por CWOP y NOAA MADIS la
redistribuye. Si WeatherLink no trae sus datos hace más de 30 minutos, se guarda una fila de
respaldo por hora, solo para horas que WeatherLink no cubre.
"""
import datetime as dt
import os

from . import base
from .acumulado import MAX_EDAD_S, MAX_MM_H, anterior, lluvia_por_diferencia

FUENTE = "weatherlink"
ESTACIONES = {  # código: (nombre, isla, lat, lon, altitud)
    "pa_weatherlink": ("Puerto Ayora (Erna)", "Santa Cruz", -0.753368, -90.311995, 10),
    # Sensores «GALAP» de Puerto Baquerizo Moreno: inactivos el 2-nov-2026. Entran solos al panel cuando vuelvan a transmitir.
    "galap1": ("Puerto Baquerizo (GALAP1)", "San Cristóbal", -0.902, -89.608, 10),
    "galap2": ("Puerto Baquerizo (GALAP2)", "San Cristóbal", -0.902, -89.608, 10),
    "galap3": ("Puerto Baquerizo (GALAP3)", "San Cristóbal", -0.902, -89.608, 10),
    "galap4": ("Puerto Baquerizo (GALAP4)", "San Cristóbal", -0.902, -89.608, 10),
    "galap5": ("Puerto Baquerizo (GALAP5)", "San Cristóbal", -0.902, -89.608, 10),
}
ERNA = {"codigo": "pa_weatherlink", "id": "madis-D5750", "lat": -0.753, "lon": -90.312}


def _configuradas():
    salida = {}
    for par in os.environ.get("CLIMA_WEATHERLINK_ESTACIONES", "").split(","):
        if ":" in par:
            identificador, cod = par.strip().split(":", 1)
            if cod in ESTACIONES:
                salida[identificador] = cod
    if not salida:
        raise RuntimeError("Falta CLIMA_WEATHERLINK_ESTACIONES en el entorno")
    return salida


def leer(cod, d, ahora):
    """De la respuesta del mapa a (hora de la lectura, {variable: valor}), o None si la estación está inactiva."""
    try:
        edad = ahora.timestamp() - int(d.get("lastTimestamp"))
    except (TypeError, ValueError):
        return None
    if edad > MAX_EDAD_S or d.get("dailyRain") in (None, "", "--"):
        return None
    num = lambda k: None if d.get(k) in (None, "", "--") else float(d[k])  # noqa: E731
    # Segundos en :00: las filas con segundos :30 son las de respaldo por hora.
    t = dt.datetime.fromtimestamp(int(d["lastTimestamp"]), base.UTC).replace(second=0)
    valores = {"lluvia_dia_acum_mm": round(num("dailyRain") * (25.4 if d.get("rainUnit", "in") == "in" else 1), 2)}
    if num("temperature") is not None:
        valores["temp_c"] = round((num("temperature") - 32) / 1.8 if "F" in d.get("temperatureUnit", "F") else num("temperature"), 2)
    if num("humidity") is not None:
        valores["hr_pct"] = num("humidity")
    if num("barometer") is not None:
        valores["presion_hpa"] = round(num("barometer") * (33.8639 if "in" in d.get("barometerUnit", "in") else 1), 1)
    if num("windSpeed") is not None:
        valores["viento_ms"] = round(num("windSpeed") * (0.44704 if "mph" in d.get("windSpeedUnit", "mph") else 1), 1)
    return t, valores


def recoger(ahora=None):
    ahora = ahora or dt.datetime.now(base.UTC)
    api = base.endpoint("CLIMA_WEATHERLINK_API")
    filas, activas, errores = [], 0, []
    for identificador, cod in _configuradas().items():
        try:
            lectura = leer(cod, base.http_json(f"{api}/{identificador}"), ahora)
        except Exception as e:  # una estación caída no detiene a las demás
            errores.append(f"{cod}: {e}")
            continue
        if not lectura:
            continue  # inactiva: no se registra ni se publica
        activas += 1
        base.estacion(FUENTE, cod, *ESTACIONES[cod], "WeatherLink")
        t, valores = lectura
        if base.existe(FUENTE, cod, en=t):
            continue  # sin dato nuevo
        mm = lluvia_por_diferencia(t, valores["lluvia_dia_acum_mm"], anterior(FUENTE, cod, t))
        if mm is not None:
            valores["lluvia_mm"] = mm
        filas += [(cod, variable, t, valor) for variable, valor in valores.items()]
    n = base.guardar(FUENTE, filas)
    try:
        n += respaldo_erna(ahora)
    except Exception as e:  # el respaldo nunca tumba la fuente principal
        errores.append(f"respaldo de Erna: {e}")
    if not activas and errores:
        raise RuntimeError("; ".join(errores)[:400])
    return n


def respaldo_erna(ahora=None):
    if not os.environ.get("CLIMA_RESPALDO_ERNA_API"):
        return 0
    ahora = ahora or dt.datetime.now(base.UTC)
    cod = ERNA["codigo"]
    ultimo = base.ultimo(FUENTE, cod, "lluvia_mm", de_cinco_min=True)
    if ultimo and ahora - ultimo < dt.timedelta(minutes=30):
        return 0  # WeatherLink está al día
    d = base.http_json(f"{base.endpoint('CLIMA_RESPALDO_ERNA_API')}/{ERNA['lat']}/{ERNA['lon']}")
    e = next((x for x in (d if isinstance(d, list) else []) if x.get("id") == ERNA["id"]), None)
    if not e or e.get("minAgo") is None or e["minAgo"] > 30 or e.get("precip_time") != 1 or e.get("precip") is None:
        return 0
    t = (ahora - dt.timedelta(minutes=int(e["minAgo"]))).replace(second=0, microsecond=0)
    inicio = (t - dt.timedelta(hours=1)).replace(second=base.HORARIO_SEG)
    # Una fila por hora como máximo, y nunca encima de datos de WeatherLink.
    if base.existe(FUENTE, cod, "lluvia_mm", desde=inicio - dt.timedelta(minutes=55), hasta=t, desde_excluida=True):
        return 0
    mm = round(float(e["precip"]), 2)
    filas = [(cod, "lluvia_mm", inicio, None if mm > MAX_MM_H else mm)]
    if e.get("temp") is not None:
        filas.append((cod, "temp_c", t, round(float(e["temp"]), 2)))
    if e.get("rh") is not None:
        filas.append((cod, "hr_pct", t, float(e["rh"])))
    return base.guardar(FUENTE, filas)

"""Reportes METAR de los aeropuertos de Baltra y San Cristóbal. No miden lluvia: dan un código."""
import datetime as dt
import urllib.parse

from . import base

FUENTE = "metar"
ESTACIONES = {"SEGS": ("Aeropuerto Seymour (Baltra)", "Baltra", -0.4539, -90.2658, 51),
              "SEST": ("Aeropuerto San Cristóbal", "San Cristóbal", -0.9100, -89.6170, 18)}


def codigo_lluvia(tiempo_presente):
    """0 sin lluvia, 1 llovizna o lluvia débil, 2 moderada, 3 fuerte o tormenta."""
    wx = tiempo_presente or ""
    if not any(k in wx for k in ("RA", "DZ", "TS", "SH")):
        return 0
    if "+" in wx or "TS" in wx:
        return 3
    if "-" in wx or ("DZ" in wx and "RA" not in wx):
        return 1
    return 2


def filas_de(reportes):
    filas = []
    for m in reportes:
        cod = m.get("icaoId")
        if cod not in ESTACIONES:
            continue
        t = dt.datetime.fromtimestamp(m["obsTime"], base.UTC)
        if m.get("temp") is not None:
            filas.append((cod, "temp_c", t, float(m["temp"])))
        if m.get("altim") is not None:
            filas.append((cod, "presion_hpa", t, float(m["altim"])))
        if m.get("wspd") is not None:
            filas.append((cod, "viento_ms", t, round(float(m["wspd"]) * 0.5144, 1)))
        filas.append((cod, "lluvia_codigo", t, codigo_lluvia(m.get("wxString"))))
    return filas


def recoger():
    q = urllib.parse.urlencode({"ids": ",".join(ESTACIONES), "format": "json", "hours": 3})
    filas = filas_de(base.http_json(f"{base.endpoint('CLIMA_METAR_API')}?{q}"))
    for cod, (nombre, isla, lat, lon, altitud) in ESTACIONES.items():
        base.estacion(FUENTE, cod, nombre, isla, lat, lon, altitud, "Aeropuertos (METAR)")
    return base.guardar(FUENTE, filas)

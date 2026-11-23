# SOS Galápagos · © 2026 Universidad San Francisco de Quito (USFQ) · Autor: Julián Maya <jamaya@usfq.edu.ec>
# Licencia Apache 2.0 (ver LICENSE y NOTICE): puede reutilizarse dando crédito.
"""Mareógrafos de la red IOC: nivel del mar medido en Puerto Ayora y Baltra.

Se usa siempre el mismo radar por estación («ras», con el mismo cero que la serie UHSLC; el
«rad» de Puerto Ayora tiene otro cero, +4,9 m) y se resta el desfase IOC−UHSLC, así que
`nivel_mar_m` queda en el cero UHSLC y se puede comparar con la predicción de mareas.
Los desfases están en clima/datos/mareas_prediccion.json.
"""
import datetime as dt
import statistics
import urllib.parse

from . import base

FUENTE = "ioc"
ESTACIONES = {"sant": ("Mareógrafo Puerto Ayora", "Santa Cruz", -0.7525, -90.3117),
              "balt": ("Mareógrafo Baltra", "Baltra", -0.4350, -90.2833)}
SENSORES = ("ras", "rad")  # orden de preferencia


def desfases():
    from ..mareas import prediccion

    return {cod: (e.get("ioc") or {}) for cod, e in (prediccion() or {}).get("estaciones", {}).items()}


def filas_de(cod, datos, desfase):
    """El sensor preferido que esté vivo (no congelado) y tenga desfase conocido."""
    por_sensor = {}
    for x in datos:
        if x.get("sensor") in SENSORES and x.get("slevel") is not None:
            por_sensor.setdefault(x["sensor"], []).append(x)
    for sensor in SENSORES:
        xs, des = por_sensor.get(sensor, []), (desfase or {}).get(sensor)
        if len(xs) > 5 and statistics.pstdev([x["slevel"] for x in xs]) > 0.002 and des:
            resta = des["desfase_cm"] / 100
            return [(cod, "nivel_mar_m", dt.datetime.fromisoformat(x["stime"].strip()).replace(tzinfo=base.UTC), round(float(x["slevel"]) - resta, 3)) for x in xs]
    return []


def recoger():
    api = base.endpoint("CLIMA_IOC_API")
    fin, todos, filas = dt.datetime.now(base.UTC), desfases(), []
    for cod, (nombre, isla, lat, lon) in ESTACIONES.items():
        base.estacion(FUENTE, cod, nombre, isla, lat, lon, 0, "IOC")
        inicio, ultimo = fin - dt.timedelta(days=3), base.ultimo(FUENTE, cod)
        if ultimo:
            inicio = max(inicio, ultimo - dt.timedelta(minutes=30))
        q = urllib.parse.urlencode({"query": "data", "code": cod, "format": "json",
                                    "timestart": inicio.strftime("%Y-%m-%dT%H:%M:%S"), "timestop": fin.strftime("%Y-%m-%dT%H:%M:%S")})
        filas += filas_de(cod, base.http_json(f"{api}?{q}", espera=120), todos.get(cod))
    return base.guardar(FUENTE, filas)

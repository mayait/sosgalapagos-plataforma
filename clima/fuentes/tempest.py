# SOS Galápagos · © 2026 Universidad San Francisco de Quito (USFQ) · Autor: Julián Maya <jamaya@usfq.edu.ec>
# Todos los derechos reservados. Usar, copiar, modificar o derivar de este código requiere permiso escrito del autor (ver LICENSE).
"""Tempest (WeatherFlow): estación particular de Punta Estrada.

API oficial con el token personal de solo lectura que genera el dueño de la estación.
En el entorno: CLIMA_TEMPEST_API, CLIMA_TEMPEST_TOKEN y CLIMA_TEMPEST_EQUIPOS
("identificador_del_equipo:código[,…]").

Da un registro por minuto: [0] época, [2] viento medio m/s, [6] presión hPa, [7] temperatura °C,
[8] humedad %, [12] lluvia del minuto mm. Se agrupan en bloques de 5 minutos, como las demás fuentes.
"""
import datetime as dt
import os
import urllib.parse

from . import base

FUENTE = "tempest"
ESTACIONES = {"punta_estrada": ("Punta Estrada", "Santa Cruz", -0.7499, -90.31081, 8)}  # código: (nombre, isla, lat, lon, altitud)


def _equipos():
    pares = [p.split(":", 1) for p in os.environ.get("CLIMA_TEMPEST_EQUIPOS", "").split(",") if ":" in p]
    if not pares:
        raise RuntimeError("Falta CLIMA_TEMPEST_EQUIPOS en el entorno")
    return [(equipo.strip(), cod) for equipo, cod in pares if cod in ESTACIONES]


def filas_de(cod, registros, ahora):
    """Registros de un minuto → filas en bloques de 5 minutos. El bloque en curso se deja para la próxima corrida."""
    bloques = {}
    for o in registros:
        if not isinstance(o, list) or len(o) < 13 or o[0] is None:
            continue
        t = dt.datetime.fromtimestamp(int(o[0]), base.UTC)
        g = bloques.setdefault(t.replace(minute=t.minute - t.minute % 5, second=0), {"lluvia": 0.0, "temp": [], "hr": [], "p": [], "v": []})
        if o[12] is not None:
            g["lluvia"] += float(o[12])
        for k, i in (("v", 2), ("p", 6), ("temp", 7), ("hr", 8)):
            if o[i] is not None:
                g[k].append(float(o[i]))
    filas = []
    for bloque, g in bloques.items():
        if bloque + dt.timedelta(minutes=5) > ahora:
            continue
        filas.append((cod, "lluvia_mm", bloque, round(g["lluvia"], 2)))
        for k, variable in (("temp", "temp_c"), ("hr", "hr_pct"), ("p", "presion_hpa"), ("v", "viento_ms")):
            if g[k]:
                filas.append((cod, variable, bloque, round(sum(g[k]) / len(g[k]), 2)))
    return filas


def _bajar(equipo, cod, desde, hasta):
    """Baja el tramo en trozos de un día."""
    api, token = base.endpoint("CLIMA_TEMPEST_API"), base.endpoint("CLIMA_TEMPEST_TOKEN")
    base.estacion(FUENTE, cod, *ESTACIONES[cod], "Tempest")
    registros, t0 = [], desde
    while t0 < hasta:
        t1 = min(hasta, t0 + dt.timedelta(days=1))
        q = urllib.parse.urlencode({"token": token, "time_start": int(t0.timestamp()), "time_end": int(t1.timestamp())})
        d = base.http_json(f"{api}/observations/device/{equipo}?{q}", espera=90)
        obs = d.get("obs") or []
        if not isinstance(obs, list):
            raise ValueError(f"respuesta inesperada de {cod}: {str(d)[:200]}")
        registros += obs
        t0 = t1
    return filas_de(cod, registros, dt.datetime.now(base.UTC))


def recoger(desde=None):
    """Desde el último bloque guardado (para rellenar cortes), como máximo 3 días atrás. Con `desde`, una carga histórica."""
    ahora, filas = dt.datetime.now(base.UTC), []
    for equipo, cod in _equipos():
        inicio = desde
        if inicio is None:
            inicio, ultimo = ahora - dt.timedelta(days=3), base.ultimo(FUENTE, cod)
            if ultimo:
                inicio = max(inicio, ultimo - dt.timedelta(minutes=10))
        filas += _bajar(equipo, cod, inicio, ahora)
    return base.guardar(FUENTE, filas)

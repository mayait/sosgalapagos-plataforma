"""Ambient Weather: estaciones particulares con panel público que su dueño comparte con un enlace.

En el entorno: CLIMA_AMBIENT_API y CLIMA_AMBIENT_ESTACIONES ("clave_del_enlace:código[,…]").

Da un registro cada 5 minutos, con historia desde que se instaló la estación. La lluvia llega
como acumulado (pulgadas) y el intervalo se calcula por diferencia; temperatura en °F, presión
en inHg, viento en mph. La respuesta trae también la clave de subida y la dirección IP de la
estación: no se guardan.

Nombre, ubicación y cita de cada estación: publicados con autorización de Julián (12-nov-2026).
"""
import datetime as dt
import os
import time
import urllib.parse

from . import base
from .acumulado import HUECO_MAX_MIN, MAX_EDAD_S, MAX_MM_H

FUENTE = "ambient"
ESTACIONES = {  # código: (nombre, isla, lat, lon, altitud); coordenadas redondeadas a ~100 m
    "evolucion": ("Evolución (Puerto Ayora)", "Santa Cruz", -0.747, -90.315, 10),
    "miconia": ("Miconia (parte alta)", "Santa Cruz", -0.6663, -90.3764, 422),
    "manzanillo_espol": ("El Manzanillo – ESPOL", "Santa Cruz", -0.6965, -90.4020, 169),
    "epmapasc_espol": ("EPMAPASC – ESPOL (Puerto Ayora)", "Santa Cruz", -0.7417, -90.3204, 22),
}


def _configuradas():
    pares = [p.strip().split(":", 1) for p in os.environ.get("CLIMA_AMBIENT_ESTACIONES", "").split(",") if ":" in p]
    if not pares:
        raise RuntimeError("Falta CLIMA_AMBIENT_ESTACIONES en el entorno")
    return [(clave, cod) for clave, cod in pares if cod in ESTACIONES]


def filas_de(cod, registros):
    """Registros de 5 minutos, ordenados → filas. La lluvia de cada uno es la diferencia con el anterior."""
    filas, previo = [], None
    num = lambda r, k: None if r.get(k) is None else float(r[k])  # noqa: E731
    for r in registros:
        t = dt.datetime.fromtimestamp(r["dateutc"] / 1000, base.UTC)
        bloque = t - dt.timedelta(minutes=5)  # etiqueta = inicio del intervalo, como las demás fuentes
        bloque = bloque.replace(minute=bloque.minute - bloque.minute % 5, second=0, microsecond=0)
        # Se usa la diferencia del acumulado anual: el diario se reinicia a medianoche, pero no siempre
        # en el mismo registro. El anual solo se reinicia el 1 de enero; ahí se usa el diario.
        acumulado = (num(r, "yearlyrainin"), num(r, "dailyrainin"))
        if previo is not None and None not in acumulado:
            t0, (anual0, dia0) = previo
            horas = max((t - t0).total_seconds() / 3600, 1 / 60)
            incremento = acumulado[0] - anual0 if acumulado[0] >= anual0 else (acumulado[1] - dia0 if acumulado[1] >= dia0 else acumulado[1])
            mm = round(incremento * 25.4, 2)
            if horas * 60 <= HUECO_MAX_MIN:  # tras un corte no se atribuye todo el hueco a un registro
                filas.append((cod, "lluvia_mm", bloque, None if mm > max(10, MAX_MM_H * horas) else mm))
        if None not in acumulado:
            previo = (t, acumulado)
        if num(r, "tempf") is not None:
            filas.append((cod, "temp_c", bloque, round((num(r, "tempf") - 32) / 1.8, 2)))
        if num(r, "humidity") is not None:
            filas.append((cod, "hr_pct", bloque, num(r, "humidity")))
        if num(r, "baromabsin") is not None:
            filas.append((cod, "presion_hpa", bloque, round(num(r, "baromabsin") * 33.8639, 1)))
        if num(r, "windspeedmph") is not None:
            filas.append((cod, "viento_ms", bloque, round(num(r, "windspeedmph") * 0.44704, 1)))
    return filas


def _bajar(clave, cod, desde, hasta, pausa=0.0):
    api = base.endpoint("CLIMA_AMBIENT_API")
    equipos = (base.http_json(f"{api}/devices?{urllib.parse.urlencode({'public.slug': clave})}").get("data")) or []
    if not equipos or not equipos[0].get("macAddress"):
        raise ValueError("el enlace público no devuelve ningún equipo (¿dejó de compartirse?)")
    equipo = equipos[0]
    ultimo = (equipo.get("lastData") or {}).get("dateutc")
    if not ultimo or dt.datetime.now(base.UTC).timestamp() - ultimo / 1000 > MAX_EDAD_S:
        return []  # inactiva: no se registra ni se publica
    base.estacion(FUENTE, cod, *ESTACIONES[cod], "Ambient Weather")
    registros, t0 = {}, desde
    while t0 < hasta:
        t1 = min(hasta, t0 + dt.timedelta(days=1))
        q = urllib.parse.urlencode({"macAddress": equipo["macAddress"], "res": 5, "start": int(t0.timestamp() * 1000), "end": int(t1.timestamp() * 1000)})
        d = base.http_json(f"{api}/device-data?{q}", espera=90)
        datos = d.get("data") if isinstance(d, dict) else None
        if not isinstance(datos, list):
            raise ValueError(f"respuesta inesperada de {cod}: {str(d)[:200]}")
        for r in datos:
            if isinstance(r, dict) and isinstance(r.get("dateutc"), (int, float)):
                registros[int(r["dateutc"])] = r
        t0 = t1
        time.sleep(pausa)
    return filas_de(cod, [registros[k] for k in sorted(registros)])


def recoger(desde=None):
    """Desde el último bloque guardado, como máximo 3 días atrás. Con `desde`, una carga histórica (con pausas)."""
    ahora, total = dt.datetime.now(base.UTC), 0
    for clave, cod in _configuradas():
        inicio = desde
        if inicio is None:
            inicio, ultimo = ahora - dt.timedelta(days=3), base.ultimo(FUENTE, cod)
            if ultimo:
                inicio = max(inicio, ultimo - dt.timedelta(minutes=10))
        total += base.guardar(FUENTE, _bajar(clave, cod, inicio, ahora, pausa=0.5 if desde else 0.0))
    return total

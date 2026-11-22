"""Las fuentes de clima: un módulo por fuente, todos con `recoger()`.

`recolectar()` corre las que toca en el ciclo de cinco minutos y anota cómo fue cada una en
Corrida. Esas filas no son solo un registro: la regla del nivel de lluvia distingue «la
estación está callada» de «no pudimos preguntarle» mirándolas.

Fuera de este ciclo quedan:
- IERSE, que entra por el relevo desde Ecuador (ver ierse.py), salvo con CLIMA_IERSE_DIRECTO=1;
- el satélite (clima/satelite/), que corre en su propio proceso porque tarda minutos;
- el INOCAR, Stormglass y los boletines, que tienen su propio ritmo (clima/tareas.py).
"""
import datetime as dt
import logging
import os
import time

from django.db import transaction

from . import ambient, base, gsc, ierse, inamhi, ioc, mar_modelo, metar, modelos, tempest, weatherlink, wunderground

registro = logging.getLogger(__name__)

# nombre → (módulo, variables del entorno sin las que no puede correr)
REGISTRO = {
    "gsc": (gsc, ("CLIMA_GSC_WS", "CLIMA_GSC_ORIGEN")),
    "inamhi": (inamhi, ("CLIMA_INAMHI_API",)),
    "ioc": (ioc, ("CLIMA_IOC_API",)),
    "metar": (metar, ("CLIMA_METAR_API",)),
    "weatherlink": (weatherlink, ("CLIMA_WEATHERLINK_API", "CLIMA_WEATHERLINK_ESTACIONES")),
    "tempest": (tempest, ("CLIMA_TEMPEST_API", "CLIMA_TEMPEST_TOKEN", "CLIMA_TEMPEST_EQUIPOS")),
    "ambient": (ambient, ("CLIMA_AMBIENT_API", "CLIMA_AMBIENT_ESTACIONES")),
    "wunderground": (wunderground, ("CLIMA_WU_PAGINA", "CLIMA_WU_ESTACIONES")),
    "mar_modelo": (mar_modelo, ("CLIMA_OPENMETEO_MARINE_API",)),
    "pronostico": (modelos, ("CLIMA_OPENMETEO_FORECAST_API", "CLIMA_OPENMETEO_ENSEMBLE_API")),
    "ierse": (ierse, ("CLIMA_IERSE_API", "CLIMA_IERSE_DIRECTO")),
}
# Nombre con que se muestra cada fuente en el panel y en las descargas.
OPERADOR = {"ierse": "IERSE-WSN", "gsc": "GSC-USFQ", "inamhi": "INAMHI", "ioc": "IOC", "metar": "Aeropuertos (METAR)",
            "weatherlink": "WeatherLink", "tempest": "Tempest", "ambient": "Ambient Weather", "wunderground": "Weather Underground",
            "mar_modelo": "Modelo de nivel del mar", "pronostico": "Pronóstico (modelos)", "goes": "Satélite GOES-19", "fcd": "Fundación Charles Darwin"}
# Fuentes con estaciones que miden: las que entran en las descargas públicas.
DE_ESTACION = ("ierse", "gsc", "inamhi", "ioc", "metar", "weatherlink", "tempest", "ambient", "wunderground")


def activas():
    """Las fuentes que tienen su configuración en el entorno."""
    return [nombre for nombre, (_, variables) in REGISTRO.items() if all(os.environ.get(v) for v in variables)]


def anotar(fuente, t0, registros=0, error=""):
    from ..models import Corrida

    Corrida.objects.update_or_create(fuente=fuente, ts=dt.datetime.now(dt.timezone.utc).replace(microsecond=0),
                                     defaults={"ok": not error, "registros": registros, "segundos": round(time.monotonic() - t0, 1), "error": str(error)[:500]})


def recolectar(nombres=None):
    """Corre cada fuente y anota su corrida. Una fuente caída no detiene a las demás. Devuelve {fuente: registros o error}."""
    salida = {}
    for nombre in (nombres if nombres is not None else activas()):
        if nombre not in REGISTRO:
            continue
        t0 = time.monotonic()
        try:
            with transaction.atomic():
                n = REGISTRO[nombre][0].recoger()
            anotar(nombre, t0, n)
            salida[nombre] = n
        except Exception as e:
            registro.exception("Falló la fuente %s", nombre)
            anotar(nombre, t0, error=f"{type(e).__name__}: {e}")
            salida[nombre] = f"error: {type(e).__name__}"
    if salida:
        # Las fuentes rellenan hasta tres días atrás: se rehacen los resúmenes por hora de ese tramo.
        with transaction.atomic():
            base.resumir(dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=3))
    return salida

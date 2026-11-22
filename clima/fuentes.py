"""Recoger las fuentes de clima desde esta aplicación (etapa 5 de docs/plan-clima.md).

Las funciones que hablan con cada fuente son las del recolector anterior (clima/anterior/),
que escriben en PostgreSQL a través de la conexión de compatibilidad. Aquí solo se decide
cuáles corren y se anota cómo fue cada una.

CLIMA_FUENTES_NATIVAS dice qué fuentes recoge esta aplicación. Las demás (hoy IERSE, que entra
por el puente desde una Mac en Ecuador, y el satélite) se siguen copiando de la base anterior.
"""
import logging
import time
from datetime import datetime, timedelta, timezone

from django.conf import settings
from django.db import connection, transaction

from .compat import Conexion, modulos

registro = logging.getLogger(__name__)


def nativas():
    return list(settings.CLIMA_FUENTES_NATIVAS)


def recolectar(nombres=None):
    """Corre cada fuente y anota su corrida. Una fuente caída no detiene a las demás. Devuelve {fuente: registros o error}."""
    from .models import Corrida
    from .sincronizar import _resumir

    recolector = modulos()
    con, salida = Conexion(), {}
    for nombre in (nombres if nombres is not None else nativas()):
        funcion = recolector.FUENTES.get(nombre)
        if not funcion:
            continue
        t0, ahora = time.monotonic(), datetime.now(timezone.utc).replace(microsecond=0)
        try:
            with transaction.atomic():
                n = funcion(con)
            Corrida.objects.update_or_create(fuente=nombre, ts=ahora, defaults={"ok": True, "registros": n, "segundos": round(time.monotonic() - t0, 1), "error": ""})
            salida[nombre] = n
        except Exception as e:
            registro.exception("Falló la fuente %s", nombre)
            Corrida.objects.update_or_create(fuente=nombre, ts=ahora, defaults={"ok": False, "registros": 0, "segundos": round(time.monotonic() - t0, 1), "error": f"{type(e).__name__}: {e}"[:500]})
            salida[nombre] = f"error: {type(e).__name__}"
    if salida:
        # Las fuentes rellenan hasta tres días atrás: se rehacen los resúmenes por hora de ese tramo.
        with transaction.atomic(), connection.cursor() as c:
            _resumir(c, datetime.now(timezone.utc) - timedelta(days=3))
    return salida

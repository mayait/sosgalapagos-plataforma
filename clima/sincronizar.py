"""Copia las mediciones de la base del recolector anterior (SQLite) a PostgreSQL.

Se corre cada cinco minutos. Cada vez relee los últimos días completos, no solo lo nuevo:
el recolector corrige hacia atrás (rellena huecos, recalcula la lluvia por diferencia,
cambia filas horarias por las de cinco minutos), y aquí tiene que quedar igual.

No toca la base de origen: la abre en modo de solo lectura.
"""
import logging
import sqlite3
import time
from datetime import datetime, timedelta, timezone

from django.conf import settings
from django.db import connection, transaction

from .models import Sincronizacion

registro = logging.getLogger(__name__)

# Variables que se resumen por hora. La lluvia se suma; lo demás se promedia.
RESUMIDAS = ("lluvia_mm", "temp_c", "hr_pct", "presion_hpa", "viento_ms", "nivel_mar_m", "rad_wm2")


def _origen(ruta=None):
    con = sqlite3.connect(f"file:{ruta or settings.CLIMA_SQLITE}?mode=ro", uri=True, timeout=60)
    con.execute("PRAGMA query_only = 1")
    return con


def _iso(ts):
    """Las horas de origen son texto ISO en UTC; algunas corridas no llevan la «Z»."""
    return ts if ts.endswith("Z") or "+" in ts[10:] else ts + "Z"


def sincronizar(dias=3, completa=False, ruta=None):
    """Devuelve la fila de Sincronizacion con lo que hizo."""
    t0 = time.monotonic()
    fila = Sincronizacion(completa=completa)
    try:
        with transaction.atomic():
            _copiar(fila, None if completa else datetime.now(timezone.utc) - timedelta(days=dias), ruta)
    except Exception as error:  # la base de origen ocupada, el archivo ausente…
        registro.exception("No se pudo sincronizar el clima")
        fila.error = f"{type(error).__name__}: {error}"[:500]
    fila.segundos = round(time.monotonic() - t0, 2)
    fila.save()
    return fila


def _copiar(fila, desde, ruta):
    origen = _origen(ruta)
    try:
        with connection.cursor() as c:
            # ── Estaciones ────────────────────────────────────────────────────
            for fuente, codigo, nombre, isla, lat, lon, altitud, operador in origen.execute(
                "SELECT fuente, estacion, nombre, isla, lat, lon, altitud_m, operador FROM estaciones"
            ):
                c.execute(
                    """INSERT INTO clima_estacion (fuente, codigo, nombre, isla, punto, altitud_m, operador)
                       VALUES (%s, %s, %s, %s, CASE WHEN %s::float8 IS NULL THEN NULL ELSE ST_SetSRID(ST_MakePoint(%s, %s), 4326) END, %s, %s)
                       ON CONFLICT (fuente, codigo) DO UPDATE SET nombre = EXCLUDED.nombre, isla = EXCLUDED.isla,
                         punto = EXCLUDED.punto, altitud_m = EXCLUDED.altitud_m, operador = EXCLUDED.operador""",
                    [fuente, codigo, nombre or "", isla or "", lat, lon, lat, altitud, operador or ""],
                )

            # ── Mediciones: a una tabla temporal y de ahí se concilian ─────────
            c.execute("CREATE TEMP TABLE _obs (fuente text, codigo text, variable text, ts timestamptz, valor float8) ON COMMIT DROP")
            consulta, parametros = "SELECT fuente, estacion, variable, ts, valor FROM obs", []
            if desde:
                consulta += " WHERE ts >= ?"
                parametros.append(desde.strftime("%Y-%m-%dT%H:%M:%SZ"))
            leidas = 0
            with c.copy("COPY _obs (fuente, codigo, variable, ts, valor) FROM STDIN") as copia:
                for fuente, codigo, variable, ts, valor in origen.execute(consulta, parametros):
                    copia.write_row((fuente, codigo, variable, _iso(ts), valor))
                    leidas += 1
            fila.leidas = leidas
            c.execute("CREATE INDEX ON _obs (fuente, codigo, variable, ts)")
            c.execute("ANALYZE _obs")
            # Lo que mide el satélite se guarda por zona, y esas «estaciones» no están en la tabla de origen.
            c.execute(
                """INSERT INTO clima_estacion (fuente, codigo, nombre, isla, operador)
                   SELECT DISTINCT fuente, codigo, codigo, '', '' FROM _obs ON CONFLICT (fuente, codigo) DO NOTHING"""
            )
            c.execute(
                """INSERT INTO clima_observacion (estacion_id, variable, ts, valor)
                   SELECT e.id, o.variable, o.ts, o.valor FROM _obs o JOIN clima_estacion e USING (fuente, codigo)
                   ON CONFLICT (estacion_id, variable, ts) DO UPDATE SET valor = EXCLUDED.valor
                   WHERE clima_observacion.valor IS DISTINCT FROM EXCLUDED.valor"""
            )
            fila.cambiadas = c.rowcount

            if desde:
                # Lo que el recolector borró en estos días también se borra aquí. Como defensa, solo
                # si la lectura trajo una cantidad razonable: una lectura trunca no debe vaciar nada.
                c.execute("SELECT count(*) FROM clima_observacion WHERE ts >= %s", [desde])
                aqui = c.fetchone()[0]
                if leidas >= 0.5 * aqui:
                    c.execute(
                        """DELETE FROM clima_observacion x USING clima_estacion e
                           WHERE x.estacion_id = e.id AND x.ts >= %s AND NOT EXISTS (
                             SELECT 1 FROM _obs o WHERE o.fuente = e.fuente AND o.codigo = e.codigo AND o.variable = x.variable AND o.ts = x.ts)""",
                        [desde],
                    )
                    fila.borradas = c.rowcount
                else:
                    registro.warning("Lectura corta (%s de %s): no se borra nada", leidas, aqui)

            # ── Corridas del recolector: las recientes que falten ─────────────
            c.execute("SELECT max(ts) FROM clima_corrida")
            ultima = c.fetchone()[0]
            corte = (ultima - timedelta(minutes=30)).strftime("%Y-%m-%dT%H:%M:%S") if ultima else ""
            c.execute("CREATE TEMP TABLE _corridas (ts timestamptz, fuente text, ok boolean, registros int, segundos float8, error text) ON COMMIT DROP")
            with c.copy("COPY _corridas FROM STDIN") as copia:
                for ts, fuente, ok, registros, segundos, error in origen.execute(
                    "SELECT ts, fuente, ok, registros, segundos, error FROM corridas WHERE ts > ?", [corte]
                ):
                    copia.write_row((_iso(ts), fuente, bool(ok), registros, segundos, (error or "")[:2000]))
            c.execute(
                """INSERT INTO clima_corrida (ts, fuente, ok, registros, segundos, error)
                   SELECT DISTINCT ON (fuente, ts) ts, fuente, ok, registros, segundos, error FROM _corridas
                   ON CONFLICT (fuente, ts) DO NOTHING"""
            )

            _resumir(c, desde)
            c.execute(
                """UPDATE clima_estacion e SET primera = r.primera, ultima = r.ultima
                   FROM (SELECT estacion_id, min(ts) AS primera, max(ts) AS ultima FROM clima_observacion GROUP BY 1) r
                   WHERE r.estacion_id = e.id AND (e.primera IS DISTINCT FROM r.primera OR e.ultima IS DISTINCT FROM r.ultima)"""
            )
    finally:
        origen.close()


def _resumir(c, desde):
    """Rehace los resúmenes por hora de los días releídos (o todos)."""
    hora = desde.replace(minute=0, second=0, microsecond=0) if desde else None
    filtro, parametros = ("WHERE hora >= %s", [hora]) if hora else ("", [])
    c.execute(f"DELETE FROM clima_horaria {filtro}", parametros)
    c.execute(
        f"""INSERT INTO clima_horaria (estacion_id, variable, hora, suma, media, maximo, n)
            SELECT estacion_id, variable, date_trunc('hour', ts), sum(valor), avg(valor), max(valor), count(valor)
            FROM clima_observacion
            WHERE variable = ANY(%s) AND valor IS NOT NULL {'AND ts >= %s' if hora else ''}
            GROUP BY 1, 2, 3""",
        [list(RESUMIDAS)] + parametros,
    )

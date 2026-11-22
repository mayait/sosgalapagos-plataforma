"""Lo común a todas las fuentes de clima: pedir, guardar y preguntar qué hay ya guardado.

Cada fuente es un módulo de esta carpeta con una función `recoger()` que devuelve cuántas
mediciones guardó. Todas escriben en las tablas de la aplicación (PostgreSQL) con estas
funciones; ninguna abre archivos ni otra base.

Convenciones que comparten:
- las horas se guardan en UTC;
- `lluvia_mm` es la lluvia del intervalo (5 minutos, por lo general);
- las filas de respaldo por hora (INAMHI, estación de Erna) llevan los segundos en :30, para
  no chocar con las de 5 minutos, que van en :00;
- las direcciones de las fuentes NO están en el código: se leen del entorno (ver env.ejemplo).
"""
import datetime as dt
import json
import os
import time
import urllib.request

from django.db import connection, transaction

UTC = dt.timezone.utc
GALAPAGOS = dt.timezone(dt.timedelta(hours=-6))
CONTINENTE = dt.timezone(dt.timedelta(hours=-5))
AGENTE = "sosgalapagos-clima/2.0"
HORARIO_SEG = 30  # segundos de las filas de respaldo por hora

# Variables que se resumen por hora. La lluvia se suma; lo demás se promedia.
RESUMIDAS = ("lluvia_mm", "temp_c", "hr_pct", "presion_hpa", "viento_ms", "nivel_mar_m", "rad_wm2")


def endpoint(nombre):
    """Dirección o credencial de una fuente, del entorno. Nunca del repositorio."""
    valor = os.environ.get(nombre)
    if not valor:
        raise RuntimeError(f"Falta {nombre} en el entorno (ver despliegue/produccion/env.ejemplo)")
    return valor


def http_json(url, cuerpo=None, intentos=3, espera=60, cabeceras=None):
    datos = json.dumps(cuerpo).encode() if cuerpo is not None else None
    for i in range(intentos):
        try:
            pedido = urllib.request.Request(url, data=datos, method="POST" if datos else "GET",
                                            headers={"Content-Type": "application/json", "User-Agent": AGENTE, **(cabeceras or {})})
            with urllib.request.urlopen(pedido, timeout=espera) as r:
                texto = r.read()
                # «204, sin contenido»: la fuente respondió bien y no tiene nada nuevo (los
                # aeropuertos no reportan de noche). No es un fallo.
                return json.loads(texto) if texto.strip() else []
        except Exception:
            if i == intentos - 1:
                raise
            time.sleep(2 * (i + 1))


def estacion(fuente, codigo, nombre, isla, lat, lon, altitud=None, operador=""):
    """Crea la estación o actualiza sus datos."""
    with connection.cursor() as c:
        c.execute(
            """INSERT INTO clima_estacion (fuente, codigo, nombre, isla, punto, altitud_m, operador)
               VALUES (%s, %s, %s, %s, CASE WHEN %s::float8 IS NULL THEN NULL ELSE ST_SetSRID(ST_MakePoint(%s, %s), 4326) END, %s, %s)
               ON CONFLICT (fuente, codigo) DO UPDATE SET nombre = EXCLUDED.nombre, isla = EXCLUDED.isla,
                 punto = EXCLUDED.punto, altitud_m = EXCLUDED.altitud_m, operador = EXCLUDED.operador""",
            [fuente, codigo, nombre or "", isla or "", lat, lon, lat, altitud, operador or ""],
        )


def guardar(fuente, filas):
    """filas: [(código de estación, variable, hora con zona, valor)]. Si la medición ya existe, se reemplaza.

    Devuelve cuántas filas recibió. Una estación que aún no existe se crea con su código por nombre.
    """
    limpias = {}
    for codigo, variable, ts, valor in filas:
        if isinstance(valor, float) and valor != valor:  # NaN
            valor = None
        limpias[(codigo, variable, ts.astimezone(UTC))] = valor
    if not limpias:
        return 0
    with transaction.atomic(), connection.cursor() as c:  # la tabla temporal vive lo que la transacción
        c.execute("CREATE TEMP TABLE IF NOT EXISTS _entrada (codigo text, variable text, ts timestamptz, valor float8) ON COMMIT DROP")
        c.execute("TRUNCATE _entrada")
        with c.copy("COPY _entrada (codigo, variable, ts, valor) FROM STDIN") as copia:
            for (codigo, variable, ts), valor in limpias.items():
                copia.write_row((codigo, variable, ts, valor))
        c.execute(
            """INSERT INTO clima_estacion (fuente, codigo, nombre, isla, operador)
               SELECT DISTINCT %s, codigo, codigo, '', '' FROM _entrada ON CONFLICT (fuente, codigo) DO NOTHING""",
            [fuente],
        )
        c.execute(
            """INSERT INTO clima_observacion (estacion_id, variable, ts, valor)
               SELECT e.id, x.variable, x.ts, x.valor FROM _entrada x JOIN clima_estacion e ON e.fuente = %s AND e.codigo = x.codigo
               ON CONFLICT (estacion_id, variable, ts) DO UPDATE SET valor = EXCLUDED.valor
               WHERE clima_observacion.valor IS DISTINCT FROM EXCLUDED.valor""",
            [fuente],
        )
        c.execute(
            """UPDATE clima_estacion e SET primera = LEAST(e.primera, r.primera), ultima = GREATEST(e.ultima, r.ultima)
               FROM (SELECT codigo, min(ts) AS primera, max(ts) AS ultima FROM _entrada WHERE variable <> 'lluvia_dia_mm' GROUP BY 1) r
               WHERE e.fuente = %s AND e.codigo = r.codigo
                 AND (e.primera IS NULL OR e.ultima IS NULL OR r.primera < e.primera OR r.ultima > e.ultima)""",
            [fuente],
        )
    return len(limpias)


def _filtro(fuente, codigo, variable, de_cinco_min):
    partes, parametros = ["e.fuente = %s"], [fuente]
    if codigo is not None:
        partes.append("e.codigo = %s")
        parametros.append(codigo)
    if variable is not None:
        partes.append("o.variable = %s")
        parametros.append(variable)
    if de_cinco_min:  # sin las filas de respaldo por hora
        partes.append(f"extract(second FROM o.ts)::int <> {HORARIO_SEG}")
    return " AND ".join(partes), parametros


def ultimo(fuente, codigo=None, variable=None, de_cinco_min=False):
    """Hora de la última medición guardada, o None."""
    filtro, parametros = _filtro(fuente, codigo, variable, de_cinco_min)
    with connection.cursor() as c:
        c.execute(f"SELECT max(o.ts) FROM clima_observacion o JOIN clima_estacion e ON e.id = o.estacion_id WHERE {filtro}", parametros)
        return c.fetchone()[0]


def existe(fuente, codigo, variable=None, desde=None, hasta=None, en=None, de_cinco_min=False, desde_excluida=False):
    """¿Hay alguna medición de esa estación en ese momento (`en`) o en ese tramo?"""
    filtro, parametros = _filtro(fuente, codigo, variable, de_cinco_min)
    if en is not None:
        filtro += " AND o.ts = %s"
        parametros.append(en)
    if desde is not None:
        filtro += f" AND o.ts {'>' if desde_excluida else '>='} %s"
        parametros.append(desde)
    if hasta is not None:
        filtro += " AND o.ts <= %s"
        parametros.append(hasta)
    with connection.cursor() as c:
        c.execute(f"SELECT 1 FROM clima_observacion o JOIN clima_estacion e ON e.id = o.estacion_id WHERE {filtro} LIMIT 1", parametros)
        return c.fetchone() is not None


def serie(fuente, codigo, variable, desde=None, antes_de=None, orden="ASC", limite=None):
    """[(hora, valor)] de una estación."""
    filtro, parametros = _filtro(fuente, codigo, variable, False)
    if desde is not None:
        filtro += " AND o.ts >= %s"
        parametros.append(desde)
    if antes_de is not None:
        filtro += " AND o.ts < %s"
        parametros.append(antes_de)
    with connection.cursor() as c:
        c.execute(f"""SELECT o.ts, o.valor FROM clima_observacion o JOIN clima_estacion e ON e.id = o.estacion_id
                      WHERE {filtro} ORDER BY o.ts {orden} {'LIMIT %s' % int(limite) if limite else ''}""", parametros)
        return c.fetchall()


def borrar(fuente, codigo, variable, desde=None, hasta_antes_de=None, de_respaldo=None):
    """Borra mediciones de una estación en un tramo. `de_respaldo`: True solo las de respaldo por hora, False solo las demás."""
    filtro, parametros = "e.fuente = %s AND e.codigo = %s AND o.variable = %s", [fuente, codigo, variable]
    if desde is not None:
        filtro += " AND o.ts >= %s"
        parametros.append(desde)
    if hasta_antes_de is not None:
        filtro += " AND o.ts < %s"
        parametros.append(hasta_antes_de)
    if de_respaldo is not None:
        filtro += f" AND extract(second FROM o.ts)::int {'=' if de_respaldo else '<>'} {HORARIO_SEG}"
    with connection.cursor() as c:
        c.execute(f"DELETE FROM clima_observacion o USING clima_estacion e WHERE e.id = o.estacion_id AND {filtro}", parametros)
        return c.rowcount


def resumir(desde=None):
    """Rehace los resúmenes por hora desde esa hora (o todos). Es lo que leen casi todas las consultas."""
    hora = desde.replace(minute=0, second=0, microsecond=0) if desde else None
    filtro, parametros = ("WHERE hora >= %s", [hora]) if hora else ("", [])
    with connection.cursor() as c:
        c.execute(f"DELETE FROM clima_horaria {filtro}", parametros)
        c.execute(
            f"""INSERT INTO clima_horaria (estacion_id, variable, hora, suma, media, maximo, n)
                SELECT estacion_id, variable, date_trunc('hour', ts), sum(valor), avg(valor), max(valor), count(valor)
                FROM clima_observacion
                WHERE variable = ANY(%s) AND valor IS NOT NULL {'AND ts >= %s' if hora else ''}
                GROUP BY 1, 2, 3""",
            [list(RESUMIDAS)] + parametros,
        )


def configurado(*nombres):
    """¿Están en el entorno todas las variables que una fuente necesita?"""
    return all(os.environ.get(n) for n in nombres)

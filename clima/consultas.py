"""Lecturas del clima para la API y las páginas. Todo sale de los resúmenes por hora."""
from datetime import datetime, timedelta, timezone

from django.db import connection

from .models import Estacion, Sincronizacion

GALAPAGOS = timezone(timedelta(hours=-6))  # el día de Galápagos; no cambia de hora
DE_SUMA = {"lluvia_mm"}


def estaciones(ahora=None):
    """Estaciones con medición propia (sin las zonas de satélite), con su lluvia reciente."""
    ahora = ahora or datetime.now(timezone.utc)
    with connection.cursor() as c:
        c.execute(
            """SELECT estacion_id,
                      sum(suma) FILTER (WHERE hora >= %s) , sum(suma) FILTER (WHERE hora >= %s), sum(suma)
               FROM clima_horaria WHERE variable = 'lluvia_mm' AND hora >= %s GROUP BY 1""",
            [ahora - timedelta(hours=1), ahora - timedelta(hours=24), ahora - timedelta(hours=72)],
        )
        lluvia = {e: (a, b, d) for e, a, b, d in c.fetchall()}
    salida = []
    for e in Estacion.objects.exclude(fuente="goes"):
        l = lluvia.get(e.pk, (None, None, None))
        salida.append({
            "id": e.clave, "nombre": e.nombre, "isla": e.isla, "operador": e.operador,
            "lat": e.punto.y if e.punto else None, "lon": e.punto.x if e.punto else None, "altitud_m": e.altitud_m,
            "primera": e.primera, "ultima": e.ultima,
            "minutos_sin_dato": round((ahora - e.ultima).total_seconds() / 60) if e.ultima else None,
            "lluvia_mm": {"1h": _r(l[0]), "24h": _r(l[1]), "72h": _r(l[2])},
        })
    return salida


def _r(v):
    return None if v is None else round(v, 1)


def serie(clave, variable, desde, hasta, paso="hora"):
    """Valores por hora o por día (día de Galápagos) de una estación. None donde no hubo medición."""
    fuente, _, codigo = clave.partition("/")
    estacion = Estacion.objects.filter(fuente=fuente, codigo=codigo).first()
    if not estacion:
        return None
    columna = "suma" if variable in DE_SUMA else "media"
    if paso == "dia":
        desde = desde.astimezone(GALAPAGOS).replace(hour=0, minute=0, second=0, microsecond=0)
        n, salto = max(0, (hasta - desde).days + (1 if (hasta - desde).seconds else 0)), timedelta(days=1)
        agrupa = "date_trunc('day', hora - interval '6 hours') + interval '6 hours'"
        valor = "sum(suma)" if variable in DE_SUMA else "avg(media)"
    else:
        desde = desde.replace(minute=0, second=0, microsecond=0)
        n, salto = int((hasta - desde).total_seconds() // 3600), timedelta(hours=1)
        agrupa, valor = "hora", f"max({columna})"
    n = min(n, 24 * 366)
    valores = [None] * n
    with connection.cursor() as c:
        c.execute(
            f"SELECT {agrupa} AS t, {valor}, sum(n) FROM clima_horaria WHERE estacion_id = %s AND variable = %s AND hora >= %s AND hora < %s GROUP BY 1",
            [estacion.pk, variable, desde, hasta],
        )
        for t, v, _n in c.fetchall():
            i = int((t - desde) / salto)
            if 0 <= i < n and v is not None:
                valores[i] = round(v, 2)
    return {"estacion": clave, "nombre": estacion.nombre, "variable": variable, "paso": paso, "inicio": desde, "valores": valores}


def salud(ahora=None):
    """Cómo va cada fuente en las últimas 24 horas y cuánto retraso lleva la copia a esta base."""
    ahora = ahora or datetime.now(timezone.utc)
    with connection.cursor() as c:
        c.execute(
            """SELECT fuente, count(*), count(*) FILTER (WHERE ok), max(ts) FILTER (WHERE ok), max(ts),
                      avg(segundos), max(segundos), sum(registros)
               FROM clima_corrida WHERE ts >= %s GROUP BY 1 ORDER BY 1""",
            [ahora - timedelta(hours=24)],
        )
        fuentes = [
            {"fuente": f, "corridas": n, "bien": ok, "acierto_pct": round(100 * ok / n) if n else None,
             "ultima_bien": ub, "ultima": u, "segundos_media": _r(sm), "segundos_max": _r(sx), "registros": reg,
             "minutos_sin_exito": round((ahora - ub).total_seconds() / 60) if ub else None}
            for f, n, ok, ub, u, sm, sx, reg in c.fetchall()
        ]
        c.execute("SELECT count(*), max(ts) FROM clima_observacion")
        total, ultima = c.fetchone()
        c.execute("SELECT count(*) FROM clima_horaria")
        horarias = c.fetchone()[0]
    copias = list(Sincronizacion.objects.filter(inicio__gte=ahora - timedelta(hours=24)))
    con_error = [s for s in copias if s.error]
    return {
        "generado": ahora,
        "observaciones": total,
        "resumenes_por_hora": horarias,
        "ultima_medicion": ultima,
        "retraso_min": round((ahora - ultima).total_seconds() / 60, 1) if ultima else None,
        "copia": {
            "corridas_24h": len(copias), "con_error": len(con_error),
            "segundos_media": _r(sum(s.segundos for s in copias) / len(copias)) if copias else None,
            "ultimo_error": con_error[0].error if con_error else "",
        },
        "fuentes": fuentes,
    }

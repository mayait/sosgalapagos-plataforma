# SOS Galápagos · © 2026 Universidad San Francisco de Quito (USFQ) · Autor: Julián Maya <jamaya@usfq.edu.ec>
# Licencia Apache 2.0 (ver LICENSE y NOTICE): puede reutilizarse dando crédito.
"""Los datos que lee el panel de /clima/: estado.json, horario.json, diario.json y pronostico.json.

Todo sale de PostgreSQL: de los resúmenes por hora y de consultas acotadas, no de recorrer toda
la historia cada cinco minutos.

- Nivel de lluvia peligrosa: clima/nivel.py.    - Mareas: clima/mareas.py.
- Pronóstico de modelos: clima/senal.py.        - Estacionalidad: clima/estacionalidad.py.
- Satélite: lo que deja el colector (clima/satelite/) en la tabla Estado.

Recordatorio para quien lo toque: el nivel, el pronóstico, las mareas predichas, la estacionalidad
y el satélite son modelos o estimaciones propias, NO datos oficiales. El panel lo dice en cada bloque.
"""
import datetime as dt
import json
import logging
import os
import time
from pathlib import Path

from django.conf import settings
from django.db import connection

from . import danadas as marcas_de_dano
from .fuentes import OPERADOR
from .models import Estado

registro = logging.getLogger(__name__)
UTC = dt.timezone.utc
iso = lambda t: t.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")  # noqa: E731


def _seguro(nombre, funcion):
    """Una parte que falla no tumba el resto: deja {"error": …}, como hacía el recolector."""
    try:
        return funcion()
    except Exception as e:
        registro.exception("Falló %s al generar el panel", nombre)
        return {"error": str(e)[:200]}


EVENTOS = [  # momentos de referencia para comparar (horas UTC)
    {"id": "inundacion-2026-10-30", "nombre": "Inundación La Cascada (30–31 oct 2026)", "desde": "2026-10-30T06:00:00Z", "hasta": "2026-11-01T06:00:00Z"},
]
# Red DARWIN-Rain (Philipps-Universität Marburg, con la Fundación Charles Darwin y la Universidad de
# Cuenca): estaciones automáticas con pluviómetro, sin transmisión en tiempo real (los datos se suben
# con semanas de retraso y su descarga requiere un acuerdo). Se publican nombre, ubicación y cita
# (autorizado por Julián el 12-nov-2026) para que se sepa que existen; no hay serie. La fecha es el
# último dato publicado que vimos en sus metadatos (12-nov-2026). Cerro Crocker, Santa Rosa y
# Militar no se repiten: son los mismos sitios que transmiten en vivo por IERSE-WSN.
DARWIN_RAIN = [  # (código, nombre, isla, lat, lon, altitud, datos hasta, nota)
    ("puerto_baquerizo", "Puerto Baquerizo Moreno (DARWIN)", "San Cristóbal", -0.9031, -89.612, 25, "2026-10-29", None),
    ("galapaguera", "La Galapaguera", "San Cristóbal", -0.914, -89.437, 165, "2026-10-10", None),
    ("el_junco", "El Junco (DARWIN)", "San Cristóbal", -0.8938, -89.480, 684, "2026-05-25", None),
    ("sierra_negra", "Sierra Negra", "Isabela", -0.8484, -91.131, 1145, "2026-10-28", None),
    ("cueva_sucre", "Cueva de Sucre", "Isabela", -0.8431, -91.028, 382, "2026-10-19", None),
    ("puerto_villamil", "Puerto Villamil (El Chapín)", "Isabela", -0.9462, -90.974, 22, "2026-01-14", None),
    ("wittmer", "Wittmer (Puerto Velasco Ibarra)", "Floreana", -1.2757, -90.4875, None, "2026-10-01", "ubicación aproximada: la red no publica coordenadas"),
    ("minas_rojas", "Minas Rojas", "Santa Cruz", -0.6186, -90.367, 619, "2026-05-20", None),
    ("puerto_ayora_fcd", "Puerto Ayora (FCD)", "Santa Cruz", -0.7438, -90.302, 4, "2026-01-12", None),
]
# Fuentes que no son estaciones del panel: el satélite (zonas) y las series históricas diarias de la FCD.
SIN_PANEL = ("goes", "fcd")


def _estaciones(ahora, marcas):
    hace = lambda **k: ahora - dt.timedelta(**k)  # noqa: E731
    with connection.cursor() as c:
        c.execute("""SELECT id, fuente, codigo, nombre, isla, ST_Y(punto), ST_X(punto), altitud_m FROM clima_estacion
                     WHERE NOT (fuente = ANY(%s)) ORDER BY isla, altitud_m DESC NULLS LAST""", [list(SIN_PANEL)])
        filas = c.fetchall()
        c.execute("SELECT estacion_id, max(ts) FROM clima_observacion WHERE variable <> 'lluvia_dia_mm' GROUP BY 1")
        ultimo = dict(c.fetchall())
        c.execute("""SELECT DISTINCT ON (estacion_id, variable) estacion_id, variable, valor FROM clima_observacion
                     WHERE ts >= %s AND variable <> 'lluvia_dia_mm' ORDER BY estacion_id, variable, ts DESC""", [hace(hours=3)])
        actual = {}
        for e, v, x in c.fetchall():
            actual.setdefault(e, {})[v] = round(x, 2) if x is not None else None
        ventanas = (("1h", 1), ("3h", 3), ("6h", 6), ("24h", 24), ("72h", 72), ("7d", 168))
        sumas = ", ".join(f"sum(valor) FILTER (WHERE ts > %s), count(*) FILTER (WHERE ts > %s)" for _ in ventanas)
        c.execute(f"SELECT estacion_id, {sumas} FROM clima_observacion WHERE variable = 'lluvia_mm' AND ts > %s GROUP BY 1",
                  [p for _, h in ventanas for p in (hace(hours=h), hace(hours=h))] + [hace(hours=168)])
        lluvia = {f[0]: f[1:] for f in c.fetchall()}
    ests = []
    for pk, fuente, codigo, nombre, isla, lat, lon, altitud in filas:
        e = {"fuente": fuente, "estacion": codigo, "nombre": nombre, "isla": isla, "lat": lat, "lon": lon, "altitud_m": altitud,
             "operador": OPERADOR.get(fuente, fuente), "ultimo": iso(ultimo[pk]) if pk in ultimo else None,
             "actual": dict(actual.get(pk, {})), "lluvia": {}}
        marca = marcas_de_dano.publica(marcas, f"{fuente}/{codigo}")
        if marca:  # sensor dañado: no se publica su lluvia (los crudos siguen en la base)
            e["danada"] = marca
            for v in marca["variables"]:
                e["actual"].pop(v, None)
        if marca and "lluvia_mm" in marca["variables"]:
            e["lluvia"] = {k: None for k, _ in ventanas}
        else:
            valores = lluvia.get(pk)
            for i, (etiqueta, _) in enumerate(ventanas):
                e["lluvia"][etiqueta] = None if not valores or not valores[2 * i + 1] else round(valores[2 * i], 1)
        ests.append(e)
    ests += [{"fuente": "darwin", "estacion": c_, "nombre": n, "isla": i, "lat": la, "lon": lo, "altitud_m": a, "operador": "DARWIN-Rain",
              "ultimo": None, "actual": {}, "lluvia": {}, "en_vivo": False, "datos_hasta": h, **({"nota": nota} if nota else {})}
             for c_, n, i, la, lo, a, h, nota in DARWIN_RAIN]
    return ests


def _fuentes():
    with connection.cursor() as c:
        c.execute("SELECT DISTINCT ON (fuente) fuente, ts, ok, registros, segundos FROM clima_corrida ORDER BY fuente, ts DESC")
        return {OPERADOR.get(f, f): {"ts": iso(ts), "ok": int(ok), "registros": n, "segundos": s} for f, ts, ok, n, s in c.fetchall()}


def estado(ahora=None):
    from . import mareas, nivel, senal

    ahora = ahora or dt.datetime.now(UTC)
    marcas = marcas_de_dano.vigentes(ahora)
    pron = _seguro("el pronóstico", lambda: senal.publicado(ahora))
    satelite = Estado.objects.filter(clave="satelite").first()
    return {"generado": iso(ahora), "estaciones": _estaciones(ahora, marcas), "fuentes": _fuentes(), "eventos": EVENTOS,
            "inundacion": _seguro("el nivel de lluvia", lambda: nivel.calcular(ahora)),
            "mareas": _seguro("las mareas", lambda: mareas.calcular(ahora)), "pronostico": pron,
            "satelite": satelite.datos if satelite else None}, pron


def horario(ahora=None):
    """Historia horaria completa en un eje común (horas UTC): lluvia (suma), temperatura y nivel del mar (media)."""
    ahora = ahora or dt.datetime.now(UTC)
    marcas = marcas_de_dano.vigentes(ahora)
    with connection.cursor() as c:
        c.execute("""SELECT min(h.hora) FROM clima_horaria h JOIN clima_estacion e ON e.id = h.estacion_id
                     WHERE h.variable IN ('lluvia_mm', 'temp_c') AND e.fuente IN ('ierse', 'gsc')""")
        h0 = c.fetchone()[0]
        series, n = {}, 0
        if h0:
            n = int((ahora - h0).total_seconds() // 3600) + 1
            c.execute("""SELECT e.fuente, e.codigo, h.variable, h.hora, CASE WHEN h.variable = 'lluvia_mm' THEN h.suma ELSE h.media END
                         FROM clima_horaria h JOIN clima_estacion e ON e.id = h.estacion_id
                         WHERE h.variable IN ('lluvia_mm', 'temp_c', 'nivel_mar_m') AND h.hora >= %s""", [h0])
            for f, e, v, h, x in c.fetchall():
                i = int((h - h0).total_seconds() // 3600)
                if not 0 <= i < n:
                    continue
                s = series.setdefault(f"{f}/{e}", {}).setdefault(v, [None] * n)
                if marcas_de_dano.danada(marcas, f"{f}/{e}", v, h + dt.timedelta(minutes=59, seconds=59)):
                    continue  # hora con datos de un sensor dañado: queda en null
                s[i] = None if x is None else round(x, 1)
    return {"generado": iso(ahora), "inicio": iso(h0) if h0 else None, "horas": n, "series": series}


def diario(ahora=None):
    """Lluvia por día de Galápagos (UTC−6): la suma de lo medido si la estación transmitió 20 horas o más;
    si no, el diario histórico de la fuente. Más la estacionalidad."""
    ahora = ahora or dt.datetime.now(UTC)
    marcas = marcas_de_dano.vigentes(ahora)
    dia = {}
    with connection.cursor() as c:
        c.execute("""SELECT e.fuente, e.codigo, (h.hora - interval '6 hours')::date, sum(h.suma), count(*)
                     FROM clima_horaria h JOIN clima_estacion e ON e.id = h.estacion_id
                     WHERE h.variable = 'lluvia_mm' AND NOT (e.fuente = ANY(%s)) GROUP BY 1, 2, 3""", [list(SIN_PANEL)])
        for f, e, d, ll, hs in c.fetchall():
            dia.setdefault(f"{f}/{e}", {})[d.isoformat()] = (round(ll, 1), hs)
        c.execute("""SELECT e.fuente, e.codigo, (o.ts - interval '5 hours')::date, o.valor
                     FROM clima_observacion o JOIN clima_estacion e ON e.id = o.estacion_id
                     WHERE o.variable = 'lluvia_dia_mm' AND NOT (e.fuente = ANY(%s))""", [list(SIN_PANEL)])
        for f, e, d, ll in c.fetchall():
            s = dia.setdefault(f"{f}/{e}", {})
            d = d.isoformat()
            if ll is not None and (d not in s or s[d][1] < 20):
                s[d] = (round(ll, 1), 24)
    for k, s in dia.items():  # sensores dañados: sin lluvia diaria desde el día en que empezó la falla
        x = marcas_de_dano.danada(marcas, k, "lluvia_mm")
        if x:
            d0 = (x["desde_dt"] - dt.timedelta(hours=6)).date().isoformat()
            for d in [d for d in s if d >= d0]:
                s[d] = (None, 0)
    salida = {}
    for k, s in dia.items():
        fechas = sorted(s)
        d0 = dt.date.fromisoformat(fechas[0])
        n = (dt.date.fromisoformat(fechas[-1]) - d0).days + 1
        ll, cob = [None] * n, [0] * n
        for d, (x, hs) in s.items():
            i = (dt.date.fromisoformat(d) - d0).days
            ll[i], cob[i] = x, min(hs, 24)
        salida[k] = {"inicio": fechas[0], "lluvia": ll, "horas": cob}
    return {"generado": iso(ahora), "diario": salida, "estacionalidad": _estacionalidad(ahora)}


def _estacionalidad(ahora):
    """Cambia una vez al día y recorre series de años: se calcula cada seis horas y se guarda."""
    guardada = Estado.objects.filter(clave="estacionalidad").first()
    if guardada and ahora - guardada.generado < dt.timedelta(hours=6):
        return guardada.datos
    from . import estacionalidad

    datos = _seguro("la estacionalidad", estacionalidad.calcular)
    if "error" not in datos:
        Estado.objects.update_or_create(clave="estacionalidad", defaults={"datos": datos, "generado": ahora})
    return datos


def _escribir(ruta, obj):
    ruta.parent.mkdir(parents=True, exist_ok=True)
    tmp = ruta.with_suffix(ruta.suffix + ".django.tmp")
    tmp.write_text(json.dumps(obj, ensure_ascii=False, separators=(",", ":"), default=str))
    os.chmod(tmp, 0o644)
    os.replace(tmp, ruta)


def publicar(carpeta=None, ahora=None):
    """Genera los tres archivos y los deja en la carpeta (por defecto, la que lee el panel). Devuelve tiempos y tamaños."""
    carpeta = Path(carpeta or settings.CLIMA_SALIDA)
    ahora = ahora or dt.datetime.now(UTC)
    t0, r = time.monotonic(), {}
    est, pron = estado(ahora)
    if "error" not in pron:
        _escribir(carpeta / "pronostico.json", pron)
    _escribir(carpeta / "estado.json", est)
    r["estado_s"] = round(time.monotonic() - t0, 2)
    t1 = time.monotonic()
    _escribir(carpeta / "horario.json", horario(ahora))
    r["horario_s"] = round(time.monotonic() - t1, 2)
    t2 = time.monotonic()
    _escribir(carpeta / "diario.json", diario(ahora))
    r["diario_s"] = round(time.monotonic() - t2, 2)
    r["total_s"] = round(time.monotonic() - t0, 2)
    r["errores"] = [k for k in ("inundacion", "mareas", "pronostico") if isinstance(est.get(k), dict) and "error" in est[k]]
    return r

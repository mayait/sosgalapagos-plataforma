"""Recolectores nativos: cada fuente como una función que escribe directo en PostgreSQL.

Etapa 5 de docs/plan-clima.md. Las fuentes se pasan de una en una: la que figura en
CLIMA_FUENTES_NATIVAS la recoge esta aplicación y deja de copiarse de la base del recolector
anterior (que la sigue recogiendo por su lado, así se pueden comparar las dos).

Cada función es la del recolector anterior con la misma conversión de unidades y de horas;
solo cambia dónde guarda. Los endpoints van en variables de entorno, nunca aquí.
"""
import json
import logging
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone

from django.conf import settings
from django.db import connection, transaction

from .models import Corrida

registro = logging.getLogger(__name__)
UA = "sosgalapagos.org (clima; contacto en el sitio)"


def http_json(url, intentos=3, espera=60):
    for i in range(intentos):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers={"Content-Type": "application/json", "User-Agent": UA}), timeout=espera) as r:
                cuerpo = r.read()
                # «204, sin contenido»: la fuente respondió bien y no tiene nada nuevo (los aeropuertos no
                # reportan de noche). El recolector anterior lo contaba como fallo.
                return json.loads(cuerpo) if cuerpo.strip() else []
        except Exception:
            if i == intentos - 1:
                raise
            time.sleep(2 * (i + 1))


def estacion(c, fuente, codigo, nombre, isla, lat, lon, altitud=None, operador=""):
    c.execute(
        """INSERT INTO clima_estacion (fuente, codigo, nombre, isla, punto, altitud_m, operador)
           VALUES (%s, %s, %s, %s, ST_SetSRID(ST_MakePoint(%s, %s), 4326), %s, %s)
           ON CONFLICT (fuente, codigo) DO UPDATE SET nombre = EXCLUDED.nombre, isla = EXCLUDED.isla, punto = EXCLUDED.punto,
             altitud_m = EXCLUDED.altitud_m, operador = EXCLUDED.operador""",
        [fuente, codigo, nombre, isla, lon, lat, altitud, operador],
    )


def guardar(c, fuente, filas):
    """filas: [(código de estación, variable, datetime con zona, valor)]. Devuelve cuántas llegaron."""
    filas = list(filas)
    if not filas:
        return 0
    c.execute("CREATE TEMP TABLE IF NOT EXISTS _nat (codigo text, variable text, ts timestamptz, valor float8) ON COMMIT DROP")
    c.execute("TRUNCATE _nat")
    with c.copy("COPY _nat FROM STDIN") as copia:
        for codigo, variable, ts, valor in filas:
            copia.write_row((codigo, variable, ts.astimezone(timezone.utc).replace(microsecond=0), valor))
    c.execute(
        """INSERT INTO clima_observacion (estacion_id, variable, ts, valor)
           SELECT e.id, n.variable, n.ts, n.valor FROM (SELECT DISTINCT ON (codigo, variable, ts) * FROM _nat) n
           JOIN clima_estacion e ON e.fuente = %s AND e.codigo = n.codigo
           ON CONFLICT (estacion_id, variable, ts) DO UPDATE SET valor = EXCLUDED.valor WHERE clima_observacion.valor IS DISTINCT FROM EXCLUDED.valor""",
        [fuente],
    )
    return len(filas)


# ── METAR (aeropuertos) ──────────────────────────────────────────────────────
METAR_EST = {"SEGS": ("Aeropuerto Seymour (Baltra)", "Baltra", -0.4539, -90.2658, 51),
             "SEST": ("Aeropuerto San Cristóbal", "San Cristóbal", -0.9100, -89.6170, 18)}


def _codigo_lluvia(wx):
    """0 sin lluvia, 1 llovizna o lluvia débil, 2 moderada, 3 fuerte o tormenta."""
    wx = wx or ""
    if not any(k in wx for k in ("RA", "DZ", "TS", "SH")):
        return 0
    if "+" in wx or "TS" in wx:
        return 3
    if "-" in wx or ("DZ" in wx and "RA" not in wx):
        return 1
    return 2


def fuente_metar(c):
    q = urllib.parse.urlencode({"ids": ",".join(METAR_EST), "format": "json", "hours": 3})
    filas = []
    for m in http_json(f"{settings.CLIMA_METAR_API}?{q}"):
        cod = m.get("icaoId")
        if cod not in METAR_EST:
            continue
        t = datetime.fromtimestamp(m["obsTime"], timezone.utc)
        if m.get("temp") is not None:
            filas.append((cod, "temp_c", t, float(m["temp"])))
        if m.get("altim") is not None:
            filas.append((cod, "presion_hpa", t, float(m["altim"])))
        if m.get("wspd") is not None:
            filas.append((cod, "viento_ms", t, round(float(m["wspd"]) * 0.5144, 1)))
        filas.append((cod, "lluvia_codigo", t, _codigo_lluvia(m.get("wxString"))))
    for cod, (nombre, isla, lat, lon, alt) in METAR_EST.items():
        estacion(c, "metar", cod, nombre, isla, lat, lon, alt, "Aeropuertos (METAR)")
    return guardar(c, "metar", filas)


FUENTES = {"metar": fuente_metar}


def nativas():
    return [f for f in settings.CLIMA_FUENTES_NATIVAS if f in FUENTES]


def recolectar():
    """Corre las fuentes nativas, una por una. Devuelve {fuente: registros o error}."""
    from .sincronizar import _resumir

    salida = {}
    for fuente in nativas():
        t0, ahora = time.monotonic(), datetime.now(timezone.utc)
        try:
            with transaction.atomic(), connection.cursor() as c:
                n = FUENTES[fuente](c)
                _resumir(c, ahora.replace(hour=0, minute=0, second=0, microsecond=0))  # los resúmenes de hoy
            Corrida.objects.create(fuente=fuente, ts=ahora, ok=True, registros=n, segundos=round(time.monotonic() - t0, 2))
            salida[fuente] = n
        except Exception as e:
            registro.exception("Falló la fuente %s", fuente)
            Corrida.objects.create(fuente=fuente, ts=ahora, ok=False, registros=0, segundos=round(time.monotonic() - t0, 2), error=f"{type(e).__name__}: {e}"[:500])
            salida[fuente] = f"error: {type(e).__name__}"
    return salida

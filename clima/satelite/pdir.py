# SOS Galápagos · © 2026 Universidad San Francisco de Quito (USFQ) · Autor: Julián Maya <jamaya@usfq.edu.ec>
# Todos los derechos reservados. Usar, copiar, modificar o derivar de este código requiere permiso escrito del autor (ver LICENSE).
"""Lluvia estimada por satélite PDIR-Now (CHRS, Universidad de California, Irvine), recortada a Galápagos.

PDIR-Now es una ESTIMACIÓN POR INFRARROJO, como el RRQPE de la NOAA: no es lluvia medida ni un dato
oficial, y no ve la garúa ni la lluvia de nubes bajas (el 23-nov-2026 a las 04 UTC dio 0 en La Cascada
mientras las estaciones medían 3,3 mm/h). Solo se MUESTRA en el panel: no entra en la señal de
vigilancia (vigilancia.py) ni en el nivel de lluvia.

Archivo horario (~4,3 MB comprimido): int16 little-endian, mm/h × 100, negativo = sin dato.
3000 filas × 9000 columnas de 0,04°. La fila 0 está centrada en 59,98° N; la columna 0, en 0,02° E
(la longitud va de 0,02 a 359,98: oeste = lon + 360). La hora del archivo es la hora UTC de INICIO de
la hora acumulada. Llega unos 15–20 min después de terminar la hora.

Solo biblioteca estándar. Se lee por flujo: solo se descomprimen las filas del recorte.
La raíz del archivo va en CLIMA_PDIRNOW_URL; aquí no se escribe ningún endpoint.

Salida: CLIMA_SALIDA/pdirnow.json (la sirve /riesgos/api/clima/pdirnow.json), con las últimas
HORAS_GUARDADAS horas de rejilla (un byte por celda) y el máximo por zona y a 25 km.
"""
from __future__ import annotations

import array
import base64
import datetime as dt
import gzip
import io
import json
import math
import os
import sys
import tempfile
import urllib.error
import urllib.request
from pathlib import Path

UTC = dt.timezone.utc
UA = "sosgalapagos-clima-satelite/0.1"
NOMBRE = "pdirnow.json"

# Rejilla global del archivo
FILAS, COLUMNAS = 3000, 9000
PASO = 0.04
LAT0 = 59.98          # centro de la fila 0
LON0 = 0.02           # centro de la columna 0 (0–360)

# Recorte (grados): sur, norte, oeste, este
CAJA = (-2.0, 1.5, -92.5, -88.5)
HORAS_GUARDADAS = 6
ANILLO_KM = 25
TIMEOUT_S = 40
REINTENTO_VIEJAS_MIN = 30   # una hora vieja que faltó se vuelve a pedir, como mucho, cada 30 min
LATENCIA_MIN = 15           # antes de esto, ni se intenta la hora recién terminada

FUENTE = "PDIR-Now (CHRS, Universidad de California, Irvine)"
ADVERTENCIA = ("Lluvia ESTIMADA por satélite (infrarrojo), no medida ni oficial. No ve la garúa ni la lluvia de "
               "nubes bajas: un cero aquí no quiere decir que no llueva. No entra en la señal satelital ni en el nivel de lluvia.")


# ── Geometría ────────────────────────────────────────────────────────────────
def fila_de(lat: float) -> int:
    """Fila cuya celda contiene lat."""
    return math.floor((LAT0 + PASO / 2 - lat) / PASO)


def columna_de(lon: float) -> int:
    """Columna cuya celda contiene lon (acepta −180…180 o 0…360)."""
    return math.floor(((lon % 360) - (LON0 - PASO / 2)) / PASO)


def centro(fila: int, columna: int) -> tuple[float, float]:
    lon = LON0 + PASO * columna
    return round(LAT0 - PASO * fila, 4), round(lon - 360 if lon > 180 else lon, 4)


def ventana(caja=CAJA):
    """(fila0, fila1, col0, col1), inclusivas: todas las celdas que tocan la caja."""
    s, n, o, e = caja
    return fila_de(n), fila_de(s), columna_de(o), columna_de(e)


# ── Lectura ──────────────────────────────────────────────────────────────────
def recortar(flujo, caja=CAJA, columnas=COLUMNAS):
    """Recorte de un archivo PDIR-Now (flujo binario ya descomprimido o gzip abierto).

    Devuelve {"filas", "columnas", "fila0", "col0", "mmh"}: mmh es una lista por filas (de norte a sur)
    con mm/h o None (sin dato). Lee solo las filas del recorte."""
    f0, f1, c0, c1 = ventana(caja)
    ancho = 2 * columnas
    flujo.seek(f0 * ancho)
    crudo = flujo.read((f1 - f0 + 1) * ancho)
    if len(crudo) < (f1 - f0 + 1) * ancho:
        raise ValueError("archivo PDIR-Now incompleto")
    valores = array.array("h")
    valores.frombytes(crudo)
    if sys.byteorder != "little":
        valores.byteswap()
    mmh = [[(v / 100 if v >= 0 else None) for v in valores[i * columnas + c0:i * columnas + c1 + 1]]
           for i in range(f1 - f0 + 1)]
    return {"filas": f1 - f0 + 1, "columnas": c1 - c0 + 1, "fila0": f0, "col0": c0, "mmh": mmh}


def leer_gz(datos: bytes, caja=CAJA, columnas=COLUMNAS):
    with gzip.GzipFile(fileobj=io.BytesIO(datos)) as g:
        return recortar(g, caja, columnas)


# ── Codificación: un byte por celda, 255 = sin dato ─────────────────────────
def codificar(mm):
    """mm/h → byte. mm/h = (b / 10)²: 0,01 mm/h de resolución abajo, ≈ 1,4 mm/h a 50, hasta 645."""
    if mm is None:
        return 255
    return min(254, round(10 * math.sqrt(max(0.0, mm))))


def decodificar(b):
    return None if b == 255 else (b / 10) ** 2


# ── Zonas ────────────────────────────────────────────────────────────────────
def ampliar(caja, km):
    g = km / 111.0
    return [caja[0] - g, caja[1] - g, caja[2] + g, caja[3] + g]


def maximo(recorte, bbox):
    """Máximo (mm/h) de las celdas que tocan la caja [oeste, sur, este, norte]. Sin ninguna con dato: None."""
    o, s, e, n = bbox
    f0, f1 = fila_de(n) - recorte["fila0"], fila_de(s) - recorte["fila0"]
    c0, c1 = columna_de(o) - recorte["col0"], columna_de(e) - recorte["col0"]
    vals = [v for fila in recorte["mmh"][max(0, f0):max(0, f1 + 1)] for v in fila[max(0, c0):max(0, c1 + 1)] if v is not None]
    return round(max(vals), 2) if vals else None


def por_zona(recorte, zonas):
    return {zid: {"max_mmh": maximo(recorte, z["bbox"]), "max_mmh_25km": maximo(recorte, ampliar(z["bbox"], ANILLO_KM))}
            for zid, z in zonas.items()}


# ── Descarga ─────────────────────────────────────────────────────────────────
def raiz() -> str:
    r = os.environ.get("CLIMA_PDIRNOW_URL", "").rstrip("/")
    if not r:
        raise RuntimeError("Falta CLIMA_PDIRNOW_URL en el entorno (ver despliegue/produccion/env.ejemplo)")
    return r


def url_de(hora: dt.datetime) -> str:
    return f"{raiz()}/{hora:%Y}/pdirnow1h{hora:%y%m%d%H}.bin.gz"


def bajar(hora: dt.datetime) -> bytes | None:
    """El archivo de la hora que EMPIEZA en `hora` (UTC). None si todavía no existe."""
    try:
        with urllib.request.urlopen(urllib.request.Request(url_de(hora), headers={"User-Agent": UA}), timeout=TIMEOUT_S) as r:
            return r.read()
    except urllib.error.HTTPError as e:
        if e.code in (403, 404):
            return None
        raise


# ── Salida ───────────────────────────────────────────────────────────────────
def iso(t: dt.datetime) -> str:
    return t.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _t(s: str) -> dt.datetime:
    return dt.datetime.fromisoformat(s.replace("Z", "+00:00"))


def leer_salida(salida) -> dict:
    ruta = Path(salida) / NOMBRE
    try:
        return json.loads(ruta.read_text())
    except (OSError, ValueError):
        return {}


def escribir(salida, datos: dict) -> Path:
    """Escritura atómica: la API puede estar sirviendo el archivo mientras se rehace."""
    ruta = Path(salida) / NOMBRE
    ruta.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=ruta.parent, prefix=".pdirnow-", suffix=".json")
    with os.fdopen(fd, "w") as f:
        json.dump(datos, f, ensure_ascii=False, separators=(",", ":"))
    os.chmod(tmp, 0o644)
    os.replace(tmp, ruta)
    return ruta


def horas_esperadas(ahora: dt.datetime, n=HORAS_GUARDADAS):
    """Horas de inicio (UTC) que ya deberían existir, de la más reciente a la más vieja."""
    ultima = (ahora - dt.timedelta(hours=1, minutes=LATENCIA_MIN)).replace(minute=0, second=0, microsecond=0)
    return [ultima - dt.timedelta(hours=i) for i in range(n)]


def hora_desde_recorte(hora: dt.datetime, r: dict, zonas: dict) -> dict:
    plano = bytes(codificar(v) for fila in r["mmh"] for v in fila)
    return {"inicio": iso(hora), "fin": iso(hora + dt.timedelta(hours=1)),
            "b64": base64.b64encode(plano).decode("ascii"), "zonas": por_zona(r, zonas)}


def actualizar(salida, zonas: dict, ahora: dt.datetime | None = None, bajar_=None) -> dict:
    """Baja las horas que falten (la más reciente en cada pasada; las viejas, cada REINTENTO_VIEJAS_MIN)
    y reescribe pdirnow.json. Devuelve {"nuevas": [...], "faltan": [...], "errores": [...]}."""
    ahora = ahora or dt.datetime.now(UTC)
    bajar_ = bajar_ or bajar
    previo = leer_salida(salida)
    horas = {h["inicio"]: h for h in previo.get("horas", [])}
    intentos = previo.get("intentos", {})
    esperadas = horas_esperadas(ahora)
    nuevas, faltan, errores = [], [], []
    for i, hora in enumerate(esperadas):
        clave = iso(hora)
        if clave in horas:
            continue
        ultimo = intentos.get(clave)
        if i > 0 and ultimo and ahora - _t(ultimo) < dt.timedelta(minutes=REINTENTO_VIEJAS_MIN):
            faltan.append(clave)
            continue
        intentos[clave] = iso(ahora)
        try:
            datos = bajar_(hora)
        except Exception as e:  # red caída: se reintenta en la próxima pasada
            errores.append(f"{clave}: {type(e).__name__}: {str(e)[:100]}")
            faltan.append(clave)
            continue
        if datos is None:
            faltan.append(clave)
            continue
        try:
            horas[clave] = hora_desde_recorte(hora, leer_gz(datos), zonas)
            nuevas.append(clave)
        except Exception as e:
            errores.append(f"{clave}: {type(e).__name__}: {str(e)[:100]}")
            faltan.append(clave)
    corte = iso(esperadas[-1])
    guardadas = sorted((h for k, h in horas.items() if k >= corte), key=lambda h: h["inicio"])
    f0, f1, c0, c1 = ventana()
    lat_n, lon_o = centro(f0, c0)
    escribir(salida, {
        "generado": iso(ahora),
        "fuente": FUENTE,
        "advertencia": ADVERTENCIA,
        "unidad": "mm/h (promedio de la hora)",
        "codificacion": "un byte por celda, de norte a sur y de oeste a este; mm/h = (b / 10)²; 255 = sin dato",
        "paso": PASO, "filas": f1 - f0 + 1, "columnas": c1 - c0 + 1,
        # Bordes del recorte (no centros): centro de la primera celda ± medio paso
        "norte": round(lat_n + PASO / 2, 4), "oeste": round(lon_o - PASO / 2, 4),
        "sur": round(lat_n - PASO * (f1 - f0) - PASO / 2, 4), "este": round(lon_o + PASO * (c1 - c0) + PASO / 2, 4),
        "anillo_km": ANILLO_KM,
        "horas": guardadas,
        "intentos": {k: v for k, v in intentos.items() if k >= corte},
    })
    return {"nuevas": nuevas, "faltan": faltan, "errores": errores}

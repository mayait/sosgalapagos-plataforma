"""El mar: pleamares y bajamares de la tabla oficial del INOCAR, y oleaje y mareas de Stormglass.

Los endpoints van en variables de entorno (nunca en el repositorio):
  CLIMA_INOCAR_MAREAS_URL   dirección de la tabla diaria, con {cp} y {fecha}
  CLIMA_STORMGLASS_API      dirección base de la API
  CLIMA_STORMGLASS_LLAVES   llaves separadas por comas (cada una da 10 llamadas al día)
"""
import html
import json
import re
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone

from django.conf import settings

from .consultas import GALAPAGOS
from .models import Corrida, MareaExtremo, MarHora

# Puertos con tabla del INOCAR (su código) y punto para Stormglass. `zona` es la isla de los avisos.
PUERTOS = {
    "santa-cruz": {"nombre": "Puerto Ayora (Santa Cruz)", "zona": "santa-cruz", "inocar": 30, "lat": -0.748, "lon": -90.311},
    "san-cristobal": {"nombre": "Puerto Baquerizo Moreno (San Cristóbal)", "zona": "san-cristobal", "inocar": 387, "lat": -0.901, "lon": -89.612},
    "isabela": {"nombre": "Puerto Villamil (Isabela)", "zona": "isabela", "inocar": 394, "lat": -0.962, "lon": -90.965},
    "baltra": {"nombre": "Baltra", "zona": "santa-cruz", "inocar": 385, "lat": -0.436, "lon": -90.285},
}
CUPO_DIARIO = 9  # de las 10 llamadas de cada llave de Stormglass se deja una de margen


def _bajar(url, cabeceras=None, espera=30):
    pedido = urllib.request.Request(url, headers={"User-Agent": "sosgalapagos.org (clima; contacto en el sitio)", **(cabeceras or {})})
    with urllib.request.urlopen(pedido, timeout=espera) as r:
        return r.read()


def _corrida(fuente, t0, ok, registros=0, error=""):
    Corrida.objects.update_or_create(fuente=fuente, ts=datetime.now(timezone.utc),
                                     defaults={"ok": ok, "registros": registros, "segundos": round(time.monotonic() - t0, 2), "error": str(error)[:500]})


# ── INOCAR: tabla oficial ────────────────────────────────────────────────────
def leer_tabla_inocar(pagina):
    """[(ts en UTC, 'P'|'B', metros)] de la página diaria (trae ayer, hoy y mañana, en hora de Galápagos)."""
    texto = re.sub(r"<script.*?</script>|<style.*?</style>", "", pagina, flags=re.S)
    salida, dia = [], None
    for fila in re.findall(r"<tr[^>]*>(.*?)</tr>", texto, re.S):
        celdas = [html.unescape(re.sub(r"<[^>]+>", "", c)).strip() for c in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", fila, re.S)]
        if len(celdas) == 1 and (m := re.match(r"(\d{2})/(\d{2})/(\d{4})", celdas[0])):
            dia = (int(m.group(3)), int(m.group(2)), int(m.group(1)))
        elif dia and len(celdas) == 2 and (h := re.match(r"(\d{1,2}):(\d{2})$", celdas[0])) and (a := re.match(r"(-?\d+(?:\.\d+)?)\s*([PB])$", celdas[1])):
            local = datetime(*dia, int(h.group(1)), int(h.group(2)), tzinfo=GALAPAGOS)
            salida.append((local.astimezone(timezone.utc), a.group(2), float(a.group(1))))
    return salida


def guardar_mareas(puerto, extremos, fuente, datum):
    filas = [MareaExtremo(puerto=puerto, ts=ts, tipo=tipo, altura_m=altura, fuente=fuente, datum=datum) for ts, tipo, altura in extremos]
    return len(MareaExtremo.objects.bulk_create(filas, update_conflicts=True, unique_fields=["puerto", "fuente", "ts"], update_fields=["tipo", "altura_m", "datum"]))


def actualizar_inocar(dias=9, hoy=None):
    """Baja la tabla de los próximos días de los cuatro puertos. Devuelve cuántos extremos guardó."""
    if not settings.CLIMA_INOCAR_MAREAS_URL:
        return 0
    t0, total, error = time.monotonic(), 0, ""
    hoy = hoy or datetime.now(GALAPAGOS).date()
    for puerto, p in PUERTOS.items():
        for salto in range(0, dias, 3):  # cada página trae tres días
            fecha = hoy + timedelta(days=salto)
            try:
                pagina = _bajar(settings.CLIMA_INOCAR_MAREAS_URL.format(cp=p["inocar"], fecha=fecha.isoformat())).decode("utf-8", "replace")
                total += guardar_mareas(puerto, leer_tabla_inocar(pagina), "inocar", "MLWS")
            except Exception as e:  # la página del INOCAR falla a veces: se sigue con el resto
                error = f"{puerto} {fecha}: {type(e).__name__}"
    _corrida("inocar_mareas", t0, bool(total), total, error)
    return total


# ── Stormglass ───────────────────────────────────────────────────────────────
def _llave_stormglass(ahora=None):
    """La primera llave que aún tiene cupo hoy (día UTC). El gasto se cuenta en las corridas."""
    ahora = ahora or datetime.now(timezone.utc)
    inicio = ahora.replace(hour=0, minute=0, second=0, microsecond=0)
    for i, llave in enumerate(k.strip() for k in settings.CLIMA_STORMGLASS_LLAVES.split(",") if k.strip()):
        if Corrida.objects.filter(fuente=f"stormglass_{i + 1}", ts__gte=inicio).count() < CUPO_DIARIO:
            return i + 1, llave
    return None, None


def _stormglass(ruta):
    n, llave = _llave_stormglass()
    if not llave or not settings.CLIMA_STORMGLASS_API:
        return None
    t0 = time.monotonic()
    try:
        datos = json.loads(_bajar(settings.CLIMA_STORMGLASS_API.rstrip("/") + ruta, {"Authorization": llave}, espera=45))
        _corrida(f"stormglass_{n}", t0, True, len(datos.get("data") or datos.get("hours") or []))
        return datos
    except urllib.error.HTTPError as e:
        _corrida(f"stormglass_{n}", t0, False, error=f"HTTP {e.code}")  # también gasta cupo
    except Exception as e:
        _corrida(f"stormglass_{n}", t0, False, error=type(e).__name__)
    return None


def _z(t):
    return t.strftime("%Y-%m-%dT%H:%M:%SZ")


def actualizar_stormglass_mareas(puertos=("san-cristobal", "isabela", "santa-cruz"), ahora=None):
    """Pleamares y bajamares de los próximos 10 días (una llamada por puerto). Nivel medio del mar (MSL)."""
    ahora = (ahora or datetime.now(timezone.utc)).replace(minute=0, second=0, microsecond=0)
    total = 0
    for puerto in puertos:
        p = PUERTOS[puerto]
        d = _stormglass(f"/tide/extremes/point?lat={p['lat']}&lng={p['lon']}&start={_z(ahora - timedelta(hours=12))}&end={_z(ahora + timedelta(days=10))}")
        if d and d.get("data"):
            total += guardar_mareas(puerto, [(datetime.fromisoformat(e["time"]), "P" if e["type"] == "high" else "B", round(e["height"], 3)) for e in d["data"]],
                                    "stormglass", (d.get("meta") or {}).get("datum") or "MSL")
    return total


PARAMETROS = {"waveHeight": "ola_m", "swellHeight": "fondo_m", "swellPeriod": "periodo_s", "swellDirection": "direccion", "windSpeed": "viento_ms",
              "gust": "racha_ms", "seaLevel": "nivel_m", "waterTemperature": "agua_c", "precipitation": "lluvia_mm"}


def actualizar_stormglass_mar(puertos=("san-cristobal", "isabela", "santa-cruz"), dias=5, ahora=None):
    """Oleaje, mar de fondo, viento y nivel del mar hora a hora (una llamada por puerto)."""
    ahora = (ahora or datetime.now(timezone.utc)).replace(minute=0, second=0, microsecond=0)
    total = 0
    for puerto in puertos:
        p = PUERTOS[puerto]
        d = _stormglass(f"/weather/point?lat={p['lat']}&lng={p['lon']}&start={_z(ahora)}&end={_z(ahora + timedelta(days=dias))}&params={','.join(PARAMETROS)}")
        if not d or not d.get("hours"):
            continue
        filas = []
        for h in d["hours"]:
            valores = {campo: (h.get(nombre) or {}).get("sg") for nombre, campo in PARAMETROS.items()}
            filas.append(MarHora(puerto=puerto, hora=datetime.fromisoformat(h["time"]), obtenido=ahora, **valores))
        total += len(MarHora.objects.bulk_create(filas, update_conflicts=True, unique_fields=["puerto", "hora"], update_fields=list(PARAMETROS.values()) + ["obtenido"]))
    return total


# ── Lectura ──────────────────────────────────────────────────────────────────
def resumen(ahora=None):
    """Para cada puerto: las próximas pleamares y bajamares (oficiales si las hay) y el mar de las próximas 72 h."""
    ahora = ahora or datetime.now(timezone.utc)
    salida = []
    for puerto, p in PUERTOS.items():
        fuente = "inocar" if MareaExtremo.objects.filter(puerto=puerto, fuente="inocar", ts__gte=ahora).exists() else "stormglass"
        extremos = list(MareaExtremo.objects.filter(puerto=puerto, fuente=fuente, ts__gte=ahora - timedelta(hours=6), ts__lte=ahora + timedelta(days=4)))
        horas = list(MarHora.objects.filter(puerto=puerto, hora__gte=ahora, hora__lte=ahora + timedelta(hours=72)))
        olas = [h.ola_m for h in horas if h.ola_m is not None]
        pico = max(horas, key=lambda h: h.ola_m or 0) if olas else None
        salida.append({
            "puerto": puerto, "nombre": p["nombre"], "zona": p["zona"],
            "mareas": {"fuente": "INOCAR, tabla oficial" if fuente == "inocar" else "Stormglass (estación NOAA cercana)",
                       "referencia": extremos[0].datum if extremos else "", "hora": "Galápagos (UTC−6)",
                       "extremos": [{"ts": e.ts, "local": e.ts.astimezone(GALAPAGOS).strftime("%a %d %H:%M"), "tipo": "pleamar" if e.tipo == "P" else "bajamar", "altura_m": e.altura_m} for e in extremos]},
            "mar_72h": {"ola_max_m": round(max(olas), 1), "cuando": pico.hora, "mar_de_fondo_m": pico.fondo_m, "periodo_s": pico.periodo_s,
                        "agua_c": horas[0].agua_c, "obtenido": horas[0].obtenido} if olas else None,
        })
    return {"generado": ahora, "aviso": "Predicciones y modelos, no mediciones. La tabla del INOCAR es la oficial; lo demás es orientativo. No reemplaza los avisos de la Armada.", "puertos": salida}

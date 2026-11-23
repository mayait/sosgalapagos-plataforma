# SOS Galápagos · © 2026 Universidad San Francisco de Quito (USFQ) · Autor: Julián Maya <jamaya@usfq.edu.ec>
# Todos los derechos reservados. Usar, copiar, modificar o derivar de este código requiere permiso escrito del autor (ver LICENSE).
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
        # El encabezado del día trae a veces una celda vacía de más («24/11/2026Martes», «»). Antes solo se
        # aceptaba con una celda: ese día se guardaba con la fecha del anterior.
        if not any(celdas[1:]) and celdas and (m := re.match(r"(\d{2})/(\d{2})/(\d{4})", celdas[0])):
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
        # Una página por día. Dicen traer ayer, hoy y mañana, pero no siempre: la del 25-nov-2026 empezaba
        # el 25, y con una página cada tres días el 24 quedó sin pedir y la curva de marea salía cortada.
        for salto in range(0, dias):
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
            filas.append(MarHora(puerto=puerto, fuente="stormglass", hora=datetime.fromisoformat(h["time"]), obtenido=ahora, **valores))
        total += len(MarHora.objects.bulk_create(filas, update_conflicts=True, unique_fields=["puerto", "fuente", "hora"], update_fields=list(PARAMETROS.values()) + ["obtenido"]))
    return total


DIAS = ("lun", "mar", "mié", "jue", "vie", "sáb", "dom")


def _local(ts):
    t = ts.astimezone(GALAPAGOS)
    return f"{DIAS[t.weekday()]} {t.day} {t:%H:%M}"


# ── Lectura ──────────────────────────────────────────────────────────────────
def resumen(ahora=None):
    """Para cada puerto: las próximas pleamares y bajamares (oficiales si las hay) y el mar de las próximas 72 h."""
    ahora = ahora or datetime.now(timezone.utc)
    salida = []
    for puerto, p in PUERTOS.items():
        fuente_marea = "inocar" if MareaExtremo.objects.filter(puerto=puerto, fuente="inocar", ts__gte=ahora).exists() else "stormglass"
        extremos = list(MareaExtremo.objects.filter(puerto=puerto, fuente=fuente_marea, ts__gte=ahora - timedelta(hours=6), ts__lte=ahora + timedelta(days=4)))
        # El mar de las próximas 72 horas: Stormglass; si no tiene datos de este puerto, el modelo de Open-Meteo.
        horas, modelo = [], ""
        for fuente, etiqueta in (("stormglass", "Stormglass"), ("openmeteo", "Open-Meteo Marine")):
            horas = list(MarHora.objects.filter(puerto=puerto, fuente=fuente, hora__gte=ahora - timedelta(hours=1), hora__lte=ahora + timedelta(hours=72), ola_m__isnull=False).order_by("hora"))
            if horas:
                modelo = etiqueta
                break
        olas = [h.ola_m for h in horas]
        pico = max(horas, key=lambda h: h.ola_m) if horas else None
        r1 = lambda v: None if v is None else round(v, 1)  # noqa: E731
        salida.append({
            "puerto": puerto, "nombre": p["nombre"], "zona": p["zona"],
            "mareas": {"fuente": "INOCAR, tabla oficial" if fuente_marea == "inocar" else "Stormglass (estación NOAA cercana)",
                       "referencia": extremos[0].datum if extremos else "", "hora": "Galápagos (UTC−6)",
                       "extremos": [{"ts": e.ts, "local": _local(e.ts), "tipo": "pleamar" if e.tipo == "P" else "bajamar", "altura_m": e.altura_m} for e in extremos]},
            "mar_72h": {"modelo": modelo, "ola_max_m": round(max(olas), 1), "cuando": pico.hora, "mar_de_fondo_m": pico.fondo_m, "periodo_s": pico.periodo_s,
                        "agua_c": horas[0].agua_c, "obtenido": horas[0].obtenido,
                        # Hora a hora, para dibujarlo: [hora, ola, mar de fondo, período, viento, racha, dirección del mar de fondo]
                        "horas": [[h.hora, r1(h.ola_m), r1(h.fondo_m), r1(h.periodo_s), r1(h.viento_ms), r1(h.racha_ms), None if h.direccion is None else round(h.direccion)] for h in horas]} if horas else None,
        })
    return {"generado": ahora, "aviso": "Predicciones y modelos, no mediciones. La tabla del INOCAR es la oficial; lo demás es orientativo. No reemplaza los avisos de la Armada.", "puertos": salida}

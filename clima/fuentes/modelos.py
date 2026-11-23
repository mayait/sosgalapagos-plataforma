# SOS Galápagos · © 2026 Universidad San Francisco de Quito (USFQ) · Autor: Julián Maya <jamaya@usfq.edu.ec>
# Licencia Apache 2.0 (ver LICENSE y NOTICE): puede reutilizarse dando crédito.
"""Pronósticos de lluvia de los modelos globales (Open-Meteo), guardados en la base.

Cada hora se piden los modelos deterministas (una sola petición con todos) y, de los
conjuntos, solo las corridas nuevas. De cada respuesta se guarda un resumen por punto en
PronosticoCorrida: una fila por modelo y corrida, así queda la historia de lo que dijo cada
modelo y cuándo lo dijo.

De los deterministas se guarda también el CAPE (energía disponible para la convección, J/kg): el
máximo del día, para evaluarlo con un archivo propio (pronostico/fase0/cape.md del repositorio de
datos). Todavía no entra en la señal. A los conjuntos no se les pide: su costo en llamadas crece con
el número de miembros.

Son modelos, NO un dato oficial ni una alerta. La señal que se publica se calcula en clima/senal.py.
En el entorno: CLIMA_OPENMETEO_FORECAST_API y CLIMA_OPENMETEO_ENSEMBLE_API.
"""
import datetime as dt
import json
import urllib.parse
from pathlib import Path

from . import base

FUENTE = "pronostico"
ZONAS = json.loads((Path(__file__).resolve().parent.parent / "datos" / "zonas_geo.json").read_text())["zonas"]
DIAS = 5  # hoy y 4 días más (la señal se evaluó hasta 5 días de anticipación)

# Deterministas: identificador en la API → (nombre, identificador de sus metadatos, para saber la hora de la corrida)
DETERMINISTAS = {
    "ecmwf_ifs025": ("ECMWF IFS 0,25°", "ecmwf_ifs025"),
    "ecmwf_aifs025_single": ("ECMWF AIFS (IA)", "ecmwf_aifs025_single"),
    "gfs_seamless": ("NOAA GFS", "ncep_gfs013"),
    "icon_seamless": ("DWD ICON", "dwd_icon"),
    "ukmo_seamless": ("UK Met Office", "ukmo_global_deterministic_10km"),
    "meteofrance_seamless": ("Météo-France ARPEGE", "meteofrance_arpege_world025"),
    "gem_seamless": ("Canadá GEM", "cmc_gem_gdps"),
    "ecmwf_ifs": ("ECMWF IFS 9 km", "ecmwf_ifs"),  # no entra en el consenso: se muestra hora a hora
}
DETALLE = "ecmwf_ifs"
# Variables horarias de los deterministas. El costo en llamadas es variables × modelos / 10 por punto
# (mínimo 1): con 8 modelos, «precipitation» sola pesa 1 por punto; con «cape», 1,6.
VARIABLES_DETERMINISTAS = "precipitation,cape"
CAPE_HORAS_MINIMAS = 20  # un día de CAPE cuenta si tiene al menos 20 de sus 24 horas
# Conjuntos: identificador en la API, identificador de metadatos, nombre, miembros
CONJUNTOS = [
    ("ecmwf_ifs025", "ecmwf_ifs025_ensemble", "ECMWF IFS ENS", 51),
    ("ecmwf_aifs025", "ecmwf_aifs025_ensemble", "ECMWF AIFS ENS (IA)", 51),
    ("gfs025", "ncep_gefs025", "NOAA GEFS", 31),
    ("icon_global", "dwd_icon_eps", "DWD ICON-EPS", 40),
    ("ukmo_global_ensemble_20km", "ukmo_global_ensemble_20km", "UK Met Office MOGREPS-G", 18),
]


def puntos():
    return [(z, p) for z, zona in ZONAS.items() for p in zona["puntos"]]


def _metadatos(api, identificador, ahora):
    """(inicio de la corrida, disponible desde), o (None, None) si no se sabe: algunos metadatos quedan viejos."""
    u = urllib.parse.urlsplit(api)
    try:
        m = base.http_json(f"{u.scheme}://{u.netloc}/data/{identificador}/static/meta.json", espera=30)
        inicio = dt.datetime.fromtimestamp(m["last_run_initialisation_time"], base.UTC)
        disponible = dt.datetime.fromtimestamp(m["last_run_availability_time"], base.UTC)
    except Exception:
        return None, None
    if (ahora - inicio).total_seconds() > 36 * 3600:
        return None, None
    return inicio, disponible


def _pedir(api, modelos, variables="precipitation"):
    pts = puntos()
    q = {"latitude": ",".join(str(p["lat"]) for _, p in pts), "longitude": ",".join(str(p["lon"]) for _, p in pts),
         "hourly": variables, "models": ",".join(modelos), "timezone": "GMT", "past_days": 1, "forecast_days": DIAS + 1}
    d = base.http_json(f"{api}?{urllib.parse.urlencode(q)}", espera=120)
    return d if isinstance(d, list) else [d]


def _claves_locales(t_iso):
    """La lluvia de una hora es la suma de la hora que TERMINA en t; cuenta para el día y el bloque de
    6 horas (hora de Galápagos) en que EMPIEZA esa hora."""
    local = (dt.datetime.fromisoformat(t_iso).replace(tzinfo=base.UTC) - dt.timedelta(hours=1)).astimezone(base.GALAPAGOS)
    return local.strftime("%Y-%m-%d"), f"{local:%Y-%m-%d}T{local.hour // 6 * 6:02d}"


def sumar(horas, valores_por_hora, horas_dia=24, horas_bloque=6):
    """valores_por_hora: por cada hora, una lista con el valor de cada serie. Devuelve los totales por día
    y por bloque de 6 horas, solo de los que están completos y sin huecos."""
    dias, bloques = {}, {}
    for t, fila in zip(horas, valores_por_hora):
        d, b = _claves_locales(t)
        for destino, clave in ((dias, d), (bloques, b)):
            a = destino.setdefault(clave, {"n": 0, "v": [0.0] * len(fila), "nulos": False})
            a["n"] += 1
            if any(x is None for x in fila):
                a["nulos"] = True
            else:
                a["v"] = [s + x for s, x in zip(a["v"], fila)]
    completo = lambda a, h: a["n"] >= h and not a["nulos"]  # noqa: E731
    return ({k: [round(x, 2) for x in a["v"]] for k, a in sorted(dias.items()) if completo(a, horas_dia)},
            {k: [round(x, 2) for x in a["v"]] for k, a in sorted(bloques.items()) if completo(a, horas_bloque)})


def maximos_diarios(horas, serie, horas_minimas=CAPE_HORAS_MINIMAS):
    """Máximo por día de Galápagos de una variable instantánea (el CAPE): el valor de la hora t cuenta
    para el día local de t, sin restar la hora que sí se resta a la lluvia (que es la suma de la hora
    que termina en t). Solo los días con al menos `horas_minimas` horas con dato."""
    dias = {}
    for t, x in zip(horas, serie):
        if x is None:
            continue
        d = (dt.datetime.fromisoformat(t).replace(tzinfo=base.UTC)).astimezone(base.GALAPAGOS).strftime("%Y-%m-%d")
        dias.setdefault(d, []).append(x)
    return {d: round(max(v)) for d, v in sorted(dias.items()) if len(v) >= horas_minimas}


def resumen_determinista(modelo, respuesta):
    """{punto: {dias: {fecha: mm}, cape_max?: {fecha: J/kg}, horario?}} de un modelo, a partir de la respuesta con todos."""
    salida = {}
    for (_, p), r in zip(puntos(), respuesta):
        h = r.get("hourly", {})
        serie = h.get(f"precipitation_{modelo}")
        if not serie:
            continue
        dias, _ = sumar(h["time"], [[x] for x in serie])
        salida[p["id"]] = {"dias": {k: v[0] for k, v in dias.items()}}
        cape = h.get(f"cape_{modelo}")
        if cape and any(x is not None for x in cape):  # AIFS no da CAPE: se omite la clave
            salida[p["id"]]["cape_max"] = maximos_diarios(h["time"], cape)
        if modelo == DETALLE:
            salida[p["id"]]["horario"] = {"t": h["time"], "mm": serie}
    return salida


def resumen_conjunto(respuesta):
    """{punto: {dias: {fecha: [mm de cada miembro]}, bloques6h: {…}}}."""
    salida = {}
    for (_, p), r in zip(puntos(), respuesta):
        h = r.get("hourly", {})
        claves = sorted((k for k in h if k.startswith("precipitation")), key=lambda k: (k != "precipitation", k))
        dias, bloques = sumar(h.get("time", []), list(zip(*[h[k] for k in claves])) if claves else [])
        salida[p["id"]] = {"dias": dias, "bloques6h": bloques}
    return salida


def _guardar(modelo, tipo, corrida, disponible, ahora, datos):
    from ..models import PronosticoCorrida

    # Sin hora de corrida conocida, la referencia es el bloque de 6 horas en que se recibió.
    referencia = corrida or ahora.replace(hour=ahora.hour // 6 * 6, minute=0, second=0, microsecond=0)
    _, creada = PronosticoCorrida.objects.update_or_create(
        modelo=modelo, tipo=tipo, referencia=referencia, defaults={"corrida": corrida, "disponible": disponible, "recibido": ahora, "datos": datos})
    return creada


def recoger(ahora=None, forzar=False):
    """Devuelve cuántos modelos trajeron una corrida nueva. Una vez por hora basta."""
    from ..models import PronosticoCorrida

    ahora = ahora or dt.datetime.now(base.UTC)
    ultima = PronosticoCorrida.objects.order_by("-recibido").values_list("recibido", flat=True).first()
    if not forzar and ultima and (ahora - ultima).total_seconds() < 3300:
        return 0
    nuevos, errores = 0, []

    # 1) Deterministas: una sola petición con todos los modelos.
    try:
        api = base.endpoint("CLIMA_OPENMETEO_FORECAST_API")
        respuesta = _pedir(api, list(DETERMINISTAS), VARIABLES_DETERMINISTAS)
        for modelo, (_, identificador) in DETERMINISTAS.items():
            datos = resumen_determinista(modelo, respuesta)
            if datos:
                nuevos += _guardar(modelo, "determinista", *_metadatos(api, identificador, ahora), ahora, datos)
    except Exception as e:
        errores.append(f"deterministas: {type(e).__name__}: {e}"[:200])

    # 2) Conjuntos: solo si hay corrida nueva (o cada 6 horas si la hora de la corrida no se conoce).
    for modelo, identificador, _, _ in CONJUNTOS:
        try:
            api = base.endpoint("CLIMA_OPENMETEO_ENSEMBLE_API")
            corrida, disponible = _metadatos(api, identificador, ahora)
            previa = PronosticoCorrida.objects.filter(modelo=modelo, tipo="conjunto").order_by("-recibido").first()
            if previa and corrida and previa.corrida == corrida:
                continue
            if previa and not corrida and (ahora - previa.recibido).total_seconds() < 6 * 3600:
                continue
            nuevos += _guardar(modelo, "conjunto", corrida, disponible, ahora, resumen_conjunto(_pedir(api, [modelo])))
        except Exception as e:  # un modelo caído no detiene a los demás
            errores.append(f"{modelo}: {type(e).__name__}: {e}"[:200])
    if errores and len(errores) == 1 + len(CONJUNTOS):
        raise RuntimeError("; ".join(errores))
    return nuevos

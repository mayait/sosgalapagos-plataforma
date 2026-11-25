# SOS Galápagos · © 2026 Universidad San Francisco de Quito (USFQ) · Autor: Julián Maya <jamaya@usfq.edu.ec>
# Licencia Apache 2.0 (ver LICENSE y NOTICE): puede reutilizarse dando crédito.
"""Mapa de lluvia y viento de los modelos (tipo Windy) para el panel de /clima/.

Baja de Open-Meteo una rejilla regular sobre Galápagos (por defecto 0,125°) con la lluvia cada 3 horas
y el viento a 10 m de varios modelos, y escribe un JSON compacto (`lluvia-mapa.json`) que dibuja
`clima/web/lluvia-mapa.js` del repositorio de datos.

Todo esto es lluvia de MODELO, no medida ni oficial. Los modelos globales se quedan cortos por
35–45 mm al día en las islas (no ven su relieve): el mapa lo dice a la vista. El pronóstico
oficial es del INAMHI.

Solo usa la biblioteca estándar (sin numpy ni Django), para poder correrlo fuera de la imagen:

    CLIMA_OPENMETEO_FORECAST_API=… python3 -I clima/lluvia_mapa.py salida/

El endpoint sale de CLIMA_OPENMETEO_FORECAST_API (el mismo del pronóstico). Nunca va en el código.

Costo en llamadas de Open-Meteo: cada ubicación pesa max(1, variables × modelos / 10). Con
3 variables × 3 modelos = 9, cada punto pesa 1, así que una rejilla de 29 × 33 = 957 puntos
gasta 957 llamadas por refresco. Por eso solo se refresca cuando cambia la corrida del IFS
(ver `hay_corrida_nueva`) y la petición se parte en trozos con pausa, para no pasar de
600 llamadas por minuto.
"""
import base64
import datetime as dt
import json
import math
import os
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

UTC = dt.timezone.utc
UA = "sosgalapagos-clima/1.0"
NOMBRE = "lluvia-mapa.json"

# Recuadro del mapa (grados): sur, norte, oeste, este
CAJA = (-2.0, 1.5, -92.5, -88.5)
PASO = 0.125
HORAS = 120          # horas de pronóstico desde ahora
HORAS_ANTES = 24     # se guardan 24 h antes de ahora, solo para el acumulado de 24 h
TROZO = 240          # ubicaciones por petición (cada una pesa 1 llamada)
PAUSA_S = 30         # entre trozos: 240 cada 30 s = 480 por minuto, bajo el límite de 600
MINIMO_H = 5         # nunca se refresca más seguido, aunque haya corrida nueva
SIN_META_H = 12      # si los metadatos no responden, solo se refresca cuando el archivo pasa de esta edad

# id en la API de pronóstico → (nombre, id de metadatos para la hora de corrida)
MODELOS = {
    "ecmwf_ifs": ("ECMWF IFS 9 km", "ecmwf_ifs"),
    "gfs_seamless": ("NOAA GFS", "ncep_gfs013"),
    "icon_seamless": ("DWD ICON", "dwd_icon"),
}
REFERENCIA = "ecmwf_ifs"  # su corrida decide si hay que refrescar
VARIABLES = ("precipitation", "wind_speed_10m", "wind_direction_10m")


# ── Codificación: un byte por celda, 255 = sin dato ─────────────────────────
def codificar_lluvia(mm):
    """mm en 3 h → byte. mm = (b / 10)²: 0,01 mm de resolución abajo, ≈ 1,4 mm a 50 mm, hasta 645 mm."""
    if mm is None or mm != mm:
        return 255
    return min(254, round(10 * math.sqrt(max(0.0, mm))))


def codificar_viento(c):
    """Componente en m/s → byte. m/s = (b − 128) / 4: ±31,75 m/s con 0,25 m/s de resolución."""
    if c is None or c != c:
        return 255
    return max(0, min(254, round(c * 4) + 128))


def componentes(rapidez, direccion):
    """(u, v) en m/s. La dirección es de DÓNDE viene el viento (convención meteorológica)."""
    if rapidez is None or direccion is None:
        return None, None
    r = math.radians(direccion)
    return -rapidez * math.sin(r), -rapidez * math.cos(r)


def _b64(bytes_):
    return base64.b64encode(bytes(bytes_)).decode("ascii")


# ── Rejilla ─────────────────────────────────────────────────────────────────
def rejilla(caja=CAJA, paso=PASO):
    """Puntos de norte a sur y de oeste a este (el orden que espera el navegador)."""
    sur, norte, oeste, este = caja
    nlat = round((norte - sur) / paso) + 1
    nlon = round((este - oeste) / paso) + 1
    lats = [round(norte - i * paso, 4) for i in range(nlat)]
    lons = [round(oeste + j * paso, 4) for j in range(nlon)]
    return lats, lons


# ── Red ─────────────────────────────────────────────────────────────────────
def _endpoint():
    api = os.environ.get("CLIMA_OPENMETEO_FORECAST_API", "")
    if not api:
        raise RuntimeError("Falta CLIMA_OPENMETEO_FORECAST_API (ver clima/fuentes.env.ejemplo del repo de datos)")
    return api


def _http_json(url, datos=None, timeout=120):
    cuerpo = urllib.parse.urlencode(datos).encode() if datos else None
    pet = urllib.request.Request(url, data=cuerpo, headers={"User-Agent": UA})
    with urllib.request.urlopen(pet, timeout=timeout) as r:
        return json.loads(r.read())


def corrida(api, meta_id):
    """(inicio, disponible) de la última corrida de un modelo, o (None, None)."""
    u = urllib.parse.urlsplit(api)
    try:
        m = _http_json(f"{u.scheme}://{u.netloc}/data/{meta_id}/static/meta.json", timeout=30)
        return (dt.datetime.fromtimestamp(m["last_run_initialisation_time"], UTC),
                dt.datetime.fromtimestamp(m["last_run_availability_time"], UTC))
    except Exception:
        return None, None


def _iso(t):
    return t.strftime("%Y-%m-%dT%H:%MZ") if t else None


def hay_corrida_nueva(destino, api=None, ahora=None):
    """True si conviene refrescar: hay una corrida nueva del modelo de referencia.

    Cuida la cuota, porque cada refresco gasta ≈ 957 llamadas:
    - nunca refresca si el archivo tiene menos de MINIMO_H horas;
    - si los metadatos no responden, solo refresca cuando el archivo pasa de SIN_META_H horas.
    Pedir los metadatos no gasta llamadas de la API.
    """
    archivo = _archivo(destino)
    if not archivo.exists():
        return True
    edad_h = ((ahora or time.time()) - archivo.stat().st_mtime) / 3600
    if edad_h < MINIMO_H:
        return False
    api = api or _endpoint()
    ini, _ = corrida(api, MODELOS[REFERENCIA][1])
    if ini is None:
        return edad_h >= SIN_META_H
    try:
        previo = json.loads(archivo.read_text())
        anterior = next(m["corrida"] for m in previo["modelos"] if m["id"] == REFERENCIA)
    except (OSError, ValueError, KeyError, StopIteration):
        return True
    return _iso(ini) != anterior


def _pedir(api, puntos, modelos, dias, pausa):
    """Una lista con la respuesta de cada punto, en el mismo orden."""
    salida = []
    for k in range(0, len(puntos), TROZO):
        if k:
            time.sleep(pausa)
        trozo = puntos[k:k + TROZO]
        q = {
            "latitude": ",".join(f"{la:g}" for la, _ in trozo),
            "longitude": ",".join(f"{lo:g}" for _, lo in trozo),
            "hourly": ",".join(VARIABLES), "models": ",".join(modelos),
            "temporal_resolution": "hourly_3",   # el valor en T es la lluvia de T−3 h a T
            "cell_selection": "nearest",         # sin esto los puntos de mar se van a la celda de tierra más cercana
            "wind_speed_unit": "ms", "timezone": "GMT",
            "past_days": 1, "forecast_days": dias,
        }
        d = _http_json(api, q, timeout=180)       # POST: la lista de coordenadas no cabe en la URL
        d = d if isinstance(d, list) else [d]
        if len(d) != len(trozo):
            raise RuntimeError(f"Open-Meteo devolvió {len(d)} puntos de {len(trozo)}")
        salida.extend(d)
    return salida


# ── Exportar ────────────────────────────────────────────────────────────────
def _archivo(destino):
    p = Path(destino)
    return p / NOMBRE if p.suffix != ".json" else p


def exportar(destino, ahora=None, modelos=None, caja=CAJA, paso=PASO, horas=HORAS, pausa=PAUSA_S, api=None):
    """Baja la rejilla y escribe el JSON en `destino` (carpeta o archivo .json). Devuelve la ruta.

    Gasta ≈ (número de puntos) llamadas de Open-Meteo: 957 con la rejilla por defecto.
    """
    api = api or _endpoint()
    ahora = (ahora or dt.datetime.now(UTC)).astimezone(UTC)
    modelos = list(modelos or MODELOS)
    lats, lons = rejilla(caja, paso)
    puntos = [(la, lo) for la in lats for lo in lons]
    corridas = {m: corrida(api, MODELOS[m][1]) for m in modelos}
    dias = math.ceil(horas / 24) + 1
    resp = _pedir(api, puntos, modelos, dias, pausa)

    # Horas comunes: del cuadro que contiene «ahora − 24 h» hasta «ahora + horas»
    tiempos = [dt.datetime.fromisoformat(t).replace(tzinfo=UTC) for t in resp[0]["hourly"]["time"]]
    desde = ahora - dt.timedelta(hours=HORAS_ANTES)
    hasta = ahora + dt.timedelta(hours=horas)
    elegidos = [i for i, t in enumerate(tiempos) if t > desde and t - dt.timedelta(hours=3) < hasta]
    # Primer cuadro que se muestra: el que termina después de ahora (el periodo en curso)
    inicio = next(n for n, i in enumerate(elegidos) if tiempos[i] > ahora)

    salida_modelos = []
    for m in modelos:
        lluvia, uu, vv = [], [], []
        hay_algo = False
        for i in elegidos:
            fl, fu, fv = [], [], []
            for r in resp:
                h = r["hourly"]
                mm = h.get(f"precipitation_{m}", [None] * len(tiempos))[i]
                u, v = componentes(h.get(f"wind_speed_10m_{m}", [None] * len(tiempos))[i],
                                   h.get(f"wind_direction_10m_{m}", [None] * len(tiempos))[i])
                hay_algo = hay_algo or mm is not None
                fl.append(codificar_lluvia(mm))
                fu.append(codificar_viento(u))
                fv.append(codificar_viento(v))
            lluvia.append(_b64(fl))
            uu.append(_b64(fu))
            vv.append(_b64(fv))
        if not hay_algo:
            continue
        ini, disp = corridas[m]
        salida_modelos.append({"id": m, "nombre": MODELOS[m][0], "corrida": _iso(ini), "disponible": _iso(disp),
                               "lluvia": lluvia, "u": uu, "v": vv})

    datos = {
        "version": 1,
        "generado": _iso(ahora),
        "aviso": ("Lluvia y viento de modelos globales, no medidos. En las islas los modelos se quedan cortos "
                  "por 35–45 mm al día. No es un pronóstico oficial: el oficial es del INAMHI."),
        "fuente": "Open-Meteo (CC BY 4.0) con datos de ECMWF, NOAA y DWD",
        # Filas de norte a sur, columnas de oeste a este: valor[fila * nlon + columna]
        "rejilla": {"norte": lats[0], "oeste": lons[0], "paso": paso, "nlat": len(lats), "nlon": len(lons)},
        "horas": [_iso(tiempos[i]) for i in elegidos],   # fin de cada periodo de 3 h, en UTC
        "paso_h": 3,
        "inicio": inicio,                                # índice del primer cuadro que se muestra
        "codificacion": {"lluvia": "mm en 3 h = (b/10)^2", "viento": "m/s = (b-128)/4", "sin_dato": 255},
        "modelos": salida_modelos,
    }
    archivo = _archivo(destino)
    archivo.parent.mkdir(parents=True, exist_ok=True)
    tmp = archivo.with_suffix(".tmp")
    tmp.write_text(json.dumps(datos, ensure_ascii=False, separators=(",", ":")))
    tmp.replace(archivo)
    return archivo


# ── Recorte ─────────────────────────────────────────────────────────────────
RECORTE_MINIMO_H = 6  # con menos horas por delante que estas no hay nada que animar


def recorte(datos, ahora=None, horas=24, modelo=REFERENCIA):
    """Lo que hace falta para animar las próximas `horas` con un solo modelo, o None si el archivo ya no las cubre.

    La portada anima 24 horas de un modelo: el archivo entero trae 6 días de tres modelos y pesa
    unas diez veces más. Tiene la misma forma que el archivo (lo dibuja el mismo `lluvia-mapa.js`), con
    menos cuadros, un solo modelo y `ahora`, la hora del servidor, por si el reloj del teléfono está mal.

    La lluvia de un cuadro es la de las 3 h que terminan en su hora; el viento, el de esa hora. Para
    interpolar de «ahora» a «ahora + horas» hacen falta un cuadro antes y uno después de ese tramo.
    """
    ahora = (ahora or dt.datetime.now(UTC)).astimezone(UTC)
    inicio = ahora.replace(minute=0, second=0, microsecond=0)
    tiempos = [dt.datetime.fromisoformat(h.replace("Z", "+00:00")) for h in datos.get("horas") or []]
    elegido = next((m for m in datos.get("modelos") or [] if m["id"] == modelo), None) or next(iter(datos.get("modelos") or []), None)
    if not tiempos or elegido is None or tiempos[-1] < inicio + dt.timedelta(hours=RECORTE_MINIMO_H):
        return None
    fin = inicio + dt.timedelta(hours=horas)
    primero = next(i for i, t in enumerate(tiempos) if t > inicio)                         # el periodo en curso
    ultimo = next((i for i, t in enumerate(tiempos) if t >= fin), len(tiempos) - 1)
    a, b = max(0, primero - 1), min(len(tiempos), ultimo + 2)
    salida = {k: v for k, v in datos.items() if k not in ("horas", "modelos", "inicio")}
    salida.update({
        "ahora": _iso(ahora),
        "horas": datos["horas"][a:b],
        "inicio": primero - a,
        "modelos": [{**elegido, "lluvia": elegido["lluvia"][a:b], "u": elegido["u"][a:b], "v": elegido["v"][a:b]}],
    })
    return salida


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit("uso: python3 -I clima/lluvia_mapa.py CARPETA_O_ARCHIVO [--horas N] [--paso 0.125] [--modelos a,b]")
    args = sys.argv[1:]
    def _opt(nombre, defecto):
        return args[args.index(nombre) + 1] if nombre in args else defecto
    ruta = exportar(args[0], horas=int(_opt("--horas", HORAS)), paso=float(_opt("--paso", PASO)),
                    modelos=_opt("--modelos", ",".join(MODELOS)).split(","))
    print(f"escrito {ruta} ({ruta.stat().st_size / 1024:.0f} KB)")

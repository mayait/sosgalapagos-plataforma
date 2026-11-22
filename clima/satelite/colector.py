# SOS Galápagos · © 2026 Universidad San Francisco de Quito (USFQ) · Autor: Julián Maya <jamaya@usfq.edu.ec>
# Todos los derechos reservados. Usar, copiar, modificar o derivar de este código requiere permiso escrito del autor (ver LICENSE).
"""Colector del satélite GOES-19 (ABI y GLM). Una pasada cada 5 minutos, en su propio proceso.

Qué hace en cada pasada:
1. ABI (disco completo cada 10 min): de cada barrido nuevo lee por rangos HTTP solo el recorte de
   Galápagos de la banda 13 (temperatura del tope de nube) y del RRQPE (lluvia estimada).
   Corrige el paralaje (la altura del tope sale de su temperatura), descarta los píxeles de mala
   calidad y guarda agregados por zona como mediciones de la fuente «goes».
2. GLM (archivos de 20 s): cuenta los destellos de calidad buena por zona en intervalos de 10 min.
   Rehace los intervalos recientes hasta tener sus 30 archivos.
3. Deja en la tabla Estado («satelite») el resumen público: últimas 3 horas por zona, destellos y
   núcleos fríos. El panel lo recibe dentro de estado.json.

Es una ESTIMACIÓN SATELITAL: no es lluvia medida, no cambia el nivel de lluvia y no es una alerta
oficial. No ve la lluvia de nubes bajas.

Horas en UTC. La hora de una fila de ABI es el inicio del barrido; la del GLM, el inicio del intervalo.
Dependencias: numpy y h5py. En el entorno: CLIMA_GOES_S3.
"""
import datetime as dt
import logging
import time
from concurrent.futures import ProcessPoolExecutor, as_completed

import numpy as np
from django.db import connection

from ..fuentes import anotar, base
from ..models import Estado
from . import goes, vigilancia

registro = logging.getLogger(__name__)
UTC = dt.timezone.utc
FUENTE = "goes"
# Recorte ABI: las islas habitadas con ~50 km de margen. Caja de rayos más amplia, para ver lo que se acerca.
REGION_ABI = [-91.70, -1.50, -89.00, 0.05]
REGION_GLM = [-93.50, -3.00, -87.50, 2.00]
ANILLO_KM = 25
FRIO_K = 221.0           # tope muy frío: convección profunda (−52 °C)
CELDA_GRADOS = 0.05      # rejilla gruesa (~5,5 km) para el mapa público
HORAS_PUBLICAS = 3
ABI_POR_PASADA = 6       # máximo de barridos por producto en una pasada (recuperación tras un corte)
GLM_INTERVALOS_POR_PASADA = 9
PLAZO_S = 170            # plazo total de una pasada
GLM_PROCESOS = 4

VARIABLES = {
    "tb_min_k": "Tb mínima de la banda 13 en la zona (K)",
    "frio_pct": f"% de píxeles de la zona con Tb < {FRIO_K:.0f} K",
    "frio_pct_25km": f"ídem en la zona ampliada {ANILLO_KM} km",
    "lluvia_sat_max_mmh": "RRQPE máxima en la zona (mm/h)",
    "lluvia_sat_media_mmh": "RRQPE media en la zona (mm/h)",
    "lluvia_sat_max_mmh_25km": f"RRQPE máxima en la zona ampliada {ANILLO_KM} km (mm/h)",
    "rayos_n": "destellos GLM en la zona en los 10 min que empiezan en ts",
    "rayos_n_25km": f"ídem en la zona ampliada {ANILLO_KM} km",
}


def ampliar(caja, km):
    g = km / 111.0
    return [caja[0] - g, caja[1] - g, caja[2] + g, caja[3] + g]


def dentro(lat, lon, caja):
    return (lon >= caja[0]) & (lon <= caja[2]) & (lat >= caja[1]) & (lat <= caja[3])


def iso(t):
    return t.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _numero(x):
    return None if x is None or not np.isfinite(x) else round(float(x), 3)


def guardar(filas):
    """filas: [(zona, variable, hora, valor)]."""
    return base.guardar(FUENTE, [(z, v, t, _numero(x)) for z, v, t, x in filas])


def leer_estado(clave, defecto):
    e = Estado.objects.filter(clave=clave).first()
    return e.datos if e else defecto


def escribir_estado(clave, datos, ahora):
    Estado.objects.update_or_create(clave=clave, defaults={"datos": datos, "generado": ahora})


def _horas_hechas(zona, variable, desde):
    return {t for t, _ in base.serie(FUENTE, zona, variable, desde=desde)}


class Plazo:
    def __init__(self, segundos):
        self.fin = time.time() + segundos

    def agotado(self):
        return time.time() > self.fin


# ── ABI ──────────────────────────────────────────────────────────────────────
def rejilla(lat, lon, valores, modo, umbral):
    """Celdas de CELDA_GRADOS con el mínimo (Tb) o el máximo (lluvia) que pasan el umbral."""
    m = np.isfinite(valores) & ((valores < umbral) if modo == "min" else (valores >= umbral))
    if not m.any():
        return []
    ci = np.floor(lat[m] / CELDA_GRADOS).astype(int)
    cj = np.floor(lon[m] / CELDA_GRADOS).astype(int)
    celdas = {}
    for a, b, x in zip(ci, cj, valores[m]):
        k = (a, b)
        if k not in celdas or (x < celdas[k] if modo == "min" else x > celdas[k]):
            celdas[k] = x
    return [[round((a + 0.5) * CELDA_GRADOS, 3), round((b + 0.5) * CELDA_GRADOS, 3), round(float(x), 1)] for (a, b), x in sorted(celdas.items())]


def agregados(producto, d, la, lo, zonas, t0):
    filas = []
    for zid, z in zonas.items():
        m0 = dentro(la, lo, z["bbox"]) & np.isfinite(d)
        m1 = dentro(la, lo, ampliar(z["bbox"], ANILLO_KM)) & np.isfinite(d)
        v0, v1 = d[m0], d[m1]
        if producto == "c13":
            filas += [(zid, "tb_min_k", t0, v0.min() if v0.size else None),
                      (zid, "frio_pct", t0, 100 * (v0 < FRIO_K).mean() if v0.size else None),
                      (zid, "frio_pct_25km", t0, 100 * (v1 < FRIO_K).mean() if v1.size else None)]
        else:
            filas += [(zid, "lluvia_sat_max_mmh", t0, v0.max() if v0.size else None),
                      (zid, "lluvia_sat_media_mmh", t0, v0.mean() if v0.size else None),
                      (zid, "lluvia_sat_max_mmh_25km", t0, v1.max() if v1.size else None)]
    return filas


def procesar_abi(zonas, ahora, horas_atras, errores, plazo):
    """Barridos nuevos de la banda 13 y del RRQPE, por pares: la banda 13 da la altura del tope para
    corregir el paralaje de los dos. Devuelve lo último de cada producto, para el resumen público."""
    ultimo = leer_estado("satelite_abi", {})
    desde = ahora - dt.timedelta(hours=horas_atras + 1)
    hechos = {"c13": _horas_hechas("la-cascada", "tb_min_k", desde), "rrqpe": _horas_hechas("la-cascada", "lluvia_sat_max_mmh", desde)}
    disponibles = {"c13": {}, "rrqpe": {}}
    for producto in disponibles:
        for h in range(horas_atras, -1, -1):
            if plazo.agotado():  # con el bucket colgado, los listados también cuentan para el plazo
                break
            hora = (ahora - dt.timedelta(hours=h)).replace(minute=0, second=0, microsecond=0)
            try:
                for clave, tamano in goes.listar(producto, hora):
                    t0 = goes.inicio_de(clave)
                    if goes.SUBIDO.get(clave, t0 + dt.timedelta(minutes=10)) <= ahora:
                        disponibles[producto][t0] = (clave, tamano)
            except FileNotFoundError:
                continue
            except Exception as e:
                errores.append(f"listar {producto} {hora:%H}Z: {str(e)[:100]}")
    pendientes = sorted({t for p in disponibles for t in disponibles[p] if t not in hechos[p]}, reverse=True)
    for t0 in pendientes[:ABI_POR_PASADA]:  # primero lo más reciente; tras un corte, recupera hacia atrás
        if plazo.agotado():
            break
        r13 = rrr = None
        if t0 in disponibles["c13"]:
            try:
                r13 = goes.leer_abi("c13", *disponibles["c13"][t0], REGION_ABI)
            except Exception as e:
                errores.append(f"ABI c13 {iso(t0)}: {str(e)[:100]}")
        if t0 in disponibles["rrqpe"] and t0 not in hechos["rrqpe"]:
            try:
                rrr = goes.leer_abi("rrqpe", *disponibles["rrqpe"][t0], REGION_ABI)
            except Exception as e:
                errores.append(f"ABI rrqpe {iso(t0)}: {str(e)[:100]}")
        # Paralaje: altura del tope desde la Tb de la banda 13; sin banda 13, 12 km para los píxeles con lluvia.
        if r13 is not None:
            la, lo = goes.corregir_paralaje(r13["lat"], r13["lon"], goes.altura_tope_km(r13["datos"]), r13["lon_sat"])
        for producto, r in (("c13", r13), ("rrqpe", rrr)):
            if r is None or (producto == "c13" and t0 in hechos["c13"]):
                continue
            if r13 is None:  # solo RRQPE
                la, lo = goes.corregir_paralaje(r["lat"], r["lon"], np.where(r["datos"] > 0, 12.0, 0.0), r["lon_sat"])
            d = r["datos"]
            guardar(agregados(producto, d, la, lo, zonas, t0))
            clave = disponibles[producto][t0][0]
            latencia = round((goes.SUBIDO[clave] - t0).total_seconds() / 60, 1) if clave in goes.SUBIDO else None
            previo = ultimo.get(producto, {}).get("ts")
            if previo is None or iso(t0) >= previo:
                celdas = rejilla(la, lo, d, "min", 235.0) if producto == "c13" else rejilla(la, lo, d, "max", 1.0)
                ultimo[producto] = {"ts": iso(t0), "celdas": celdas, "latencia_min": latencia, "bytes": r["bytes"]}
    escribir_estado("satelite_abi", ultimo, ahora)
    return ultimo


# ── GLM ──────────────────────────────────────────────────────────────────────
def _leer_glm(argumentos):
    clave, tamano = argumentos
    g = goes.leer_glm(clave, tamano, REGION_GLM)  # por rangos: ~55 KB de ~320 KB
    return g["lat"], g["lon"], g["base"].timestamp() + g["dt"], g["bytes"]


def procesar_glm(zonas, ahora, horas_atras, errores, plazo):
    """Destellos de calidad buena por zona en intervalos de 10 min. Los puntos quedan en Estado para el mapa."""
    puntos = leer_estado("satelite_glm", {})  # intervalo ISO → [[lat, lon, época], …]
    fin = ahora - dt.timedelta(minutes=1)
    inicio = (ahora - dt.timedelta(hours=horas_atras)).replace(second=0, microsecond=0)
    inicio -= dt.timedelta(minutes=inicio.minute % 10)
    leidos = dict(base.serie(FUENTE, "galapagos", "glm_archivos", desde=inicio))
    intervalos, t = [], inicio
    while t + dt.timedelta(minutes=10) <= fin + dt.timedelta(minutes=1):
        if t not in leidos or (leidos[t] < 30 and ahora - t < dt.timedelta(minutes=60)):
            intervalos.append(t)
        t += dt.timedelta(minutes=10)
    listados = {}
    connection.close()  # los procesos hijos no deben heredar la conexión a la base
    with ProcessPoolExecutor(GLM_PROCESOS) as ex:
        for b in intervalos[-GLM_INTERVALOS_POR_PASADA:]:
            if plazo.agotado():
                break
            hora = b.replace(minute=0)
            if hora not in listados:
                try:
                    listados[hora] = goes.listar("glm", hora)
                except FileNotFoundError:
                    listados[hora] = []
                except Exception as e:
                    errores.append(f"listar glm {hora:%H}Z: {str(e)[:100]}")
                    break
            archivos = [x for x in listados[hora] if b <= goes.inicio_de(x[0]) < b + dt.timedelta(minutes=10)]
            lat, lon, tt, leidos_ok, fallos = [], [], [], 0, 0
            for f in as_completed([ex.submit(_leer_glm, a) for a in archivos]):
                try:
                    a_, o_, t_, _ = f.result()
                except Exception:
                    fallos += 1
                    continue
                leidos_ok += 1
                lat.append(a_)
                lon.append(o_)
                tt.append(t_)
            if fallos:
                errores.append(f"GLM {iso(b)}: {fallos} archivos ilegibles")
            if not leidos_ok and archivos:
                continue
            la = np.concatenate(lat) if lat else np.array([])
            lo = np.concatenate(lon) if lon else np.array([])
            te = np.concatenate(tt) if tt else np.array([])
            filas = [("galapagos", "glm_archivos", b, leidos_ok)]
            for zid, z in zonas.items():  # sin archivos leídos: nulo (no es «0 rayos»)
                filas += [(zid, "rayos_n", b, int(dentro(la, lo, z["bbox"]).sum()) if leidos_ok else None),
                          (zid, "rayos_n_25km", b, int(dentro(la, lo, ampliar(z["bbox"], ANILLO_KM)).sum()) if leidos_ok else None)]
            guardar(filas)
            puntos[iso(b)] = [[round(float(a), 3), round(float(o), 3), int(x)] for a, o, x in zip(la, lo, te)]
    corte = iso(ahora - dt.timedelta(hours=HORAS_PUBLICAS + 1))
    escribir_estado("satelite_glm", {k: v for k, v in puntos.items() if k >= corte}, ahora)


# ── Resumen público ──────────────────────────────────────────────────────────
def resumen(zonas, ahora, ultimo, corrida):
    series = {}
    with connection.cursor() as c:
        c.execute("""SELECT e.codigo, o.variable, o.ts, o.valor FROM clima_observacion o JOIN clima_estacion e ON e.id = o.estacion_id
                     WHERE e.fuente = %s AND o.ts >= %s AND o.ts <= %s ORDER BY o.ts""", [FUENTE, ahora - dt.timedelta(hours=HORAS_PUBLICAS), ahora])
        for zona, variable, ts, valor in c.fetchall():
            series.setdefault(zona, {}).setdefault(variable, []).append([iso(ts), valor])
    por_zona = {}
    for zid, z in zonas.items():
        s = series.get(zid, {})
        por_zona[zid] = {"nombre": z["nombre"], "bbox": z["bbox"], "series": s, "evaluada": zid in vigilancia.ZONAS_EVALUADAS,
                         "vigilancia": vigilancia.evaluar(s, ahora, zid)}
    t_ahora = ahora.timestamp()
    rayos = [[a, o, int((t_ahora - x) // 60)] for pts in leer_estado("satelite_glm", {}).values() for a, o, x in pts if 0 <= t_ahora - x <= HORAS_PUBLICAS * 3600]
    archivos = series.get("galapagos", {}).get("glm_archivos", [])
    return {
        "generado": iso(ahora),
        "advertencia": "Estimación satelital (GOES-19, NOAA): no es lluvia medida ni una alerta oficial. "
                       "No ve la lluvia de nubes bajas. Siga siempre las indicaciones del COE, la SNGR y el ECU 911.",
        "fuente": "GOES-19 (GOES-East, NOAA): ABI banda 13 y RRQPE cada 10 min; rayos del GLM",
        "horas": "UTC",
        "region_abi": REGION_ABI, "region_glm": REGION_GLM, "anillo_km": ANILLO_KM, "frio_k": FRIO_K,
        "celda_grados": CELDA_GRADOS, "paralaje": "corregido (altura del tope desde la Tb de la banda 13)",
        "variables": VARIABLES,
        "vigilancia_umbrales": {k: [u, p, t] for k, (u, p, t) in vigilancia.UMBRALES.items()},
        "vigilancia_persistencia_h": vigilancia.PERSISTENCIA_H,
        "zonas_evaluadas": sorted(vigilancia.ZONAS_EVALUADAS),
        "ultima_imagen": {p: {"ts": u.get("ts"), "latencia_min": u.get("latencia_min")} for p, u in ultimo.items()},
        "glm_ultimo_intervalo": archivos[-1][0] if archivos else None,
        "zonas": por_zona,
        "rayos": rayos,                                      # [lat, lon, minutos desde el destello], calidad buena
        "nucleos": ultimo.get("c13", {}).get("celdas", []),  # [lat, lon, Tb mín. K] con Tb < 235 K, con el paralaje corregido
        "lluvia_sat": ultimo.get("rrqpe", {}).get("celdas", []),  # [lat, lon, mm/h] con ≥ 1 mm/h
        "corrida": corrida,
    }


def pasada(ahora=None, horas=1.0, con_glm=True):
    """Una pasada completa. Devuelve el estado de la corrida ({ts, segundos, ok, errores})."""
    ahora = ahora or dt.datetime.now(UTC)
    t0, plazo, errores = time.monotonic(), Plazo(PLAZO_S), []
    zonas = goes.zonas()
    ultimo = leer_estado("satelite_abi", {})
    try:
        ultimo = procesar_abi(zonas, ahora, max(0, int(np.ceil(horas))), errores, plazo)
    except Exception as e:  # un producto caído no detiene al otro
        registro.exception("Falló ABI")
        errores.append(f"abi: {str(e)[:150]}")
    if con_glm:
        try:
            procesar_glm(zonas, ahora, horas, errores, plazo)
        except Exception as e:
            registro.exception("Falló GLM")
            errores.append(f"glm: {str(e)[:150]}")
    corrida = {"ts": iso(ahora), "segundos": round(time.monotonic() - t0, 1), "ok": not errores, "errores": errores}
    escribir_estado("satelite", resumen(zonas, ahora, ultimo, corrida), ahora)
    anotar(FUENTE, t0, error="; ".join(errores))
    return corrida

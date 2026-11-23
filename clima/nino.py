# SOS Galápagos · © 2026 Universidad San Francisco de Quito (USFQ) · Autor: Julián Maya <jamaya@usfq.edu.ec>
# Licencia Apache 2.0 (ver LICENSE y NOTICE): puede reutilizarse dando crédito.
"""El Niño visto desde Galápagos: índices de la NOAA, temperatura y nivel del mar, boyas y la MJO.

Qué junta (todo es contexto; la voz oficial en Ecuador es el comité ERFEN):
  - Índices de la NOAA (CPC): ONI (mensual), Niño 1+2, 3, 3.4 y 4 (semanal y mensual), calor
    acumulado en los 300 m de arriba del Pacífico ecuatorial (mensual) y el estado de su sistema de
    alerta (sale el segundo jueves de cada mes).
  - Temperatura del mar y su anomalía diaria a 5 km de NOAA Coral Reef Watch (CRW): una rejilla de
    0,5° del Pacífico este para el mapa, otra de 0,1° del archipiélago y series de 60 días frente a
    los tres puertos. Con la rejilla se calcula cada día una estimación propia de Niño 1+2, 3 y 3.4.
  - Índices Niño diarios propios con OISST v2.1 de la NOAA (tiempo casi real, ≈ 4 días de retraso):
    es el mismo producto y la misma base 1991–2020 que usa el CPC, así que cuadran con su índice
    semanal (comprobado: Niño 1+2 del 8 al 14-nov-2026, 5,46 °C con OISST y 5,4 °C del CPC). CRW,
    en cambio, da unos 0,6 °C más en Niño 1+2 (otra base, 1985–2012): sirve para el mapa, no para el índice.
  - Anomalía del nivel del mar por altimetría (NOAA CoastWatch, mezcla de satélites, diaria).
  - Profundidad de la isoterma de 20 °C en las boyas TAO de 95° O y 110° O (cuán hondo está el agua
    fría) y su normal del mismo mes 1991–2020, calculada con la serie mensual de las mismas boyas.
  - La oscilación de Madden-Julian (MJO), índice ROMI de la NOAA PSL.
  - El último boletín ERFEN que ya guardó `oficiales.py` (si hay base de datos).

Los endpoints van en variables de entorno, nunca en el repositorio (ver `_ajuste`):
  CLIMA_CPC_ONI_URL, CLIMA_CPC_SEMANAL_URL, CLIMA_CPC_MENSUAL_URL, CLIMA_CPC_CALOR_URL,
  CLIMA_CPC_ENSO_URL, CLIMA_CRW_ERDDAP, CLIMA_OISST_ERDDAP, CLIMA_SLA_ERDDAP, CLIMA_TAO_ERDDAP, CLIMA_MJO_URL
Una variable vacía apaga esa parte; el resto se exporta igual.

El módulo se importa sin Django ni base de datos (solo biblioteca estándar): así se prueba con un
script. `exportar(destino)` escribe nino.json y nino_mapa.json.
"""
import csv
import io
import json
import math
import os
import re
import time
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

UTC = timezone.utc
GALAPAGOS = timezone(timedelta(hours=-6))
AVISO = ("Estimación con datos de satélite y boyas de la NOAA. Es contexto, no un dato oficial: "
         "la voz oficial sobre El Niño en Ecuador es el comité ERFEN (INOCAR e INAMHI).")

# Regiones Niño de la NOAA: (norte, sur, oeste, este) en grados, longitudes negativas al oeste.
REGIONES = {
    "nino12": {"nombre": "Niño 1+2", "n": 0, "s": -10, "o": -90, "e": -80, "nota": "Frente a Ecuador y Perú: la que más se parece a lo que vive Galápagos"},
    "nino3": {"nombre": "Niño 3", "n": 5, "s": -5, "o": -150, "e": -90, "nota": "Pacífico ecuatorial este"},
    "nino34": {"nombre": "Niño 3.4", "n": 5, "s": -5, "o": -170, "e": -120, "nota": "Centro del Pacífico: la que usa la NOAA para declarar El Niño"},
}
# Rejillas del mapa: (norte, sur, oeste, este, paso en celdas de la fuente)
MAPA_PACIFICO = (15, -15, -170, -75)
MAPA_ISLAS = (1.8, -1.6, -92.2, -88.9)
# Cajas de mar abierto frente a cada puerto (lat, lon, medio lado en grados): la celda del muelle es tierra.
PUERTOS = {
    "santa-cruz": {"nombre": "Puerto Ayora", "isla": "Santa Cruz", "lat": -0.80, "lon": -90.30},
    "san-cristobal": {"nombre": "Puerto Baquerizo Moreno", "isla": "San Cristóbal", "lat": -0.92, "lon": -89.64},
    "isabela": {"nombre": "Puerto Villamil", "isla": "Isabela", "lat": -1.00, "lon": -90.96},
}
BOYAS = {"0n95w": (0, -95), "2s95w": (-2, -95), "0n110w": (0, -110)}
ESTADOS_CPC = {
    "el nino advisory": ("Advertencia de El Niño", "El Niño está en curso y se espera que siga."),
    "el nino watch": ("Vigilancia de El Niño", "Las condiciones favorecen que se forme El Niño en los próximos seis meses."),
    "la nina advisory": ("Advertencia de La Niña", "La Niña está en curso y se espera que siga."),
    "la nina watch": ("Vigilancia de La Niña", "Las condiciones favorecen que se forme La Niña en los próximos seis meses."),
    "final el nino advisory": ("Fin de El Niño", "El Niño terminó."),
    "final la nina advisory": ("Fin de La Niña", "La Niña terminó."),
    "not active": ("Sistema inactivo", "No hay El Niño ni La Niña ni se espera en los próximos meses."),
}


# ── Utilidades ───────────────────────────────────────────────────────────────
def _ajuste(nombre):
    """Valor de configuración: primero los ajustes de Django (si están cargados), luego el entorno."""
    try:
        from django.conf import settings

        valor = getattr(settings, nombre, None)
        if valor:
            return valor
    except Exception:
        pass
    return os.environ.get(nombre, "")


LIMITE_S = 240  # la corrida entera: después se saltan las fuentes que falten (el trabajador es uno solo y atiende las alertas)


def _bajar(url, espera=45):
    pedido = urllib.request.Request(url, headers={"User-Agent": "sosgalapagos.org (clima; contacto en el sitio)"})
    with urllib.request.urlopen(pedido, timeout=espera) as r:
        return r.read()


def _corrida(fuente, t0, ok, registros=0, error=""):
    """Anota la corrida en el registro de salud si hay base de datos; si no, no hace nada."""
    try:
        from .mar import _corrida as anotar

        anotar(fuente, t0, ok, registros, error)
    except Exception:
        pass


def _redondo(v, d=2):
    return None if v is None or (isinstance(v, float) and math.isnan(v)) else round(v, d)


def _numero(texto):
    try:
        v = float(texto)
        return None if math.isnan(v) or v < -90 else v  # -99.9 y -999 son «sin dato» en los archivos del CPC
    except (TypeError, ValueError):
        return None


MESES_EN = {m: i for i, m in enumerate(["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"], 1)}
TEMPORADAS = ["DJF", "JFM", "FMA", "MAM", "AMJ", "MJJ", "JJA", "JAS", "ASO", "SON", "OND", "NDJ"]


# ── Lectores de los archivos de texto del CPC ────────────────────────────────
def leer_oni(texto):
    """ONI: [{temporada, anio, mes_central, sst, anom}]. La temporada «ASO 2026» se centra en septiembre."""
    salida = []
    for linea in texto.splitlines():
        p = linea.split()
        if len(p) == 4 and p[0] in TEMPORADAS and p[1].isdigit():
            mes = TEMPORADAS.index(p[0]) + 1  # DJF → enero
            anio = int(p[1])
            salida.append({"temporada": p[0], "anio": anio, "mes": f"{anio}-{mes:02d}", "sst": _numero(p[2]), "anom": _numero(p[3])})
    return salida


def leer_semanal(texto):
    """Índices semanales (semana centrada en el miércoles): [{semana, nino12, nino3, nino34, nino4}] con anomalía y temperatura.

    Ojo: el archivo pega los negativos al número anterior («20.6-0.1»), por eso se leen con una expresión regular.
    """
    salida = []
    for linea in texto.splitlines():
        m = re.match(r"\s*(\d{2})([A-Z]{3})(\d{4})(.*)", linea)
        if not m or m.group(2) not in MESES_EN:
            continue
        v = [float(x) for x in re.findall(r"-?\d+\.\d", m.group(4))]
        if len(v) != 8:
            continue
        semana = date(int(m.group(3)), MESES_EN[m.group(2)], int(m.group(1))).isoformat()
        # Orden del archivo: Niño 1+2, Niño 3, Niño 3.4, Niño 4 (temperatura y anomalía de cada uno).
        salida.append({"semana": semana, **{k: {"sst": v[2 * i], "anom": v[2 * i + 1]} for i, k in enumerate(("nino12", "nino3", "nino34", "nino4"))}})
    return salida


def leer_mensual(texto):
    """Índices mensuales (base 1991–2020): [{mes, nino12, nino3, nino4, nino34}] con temperatura y anomalía."""
    salida = []
    for linea in texto.splitlines():
        p = linea.split()
        if len(p) == 10 and p[0].isdigit() and p[1].isdigit():
            v = [_numero(x) for x in p[2:]]
            salida.append({"mes": f"{int(p[0])}-{int(p[1]):02d}", "nino12": {"sst": v[0], "anom": v[1]}, "nino3": {"sst": v[2], "anom": v[3]},
                           "nino4": {"sst": v[4], "anom": v[5]}, "nino34": {"sst": v[6], "anom": v[7]}})
    return salida


def leer_calor(texto):
    """Anomalía de temperatura media de los 300 m de arriba, Pacífico ecuatorial 180°–100° O: [{mes, anom}]."""
    salida = []
    for linea in texto.splitlines():
        p = linea.split()
        if len(p) == 5 and p[0].isdigit() and p[1].isdigit():
            salida.append({"mes": f"{int(p[0])}-{int(p[1]):02d}", "anom": _numero(p[4])})
    return salida


def leer_estado_cpc(pagina):
    """Estado del sistema de alerta de la NOAA y fecha de la discusión mensual. Solo el estado, traducido con una tabla fija."""
    texto = re.sub(r"<[^>]+>", " ", pagina)
    texto = re.sub(r"&nbsp;|\s+", " ", texto.replace("&ntilde;", "n").replace("&Ntilde;", "N"))
    m = re.search(r"ENSO Alert System Status:\s*([A-Za-z ]+?)\s*(?:Synopsis|$)", texto)
    f = re.search(r"(\d{1,2}) (January|February|March|April|May|June|July|August|September|October|November|December) (\d{4})", texto)
    if not m:
        return None
    clave = m.group(1).strip().lower()
    estado, explica = ESTADOS_CPC.get(clave, (m.group(1).strip(), ""))
    fecha = None
    if f:
        meses = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"]
        fecha = date(int(f.group(3)), meses.index(f.group(2)) + 1, int(f.group(1))).isoformat()
    fuerte = re.search(r"(strong-to-very strong|very strong|strong|moderate|weak) El Nino", texto, re.I)
    return {"estado": estado, "explica": explica, "clave": clave, "fecha": fecha,
            "intensidad_esperada": {"strong-to-very strong": "fuerte a muy fuerte", "very strong": "muy fuerte", "strong": "fuerte",
                                    "moderate": "moderada", "weak": "débil"}.get((fuerte.group(1).lower() if fuerte else ""), None)}


def leer_mjo(texto, dias=40):
    """ROMI (NOAA PSL): [{fecha, pc1, pc2, amplitud, fase}] de los últimos días. La fase (1–8) sale del ángulo de (PC2, −PC1)."""
    filas = []
    for linea in texto.splitlines():
        p = linea.split()
        if len(p) >= 7 and p[0].isdigit():
            try:
                a, m, d = int(p[0]), int(p[1]), int(p[2])
                pc1, pc2, amp = float(p[4]), float(p[5]), float(p[6])
            except ValueError:
                continue
            # Convención de Kiladis et al. (2014): RMM1 ≈ PC2 y RMM2 ≈ −PC1.
            x, y = pc2, -pc1
            fase = int(((math.degrees(math.atan2(y, x)) + 180) // 45) % 8) + 1
            filas.append({"fecha": f"{a}-{m:02d}-{d:02d}", "pc1": round(pc1, 2), "pc2": round(pc2, 2), "amplitud": round(amp, 2), "fase": fase})
    return filas[-dias:]


FASES_MJO = {
    1: "sobre el hemisferio occidental y África", 2: "sobre el océano Índico", 3: "sobre el océano Índico", 4: "sobre Indonesia",
    5: "sobre Indonesia", 6: "sobre el Pacífico oeste", 7: "sobre el Pacífico oeste", 8: "sobre el Pacífico este y América",
}


def frase_mjo(ultimo):
    if not ultimo:
        return None
    if ultimo["amplitud"] < 1:
        return "La MJO está débil: no empuja ni frena las lluvias."
    cerca = ultimo["fase"] in (8, 1)
    return (f"La MJO está activa (fase {ultimo['fase']}, {FASES_MJO[ultimo['fase']]})"
            + (": suele favorecer más lluvia en el Pacífico este." if cerca else ": lejos de Galápagos por ahora."))


# ── ERDDAP ───────────────────────────────────────────────────────────────────
def _erddap_filas(texto):
    """CSV de ERDDAP (encabezado, fila de unidades y datos) → lista de diccionarios con números."""
    lector = csv.reader(io.StringIO(texto))
    cab = next(lector)
    next(lector, None)  # unidades
    filas = []
    for fila in lector:
        d = {}
        for k, v in zip(cab, fila):
            if k in ("time", "station", "array"):
                d[k] = v
            else:
                try:
                    d[k] = float(v)
                except ValueError:
                    d[k] = None
                if isinstance(d[k], float) and math.isnan(d[k]):
                    d[k] = None
        filas.append(d)
    return filas


def _rango(a, b, paso=1):
    return f"[({a}):{paso}:({b})]" if paso != 1 else f"[({a}):({b})]"


def _griddap(base, variables, tiempo, lat, lon, espera=60):
    """Pide a un griddap de ERDDAP. `lat` y `lon` son (inicio, fin, paso) en el orden del conjunto de datos."""
    sel = "".join([tiempo, _rango(*lat), _rango(*lon)])
    consulta = ",".join(f"{v}{sel}" for v in variables)
    return _erddap_filas(_bajar(f"{base}.csv?{urllib.parse.quote(consulta, safe='[]():,!')}", espera).decode())


def _a_rejilla(filas, variable, escala, factor=1):
    """Filas (lat, lon, valor) → rejilla norte→sur, oeste→este, con enteros (valor × factor × escala) y None en tierra.

    `factor` cambia de unidad (metros → centímetros); `escala` guarda decimales en enteros (0,1 °C → 10).
    """
    lats = sorted({f["latitude"] for f in filas}, reverse=True)
    lons = sorted({f["longitude"] for f in filas})
    il = {v: i for i, v in enumerate(lats)}
    jl = {v: j for j, v in enumerate(lons)}
    valores = [None] * (len(lats) * len(lons))
    for f in filas:
        v = f.get(variable)
        if v is not None:
            valores[il[f["latitude"]] * len(lons) + jl[f["longitude"]]] = round(v * factor * escala)
    paso_lat = round(abs(lats[0] - lats[1]), 4) if len(lats) > 1 else 0
    paso_lon = round(abs(lons[1] - lons[0]), 4) if len(lons) > 1 else 0
    fecha = filas[0]["time"][:10] if filas else None
    return {"fecha": fecha, "lat_n": lats[0], "lon_o": lons[0], "paso_lat": paso_lat, "paso_lon": paso_lon,
            "nlat": len(lats), "nlon": len(lons), "escala": escala, "valores": valores}


def media_region(rejilla, n, s, o, e):
    """Media ponderada por coseno de la latitud de las celdas de mar dentro de la caja (valores reales, no enteros)."""
    suma = peso = 0.0
    for i in range(rejilla["nlat"]):
        lat = rejilla["lat_n"] - i * rejilla["paso_lat"]
        if not (s <= lat <= n):
            continue
        w = math.cos(math.radians(lat))
        for j in range(rejilla["nlon"]):
            lon = rejilla["lon_o"] + j * rejilla["paso_lon"]
            v = rejilla["valores"][i * rejilla["nlon"] + j]
            if o <= lon <= e and v is not None:
                suma += w * v / rejilla["escala"]
                peso += w
    return round(suma / peso, 2) if peso else None


def rejilla_crw(caja, paso, variable="CRW_SSTANOMALY", escala=10):
    """Último día de CRW en la caja (norte, sur, oeste, este). CRW guarda las latitudes de norte a sur."""
    n, s, o, e = caja
    filas = _griddap(_ajuste("CLIMA_CRW_ERDDAP"), [variable], "[(last)]", (n, s, paso), (o, e, paso))
    return _a_rejilla(filas, variable, escala)


def rejilla_sla(caja, paso):
    """Último día de la anomalía del nivel del mar, en centímetros enteros. Ese conjunto guarda las latitudes de sur a norte."""
    n, s, o, e = caja
    filas = _griddap(_ajuste("CLIMA_SLA_ERDDAP"), ["sla"], "[(last)]", (s, n, paso), (o, e, paso))
    return _a_rejilla(filas, "sla", 1, factor=100)


def indices_diarios(dias=30):
    """Niño 1+2, 3 y 3.4 de cada uno de los últimos días con OISST (cada 1°, ponderado por latitud): [{fecha, nino12, nino3, nino34}]."""
    base = _ajuste("CLIMA_OISST_ERDDAP")
    if not base:
        return []
    filas = _griddap(base, ["anom"], f"[last-{dias - 1}:last][(0.0)]", (-10, 5, 4), (-170, -80, 4), espera=75)
    por_dia = {}
    for f in filas:
        por_dia.setdefault(f["time"][:10], []).append(f)
    salida = []
    for dia, fs in sorted(por_dia.items()):
        fila = {"fecha": dia}
        for k, r in REGIONES.items():
            suma = peso = 0.0
            for f in fs:
                if f["anom"] is not None and r["s"] <= f["latitude"] <= r["n"] and r["o"] <= f["longitude"] <= r["e"]:
                    w = math.cos(math.radians(f["latitude"]))
                    suma, peso = suma + w * f["anom"], peso + w
            fila[k] = round(suma / peso, 2) if peso else None
        salida.append(fila)
    return salida


def _caja_puerto(p, medio=0.1):
    return (round(p["lat"] + medio, 3), round(p["lat"] - medio, 3), round(p["lon"] - medio, 3), round(p["lon"] + medio, 3))


def _media_por_dia(filas, variable):
    dias = {}
    for f in filas:
        if f.get(variable) is not None:
            dias.setdefault(f["time"][:10], []).append(f[variable])
    return {d: sum(v) / len(v) for d, v in sorted(dias.items())}


def series_puertos(dias=60):
    """Por puerto: temperatura y anomalía diaria (CRW) y anomalía del nivel del mar (altimetría) de los últimos días."""
    salida = {}
    for clave, p in PUERTOS.items():
        n, s, o, e = _caja_puerto(p)
        r = {"nombre": p["nombre"], "isla": p["isla"], "lat": p["lat"], "lon": p["lon"], "sst": [], "sla": []}
        if _ajuste("CLIMA_CRW_ERDDAP"):
            try:
                filas = _griddap(_ajuste("CLIMA_CRW_ERDDAP"), ["CRW_SST", "CRW_SSTANOMALY"], f"[last-{dias - 1}:last]", (n, s, 1), (o, e, 1))
                t, a = _media_por_dia(filas, "CRW_SST"), _media_por_dia(filas, "CRW_SSTANOMALY")
                r["sst"] = [[d, round(t[d], 2), _redondo(a.get(d))] for d in t]
            except Exception as ex:
                r["error_sst"] = type(ex).__name__
        if _ajuste("CLIMA_SLA_ERDDAP"):
            try:
                n2, s2, o2, e2 = _caja_puerto(p, 0.25)
                filas = _griddap(_ajuste("CLIMA_SLA_ERDDAP"), ["sla"], f"[last-{dias - 1}:last]", (s2, n2, 1), (o2, e2, 1))
                r["sla"] = [[d, round(v * 100, 1)] for d, v in _media_por_dia(filas, "sla").items()]
            except Exception as ex:
                r["error_sla"] = type(ex).__name__
        salida[clave] = r
    return salida


def boyas_tao(dias=60, mes=None):
    """Isoterma de 20 °C en las boyas TAO del Pacífico este: serie diaria y normal del mes (1991–2020) con la serie mensual."""
    base = _ajuste("CLIMA_TAO_ERDDAP")
    if not base:
        return {}
    desde = (datetime.now(UTC) - timedelta(days=dias + 30)).strftime("%Y-%m-%d")
    estaciones = urllib.parse.quote('"(' + "|".join(BOYAS) + ')"')
    diario = _erddap_filas(_bajar(f"{base}/pmelTaoDyIso.csv?station,time,ISO_6&station=~{estaciones}&time%3E={desde}").decode())
    mensual = _erddap_filas(_bajar(f"{base}/pmelTaoMonIso.csv?station,time,ISO_6&station=~{estaciones}&time%3E=1991-01-01&time%3C2021-01-01").decode())
    salida = {}
    for est, (lat, lon) in BOYAS.items():
        serie = [[f["time"][:10], round(f["ISO_6"], 1)] for f in diario if f["station"] == est and f.get("ISO_6") is not None][-dias:]
        m = mes or (int(serie[-1][0][5:7]) if serie else datetime.now(UTC).month)
        normales = [f["ISO_6"] for f in mensual if f["station"] == est and f.get("ISO_6") is not None and int(f["time"][5:7]) == m]
        salida[est] = {"lat": lat, "lon": lon, "d20": serie, "normal_m": round(sum(normales) / len(normales), 1) if len(normales) >= 5 else None,
                       "anios_normal": len(normales), "mes_normal": m}
    return salida


# ── Lo oficial (ERFEN), si hay base de datos ─────────────────────────────────
def erfen():
    try:
        from .models import Boletin

        b = Boletin.objects.filter(tipo="erfen").order_by("-visto_en").first()
    except Exception:
        return None
    if not b:
        return None
    return {"fuente": "Comité ERFEN (INOCAR, INAMHI y otras instituciones)", "numero": b.numero, "titulo": b.titulo,
            "emitido": b.emitido.isoformat() if b.emitido else None, "visto": b.visto_en.isoformat() if b.visto_en else None,
            "nivel": b.nivel, "resumen": b.resumen, "enlace": b.enlace, "leido_por_modelo": bool(b.extraido_con), "revisado": b.revisado}


# ── Categoría según los umbrales de la NOAA ──────────────────────────────────
def categoria(anom):
    if anom is None:
        return None
    for umbral, nombre in ((2.0, "muy fuerte"), (1.5, "fuerte"), (1.0, "moderado"), (0.5, "débil")):
        if anom >= umbral:
            return f"El Niño {nombre}"
    if anom <= -0.5:
        return "La Niña"
    return "Neutral"


# ── Armar y exportar ─────────────────────────────────────────────────────────
def _texto(nombre):
    url = _ajuste(nombre)
    return _bajar(url).decode("utf-8", "replace") if url else None


def recoger(ahora=None):
    """Baja todo lo que haya configurado. Devuelve (nino, mapa): los dos diccionarios listos para JSON."""
    ahora = ahora or datetime.now(UTC)
    t0 = time.monotonic()
    errores, fuentes = {}, {}

    def intenta(nombre, f):
        if time.monotonic() - t0 > LIMITE_S:
            errores[nombre] = "sin tiempo"
            return None
        try:
            return f()
        except Exception as e:  # una fuente caída no tumba las demás
            errores[nombre] = type(e).__name__
            return None

    oni = intenta("oni", lambda: leer_oni(_texto("CLIMA_CPC_ONI_URL") or "")) or []
    semanal = intenta("semanal", lambda: leer_semanal(_texto("CLIMA_CPC_SEMANAL_URL") or "")) or []
    mensual = intenta("mensual", lambda: leer_mensual(_texto("CLIMA_CPC_MENSUAL_URL") or "")) or []
    calor = intenta("calor", lambda: leer_calor(_texto("CLIMA_CPC_CALOR_URL") or "")) or []
    estado = intenta("estado_noaa", lambda: leer_estado_cpc(_texto("CLIMA_CPC_ENSO_URL") or ""))
    mjo = intenta("mjo", lambda: leer_mjo(_texto("CLIMA_MJO_URL") or "")) or []

    crw = _ajuste("CLIMA_CRW_ERDDAP")
    pacifico = intenta("crw_pacifico", lambda: rejilla_crw(MAPA_PACIFICO, 10)) if crw else None
    islas = intenta("crw_islas", lambda: rejilla_crw(MAPA_ISLAS, 2)) if crw else None
    sla = intenta("sla_pacifico", lambda: rejilla_sla(MAPA_PACIFICO, 2)) if _ajuste("CLIMA_SLA_ERDDAP") else None
    sla_islas = intenta("sla_islas", lambda: rejilla_sla(MAPA_ISLAS, 1)) if _ajuste("CLIMA_SLA_ERDDAP") else None
    diarios = intenta("oisst_diario", indices_diarios) or []
    puertos = intenta("puertos", series_puertos) or {}
    tao = intenta("tao", boyas_tao) or {}
    oficial = erfen()

    diario = {**diarios[-1], "fuente": "estimación propia diaria con OISST v2.1 de la NOAA (base 1991–2020)", "serie": diarios} if diarios else None
    gal = None
    if islas:
        gal = {"fecha": islas["fecha"], "anom": media_region(islas, *MAPA_ISLAS), "sla_cm": media_region(sla_islas, *MAPA_ISLAS) if sla_islas else None,
               "fuente_sst": "NOAA Coral Reef Watch, base 1985–2012 (da unos 0,5 °C más que la base 1991–2020 de los índices)",
               "fuente_sla": "NOAA CoastWatch, altimetría de varios satélites"}

    ultima_sem = semanal[-1] if semanal else None
    ultimo_oni = oni[-1] if oni else None
    frases = []
    if oficial:
        frases.append({"voz": "oficial", "texto": f"ERFEN: {oficial['resumen']}" if oficial.get("resumen") else "Hay un boletín ERFEN reciente."})
    if gal and gal["anom"] is not None:
        frases.append({"voz": "contexto", "texto": f"El mar alrededor de Galápagos está {num(gal['anom'], 1)} °C {'más caliente' if gal['anom'] >= 0 else 'más frío'} que lo normal para la fecha (satélite Coral Reef Watch, {fecha_es(gal['fecha'])})."})
    if gal and gal.get("sla_cm") is not None:
        frases.append({"voz": "contexto", "texto": f"El nivel del mar está unos {num(gal['sla_cm'], 0)} cm {'más alto' if gal['sla_cm'] >= 0 else 'más bajo'} que el promedio (altimetría): las pleamares llegan más arriba que en la tabla de mareas."})
    if diario:
        frases.append({"voz": "contexto", "texto": f"Estimación diaria propia de Niño 1+2 al {fecha_es(diario['fecha'])}: {num(diario['nino12'], 1, signo=True)} °C."})
    if ultima_sem:
        frases.append({"voz": "contexto", "texto": f"Niño 1+2, frente a Ecuador y Perú: {num(ultima_sem['nino12']['anom'], 1, signo=True)} °C la semana del {fecha_es(ultima_sem['semana'])} (NOAA)."})
    if ultimo_oni:
        frases.append({"voz": "contexto", "texto": f"ONI {ultimo_oni['temporada']} {ultimo_oni['anio']}: {num(ultimo_oni['anom'], 2, signo=True)} °C. Según los umbrales de la NOAA: {categoria(ultimo_oni['anom'])}."})
    if mjo:
        frases.append({"voz": "contexto", "texto": frase_mjo(mjo[-1])})

    for nombre, valor in (("NOAA CPC (índices)", bool(semanal or oni)), ("NOAA Coral Reef Watch", bool(pacifico)), ("NOAA OISST", bool(diarios)), ("NOAA CoastWatch (altimetría)", bool(sla)),
                          ("Boyas TAO (NOAA PMEL)", bool(tao)), ("NOAA PSL (MJO)", bool(mjo)), ("ERFEN", bool(oficial))):
        fuentes[nombre] = valor

    nino = {
        "generado": ahora.isoformat(timespec="seconds"),
        "aviso": AVISO,
        "oficial": oficial,
        "estado_noaa": estado,
        "categoria_oni": categoria(ultimo_oni["anom"]) if ultimo_oni else None,
        "indices": {
            "oni": oni[-36:],
            "semanal": [{"semana": s["semana"], **{k: s[k]["anom"] for k in ("nino12", "nino3", "nino34", "nino4")}} for s in semanal[-26:]],
            "ultima_semana": ultima_sem,
            "mensual": mensual[-24:],
            "calor_300m": calor[-24:],
            "diario": diario,
        },
        "galapagos": gal,
        "puertos": puertos,
        "boyas": tao,
        "mjo": {"serie": mjo, "ultimo": mjo[-1] if mjo else None, "frase": frase_mjo(mjo[-1]) if mjo else None},
        "regiones": REGIONES,
        "frases": frases,
        "fuentes": fuentes,
        "errores": errores,
    }
    mapa = {
        "generado": ahora.isoformat(timespec="seconds"),
        "aviso": AVISO,
        "regiones": REGIONES,
        "sst_anom": {**pacifico, "unidad": "°C", "fuente": "NOAA Coral Reef Watch, anomalía diaria (cada 0,5°)"} if pacifico else None,
        "sst_anom_islas": {**islas, "unidad": "°C", "fuente": "NOAA Coral Reef Watch, anomalía diaria (cada 0,1°)"} if islas else None,
        "sla": {**sla, "unidad": "cm", "fuente": "NOAA CoastWatch, anomalía del nivel del mar por altimetría (cada 0,5°)"} if sla else None,
        "boyas": {k: {"lat": v["lat"], "lon": v["lon"], "d20": v["d20"][-1] if v["d20"] else None, "normal_m": v["normal_m"]} for k, v in tao.items()},
        "puertos": {k: {"nombre": v["nombre"], "lat": v["lat"], "lon": v["lon"]} for k, v in PUERTOS.items()},
    }
    _corrida("nino", t0, not errores, len(fuentes), ", ".join(f"{k}: {v}" for k, v in errores.items()))
    return nino, mapa


def num(v, d=1, signo=False):
    if v is None:
        return "—"
    s = f"{v:+.{d}f}" if signo else f"{abs(v):.{d}f}"
    return s.replace(".", ",").replace("-", "−")


MESES_ES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"]


def fecha_es(iso):
    try:
        d = date.fromisoformat(iso[:10])
        return f"{d.day} de {MESES_ES[d.month - 1]}"
    except (TypeError, ValueError):
        return iso


def _escribir(ruta, obj):
    ruta.parent.mkdir(parents=True, exist_ok=True)
    tmp = ruta.with_suffix(ruta.suffix + ".tmp")
    tmp.write_text(json.dumps(obj, ensure_ascii=False, separators=(",", ":"), default=str))
    os.chmod(tmp, 0o644)
    os.replace(tmp, ruta)


def exportar(destino=None, ahora=None):
    """Escribe nino.json y nino_mapa.json en la carpeta (por defecto CLIMA_SALIDA). Devuelve un resumen."""
    carpeta = Path(destino or _ajuste("CLIMA_SALIDA") or ".")
    t0 = time.monotonic()
    nino, mapa = recoger(ahora)
    _escribir(carpeta / "nino.json", nino)
    _escribir(carpeta / "nino_mapa.json", mapa)
    return {"carpeta": str(carpeta), "segundos": round(time.monotonic() - t0, 1), "errores": nino["errores"],
            "kb_nino": round((carpeta / "nino.json").stat().st_size / 1024, 1), "kb_mapa": round((carpeta / "nino_mapa.json").stat().st_size / 1024, 1)}

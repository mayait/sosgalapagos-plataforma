# SOS Galápagos · © 2026 Universidad San Francisco de Quito (USFQ) · Autor: Julián Maya <jamaya@usfq.edu.ec>
# Licencia Apache 2.0 (ver LICENSE y NOTICE): puede reutilizarse dando crédito.
"""La zona de convergencia intertropical (ZCIT) y las ondas tropicales cerca de Galápagos.

Sale de la «Tropical Weather Discussion» del Pacífico este del Centro Nacional de Huracanes de la
NOAA (NHC), que se publica cuatro veces al día con el análisis de superficie de las 00, 06, 12 y
18 UTC. Es texto plano en inglés con coordenadas («The ITCZ extends from 02N93W to 06.5N120.5W»),
así que basta un lector con expresiones regulares: no hace falta un modelo de lenguaje. Si hay uno
configurado (IA_MODELO), se le pide además un resumen en español de lo que dice para Ecuador y
Galápagos; el resumen nunca reemplaza al texto ni a las coordenadas.

Es un análisis automático de un servicio extranjero: contexto, no aviso oficial. La voz oficial
en Ecuador es el INAMHI. Límite importante: la discusión cubre desde 3,4° S hacia el norte, así que
una segunda rama de la ZCIT al sur del ecuador (típica con El Niño fuerte) puede no aparecer.

Endpoint en variable de entorno (nunca en el repositorio): CLIMA_NHC_TWD_URL (el texto del producto).
El módulo se importa sin Django ni base de datos. `exportar(destino)` escribe zcit.json.
"""
import re
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .nino import _ajuste, _bajar, _corrida, _escribir

UTC = timezone.utc
PUERTO_AYORA_LAT = -0.75
ISLAS_N, ISLAS_S = 1.7, -1.4  # de Darwin a Española
ZONA_CERCA = (-100, -80)  # longitudes que se consideran «cerca de Galápagos»
AVISO = ("Análisis automático del Centro Nacional de Huracanes de la NOAA (Estados Unidos). Es contexto, "
         "no un aviso oficial: la voz oficial en Ecuador es el INAMHI.")

COORD = re.compile(r"\b(EQ|\d{1,2}(?:\.\d+)?)\s*([NS])?\s*(\d{2,3}(?:\.\d+)?)\s*W\b")
MESES = {m: i for i, m in enumerate(["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"], 1)}


def _coord(lat, hemi, lon):
    if lat == "EQ":
        return [0.0, -float(lon)]
    v = float(lat)
    return [-v if hemi == "S" else v, -float(lon)]


def coordenadas(texto):
    """Todas las posiciones «02N93W», «01S83.5W», «EQ95W» del texto, en orden: [[lat, lon], …] (lon negativa al oeste)."""
    return [_coord(*m.groups()) for m in COORD.finditer(texto) if m.group(1) == "EQ" or m.group(2)]


def _lat(texto):
    """«03N» → 3, «03.4S» → −3.4, «the Equator» → 0."""
    m = re.match(r"\s*(?:the\s+)?(EQ|Equator|\d{1,2}(?:\.\d+)?)\s*([NS])?", texto, re.I)
    if not m:
        return None
    if m.group(1).upper() in ("EQ", "EQUATOR"):
        return 0.0
    v = float(m.group(1))
    return -v if m.group(2) == "S" else v


def secciones(texto):
    """Parte el producto en sus secciones «...TÍTULO...»: {título: texto}."""
    partes = re.split(r"^\.\.\.([A-Z][A-Z /,\-]+?)\.\.\.\s*$", texto, flags=re.M)
    salida = {"_cabecera": partes[0]}
    for i in range(1, len(partes) - 1, 2):
        salida[re.sub(r"\s+", " ", partes[i]).strip()] = partes[i + 1].split("$$")[0].strip()
    return salida


def emitido(texto):
    """Hora de emisión en UTC, de la línea «2205 UTC Sun Nov 22 2026»."""
    m = re.search(r"^(\d{3,4}) UTC \w{3} (\w{3}) (\d{1,2}) (\d{4})", texto, re.M)
    if not m:
        return None
    hhmm = m.group(1).zfill(4)
    return datetime(int(m.group(4)), MESES[m.group(2)], int(m.group(3)), int(hhmm[:2]), int(hhmm[2:]), tzinfo=UTC)


def analisis(texto):
    """Hora del análisis de superficie en que se basa («Based on 1800 UTC surface analysis»)."""
    m = re.search(r"Based on (\d{4}) UTC surface analysis", texto)
    e = emitido(texto)
    if not (m and e):
        return None
    h = datetime(e.year, e.month, e.day, int(m.group(1)[:2]), int(m.group(1)[2:]), tzinfo=UTC)
    return h if h <= e else h - timedelta(days=1)


def _oraciones(parrafo):
    return [o.strip() for o in re.split(r"(?<=[A-Za-z0-9\)])\.\s+(?=[A-Z])", re.sub(r"\s+", " ", parrafo)) if o.strip()]


def lineas_zcit(seccion):
    """Tramos de la vaguada monzónica y de la ZCIT: [{tipo, puntos}]. «resumes» abre un tramo nuevo."""
    salida = []
    for oracion in _oraciones(seccion):
        bajo = oracion.lower()
        if "monsoon trough" in bajo and "itcz" not in bajo.split("monsoon trough")[0]:
            tipo = "vaguada_monzonica"
        elif "itcz" in bajo:
            tipo = "zcit"
        else:
            continue
        # «The ITCZ extends from B to C, then resumes … from D to E.» / «Segments of the ITCZ are from A to B, then from C to D.»
        for k, trozo in enumerate(re.split(r"\bresumes\b|\bthen\b(?!\s+to\b)", oracion)):
            pts = coordenadas(trozo)
            if len(pts) >= 2:
                salida.append({"tipo": tipo, "puntos": pts, "reanuda": k > 0})
    return salida


def conveccion(seccion):
    """Cajas de convección «from 03.4S to 00N between 116W and 120W»: [{n, s, o, e}]."""
    salida = []
    for m in re.finditer(r"from\s+(\S+)\s+to\s+(\S+)\s+between\s+(\d{2,3}(?:\.\d+)?)W\s+and\s+(\d{2,3}(?:\.\d+)?)W", re.sub(r"\s+", " ", seccion)):
        a, b = _lat(m.group(1)), _lat(m.group(2))
        if a is None or b is None:
            continue
        o, e = -max(float(m.group(3)), float(m.group(4))), -min(float(m.group(3)), float(m.group(4)))
        salida.append({"n": max(a, b), "s": min(a, b), "o": o, "e": e})
    return salida


def ondas(seccion):
    """Ondas tropicales: [{lon, lat_s, lat_n, puntos, velocidad_kt, texto}]."""
    salida = []
    for parrafo in re.split(r"\n\s*\n", seccion):
        p = re.sub(r"\s+", " ", parrafo).strip()
        if not re.search(r"tropical wave", p, re.I):
            continue
        pts = coordenadas(p)
        lon = None
        if m := re.search(r"(?:along|near|axis (?:is )?(?:along|near|at))\s+(\d{2,3}(?:\.\d+)?)W", p):
            lon = -float(m.group(1))
        elif pts:
            lon = round(sum(x[1] for x in pts) / len(pts), 1)
        if lon is None:
            continue
        lat_s = lat_n = None
        if m := re.search(r"from\s+(\S+?)\s+to\s+(\S+?)[,\s]", p):
            a, b = _lat(m.group(1)), _lat(m.group(2))
            if a is not None and b is not None:
                lat_s, lat_n = min(a, b), max(a, b)
        if lat_s is None and (m := re.search(r"(north|south) of\s+(\S+)", p)):
            v = _lat(m.group(2))
            if v is not None:
                lat_s, lat_n = (v, None) if m.group(1) == "north" else (None, v)
        vel = None
        if m := re.search(r"(\d{1,2})(?:\s*(?:-|to)\s*(\d{1,2}))?\s*kt", p):
            vel = [int(m.group(1)), int(m.group(2) or m.group(1))]
        salida.append({"lon": lon, "lat_s": lat_s, "lat_n": lat_n, "puntos": pts if len(pts) >= 2 else [],
                       "velocidad_kt": vel, "cerca": ZONA_CERCA[0] <= lon <= ZONA_CERCA[1], "texto": _limpio(p)})
    return salida


def _limpio(texto):
    """Sin enlaces: el producto trae direcciones de páginas que no se publican aquí."""
    return re.sub(r"\s+", " ", re.sub(r"(?:https?://|www\.)\S+", "", texto)).strip()


def lat_en(lineas, lon):
    """Latitud de la línea (vaguada o ZCIT) en esa longitud, por interpolación entre los puntos que la contienen."""
    for linea in lineas:
        pts = linea["puntos"]
        for (la1, lo1), (la2, lo2) in zip(pts, pts[1:]):
            if min(lo1, lo2) <= lon <= max(lo1, lo2) and lo1 != lo2:
                return round(la1 + (la2 - la1) * (lon - lo1) / (lo2 - lo1), 2), linea["tipo"]
    return None, None


def _km(lat1, lat2):
    return round(abs(lat1 - lat2) * 111.2)


def posicion(lat):
    """Dónde queda la línea respecto de las islas: 'encima', 'norte' o 'sur', y a cuántos km del borde y de Puerto Ayora."""
    if lat is None:
        return {"al": None, "km_islas": None, "km_puerto_ayora": None}
    al = "encima" if ISLAS_S <= lat <= ISLAS_N else "norte" if lat > ISLAS_N else "sur"
    borde = 0 if al == "encima" else _km(lat, ISLAS_N if al == "norte" else ISLAS_S)
    return {"al": al, "km_islas": borde, "km_puerto_ayora": _km(lat, PUERTO_AYORA_LAT)}


def _miles(n):
    return f"{n:,}".replace(",", ".")


def frases(lineas, ondas_, lat_gal, tipo_gal):
    salida = []
    nombre = {"vaguada_monzonica": "La vaguada monzónica (el tramo de la ZCIT pegado al continente)", "zcit": "La ZCIT"}
    if lat_gal is not None:
        pos = posicion(lat_gal)
        lado = "norte" if lat_gal > PUERTO_AYORA_LAT else "sur"
        if pos["al"] == "encima":
            donde = f"pasa sobre el archipiélago, a unos {_miles(pos['km_puerto_ayora'])} km al {lado} de Puerto Ayora"
        else:
            donde = f"pasa a unos {_miles(pos['km_islas'])} km al {pos['al']} de las islas"
        salida.append(f"{nombre.get(tipo_gal, 'La ZCIT')} {donde}, a la altura de 90° O.")
        if pos["km_islas"] <= 300:
            salida.append("Con la ZCIT tan cerca suelen aumentar los chubascos y las tormentas en las islas.")
    elif lineas:
        salida.append("La ZCIT no cruza la longitud de Galápagos en este análisis.")
    cerca = [o for o in ondas_ if o["cerca"]]
    for o in cerca:
        v = o["velocidad_kt"]
        vel = f", avanza hacia el oeste a {v[0]}{'–' + str(v[1]) if v[1] != v[0] else ''} nudos (≈ {round(v[0] * 1.852)} km/h)" if v else ""
        salida.append(f"Hay una onda tropical en {abs(o['lon']):g}° O{vel}.")
    if not cerca:
        salida.append("No hay ondas tropicales analizadas entre 80° y 100° O.")
    return salida


# ── Resumen en español con el modelo de lenguaje (opcional) ──────────────────
def resumen_ia(texto):
    try:
        from django.conf import settings

        if not getattr(settings, "IA_MODELO", None):
            return None
        from pydantic import BaseModel, Field
        from pydantic_ai import Agent

        class Resumen(BaseModel):
            resumen: str = Field(description="Qué dice el texto sobre Ecuador, Galápagos y el mar alrededor, en 1 a 3 frases claras en español, máximo 350 caracteres. Sin inventar nada.")
            menciona_galapagos: bool = Field(description="True si el texto nombra las islas Galápagos.")

        agente = Agent(settings.IA_MODELO, output_type=Resumen, retries=1, instructions=(
            "Lees la discusión del tiempo tropical del Pacífico este del Centro Nacional de Huracanes de Estados Unidos. "
            "Resume para vecinos de Galápagos lo que dice de la ZCIT, la vaguada monzónica, las ondas tropicales y el mar "
            "frente a Ecuador y Galápagos. Español claro, sin siglas sin explicar, sin recomendaciones propias. "
            "Las alturas de ola van en metros (1 ft = 0,3 m) y los vientos en km/h (1 kt = 1,85 km/h)."))
        r = agente.run_sync(_limpio(texto)[:12000], model_settings={"timeout": 60}).output
        return {"texto": r.resumen[:400], "menciona_galapagos": r.menciona_galapagos, "modelo": str(settings.IA_MODELO)[:60]}
    except Exception:
        return None


# ── Armar y exportar ─────────────────────────────────────────────────────────
def leer(texto, con_ia=False):
    """Del texto del producto al diccionario de zcit.json."""
    sec = secciones(texto)
    zcit_txt = next((v for k, v in sec.items() if "CONVERGENCE" in k or "ITCZ" in k), "")
    ondas_txt = next((v for k, v in sec.items() if "TROPICAL WAVE" in k), "")
    ecuador_txt = next((v for k, v in sec.items() if "ECUADOR" in k), "")
    lineas = lineas_zcit(zcit_txt)
    o = ondas(ondas_txt)
    lat_gal, tipo_gal = lat_en(lineas, -90.0)
    e, a = emitido(texto), analisis(texto)
    return {
        "emitido": e.isoformat() if e else None,
        "analisis": a.isoformat() if a else None,
        "fuente": "NHC (NOAA), Tropical Weather Discussion del Pacífico este",
        "aviso": AVISO,
        "cobertura_sur": -3.4,
        "lineas": lineas,
        "conveccion": conveccion(zcit_txt),
        "ondas": o,
        "galapagos": {"lat_zcit_90o": lat_gal, "tipo": tipo_gal, **posicion(lat_gal)},
        "frases": frases(lineas, o, lat_gal, tipo_gal),
        "texto_original": {"zcit": _limpio(zcit_txt), "ecuador": _limpio(ecuador_txt)},
        "resumen_ia": resumen_ia(zcit_txt + "\n\n" + ondas_txt + "\n\n" + ecuador_txt) if con_ia else None,
    }


def exportar(destino=None, texto=None, con_ia=True):
    """Baja la discusión (o usa `texto`) y escribe zcit.json en la carpeta (por defecto CLIMA_SALIDA)."""
    carpeta = Path(destino or _ajuste("CLIMA_SALIDA") or ".")
    t0 = time.monotonic()
    try:
        if texto is None:
            url = _ajuste("CLIMA_NHC_TWD_URL")
            if not url:
                return {"error": "CLIMA_NHC_TWD_URL vacía"}
            texto = _bajar(url).decode("utf-8", "replace")
        datos = {"generado": datetime.now(UTC).isoformat(timespec="seconds"), **leer(texto, con_ia=con_ia)}
        _escribir(carpeta / "zcit.json", datos)
        _corrida("nhc_zcit", t0, True, len(datos["lineas"]) + len(datos["ondas"]))
        return {"carpeta": str(carpeta), "emitido": datos["emitido"], "lineas": len(datos["lineas"]), "ondas": len(datos["ondas"]),
                "frases": datos["frases"]}
    except Exception as e:
        _corrida("nhc_zcit", t0, False, error=type(e).__name__)
        raise

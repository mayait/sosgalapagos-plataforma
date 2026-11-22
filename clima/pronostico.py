"""Pronóstico: guardar lo que dijo cada modelo y lo que se publicó, y medirlo contra lo que llovió.

El pronóstico lo sigue calculando el recolector anterior (etapa 5 del plan). Aquí se guarda
cada emisión en la base, cosa que antes no se hacía, y se verifica sola: sin eso no hay forma
de saber si un cambio lo mejora o lo empeora.
"""
import gzip
import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

from django.conf import settings
from django.db import connection

from .consultas import GALAPAGOS
from .models import PronosticoEmitido, PronosticoModelo

UMBRAL_MM = 20  # «lluvia fuerte»: 20 mm o más en el día

# Puntos del pronóstico, en el orden en que vienen en los archivos, con las estaciones que
# sirven para verificar cada uno. Lo observado es el máximo entre las estaciones con el día completo.
PUNTOS = [
    {"id": "cascada-alta", "nombre": "Cuenca alta de La Cascada", "zona": "la-cascada", "tipo": "alta",
     "estaciones": ["ambient/miconia", "ierse/n_glps09", "ambient/manzanillo_espol", "ierse/n_glps05", "ierse/n_glps01"]},
    {"id": "puerto-ayora", "nombre": "Puerto Ayora", "zona": "la-cascada", "tipo": "costa",
     "estaciones": ["inamhi/M0191", "ambient/evolucion", "ambient/epmapasc_espol", "weatherlink/pa_weatherlink", "wunderground/casa_marina", "tempest/punta_estrada"]},
    {"id": "santa-rosa", "nombre": "Santa Rosa", "zona": "santa-cruz-alta", "tipo": "alta", "estaciones": ["ierse/n_glps09", "ambient/miconia"]},
    {"id": "el-junco", "nombre": "El Junco / El Progreso", "zona": "san-cristobal", "tipo": "alta", "estaciones": ["gsc/junco", "gsc/mirador", "gsc/cerro_alto"]},
    {"id": "puerto-baquerizo", "nombre": "Puerto Baquerizo Moreno", "zona": "san-cristobal", "tipo": "costa", "estaciones": ["inamhi/M0221", "gsc/gsc", "gsc/merceditas"]},
    {"id": "sierra-negra", "nombre": "Parte alta de Sierra Negra", "zona": "isabela", "tipo": "alta", "estaciones": []},
    {"id": "puerto-villamil", "nombre": "Puerto Villamil", "zona": "isabela", "tipo": "costa", "estaciones": []},
]
HORAS_MINIMAS = 20  # un día de estación cuenta si transmitió al menos 20 de sus 24 horas


def _dia_local(t_iso):
    """La lluvia de una hora del modelo es la suma de la hora que TERMINA en t: cuenta para el día
    de Galápagos en que EMPIEZA esa hora. (La misma regla del recolector.)"""
    return (datetime.fromisoformat(t_iso).replace(tzinfo=timezone.utc) - timedelta(hours=1)).astimezone(GALAPAGOS).date()


def totales_por_dia(horas, valores):
    """{día: mm} solo de los días completos (24 horas) y sin huecos."""
    dias = {}
    for t, v in zip(horas, valores):
        d = dias.setdefault(_dia_local(t), [0, 0.0, False])
        d[0] += 1
        if v is None:
            d[2] = True
        else:
            d[1] += v
    return {dia: round(mm, 2) for dia, (n, mm, hueco) in dias.items() if n >= 24 and not hueco}


def _percentil(ordenados, q):
    i = q * (len(ordenados) - 1)
    a, b = int(i), min(int(i) + 1, len(ordenados) - 1)
    return ordenados[a] + (ordenados[b] - ordenados[a]) * (i - a)


def filas_de_archivo(nombre, contenido):
    """Convierte una respuesta guardada de los modelos en filas de PronosticoModelo (sin guardar)."""
    m = re.match(r"(\d{8}T\d{2})_(.+)\.json(\.gz)?$", nombre)
    if not m:
        return []
    obtenido = datetime.strptime(m.group(1), "%Y%m%dT%H").replace(tzinfo=timezone.utc)
    hoy = obtenido.astimezone(GALAPAGOS).date()
    puntos = contenido if isinstance(contenido, list) else [contenido]
    filas = []
    for punto, datos in zip(PUNTOS, puntos):
        h = datos.get("hourly") or {}
        horas = h.get("time") or []
        if m.group(2) == "deterministas":
            for clave, valores in h.items():
                if not clave.startswith("precipitation_"):
                    continue
                for dia, mm in totales_por_dia(horas, valores).items():
                    filas.append(PronosticoModelo(punto=punto["id"], modelo=clave[len("precipitation_"):], obtenido=obtenido, fecha=dia,
                                                  anticipacion=(dia - hoy).days, mm=mm))
        else:  # un conjunto: una serie por miembro
            miembros = [totales_por_dia(horas, v) for k, v in h.items() if k.startswith("precipitation")]
            for dia in sorted(set().union(*miembros) if miembros else []):
                mm = sorted(x[dia] for x in miembros if dia in x)
                if len(mm) < 0.8 * len(miembros):
                    continue
                filas.append(PronosticoModelo(punto=punto["id"], modelo="conjunto:" + m.group(2), obtenido=obtenido, fecha=dia, anticipacion=(dia - hoy).days,
                                              mm=round(_percentil(mm, 0.5), 2), p90=round(_percentil(mm, 0.9), 2), miembros=len(mm),
                                              prob20=round(sum(1 for x in mm if x >= UMBRAL_MM) / len(mm), 3)))
    return [f for f in filas if 0 <= f.anticipacion <= 7]


def guardar_archivo(carpeta=None, limite=None):
    """Lee las respuestas guardadas que aún no están en la base. Devuelve (archivos leídos, filas nuevas)."""
    carpeta = Path(carpeta or settings.CLIMA_PRONOSTICO_DIR) / "archivo"
    ultimo = {(p, mo, f): mm for p, mo, f, mm in PronosticoModelo.objects.order_by("obtenido").values_list("punto", "modelo", "fecha", "mm")}
    # Como solo se guardan los cambios, hay horas sin ninguna fila: se relee desde 18 horas antes de lo
    # último guardado (los modelos cambian cada 6 o 12 horas), que alcanza para no saltarse nada.
    mas_reciente = PronosticoModelo.objects.order_by("-obtenido").values_list("obtenido", flat=True).first()
    corte = mas_reciente - timedelta(hours=18) if mas_reciente else None
    leidos = nuevas = 0
    for ruta in sorted(carpeta.glob("*/*.json*")):
        m = re.match(r"(\d{8}T\d{2})_", ruta.name)
        if not m:
            continue
        cuando = datetime.strptime(m.group(1), "%Y%m%dT%H").replace(tzinfo=timezone.utc)
        if corte and cuando < corte:
            continue
        try:
            contenido = json.load(gzip.open(ruta) if ruta.suffix == ".gz" else open(ruta))
        except (OSError, ValueError):
            continue
        leidos += 1
        # Solo se guarda lo que cambió respecto de lo último que se sabía de ese punto, modelo y día.
        filas = [f for f in filas_de_archivo(ruta.name, contenido) if ultimo.get((f.punto, f.modelo, f.fecha)) != f.mm]
        for f in filas:
            ultimo[(f.punto, f.modelo, f.fecha)] = f.mm
        nuevas += len(PronosticoModelo.objects.bulk_create(filas, ignore_conflicts=True))
        if limite and leidos >= limite:
            break
    return leidos, nuevas


def guardar_emitido(ruta=None):
    """Guarda lo que el panel está publicando ahora, si cambió desde la última vez. Devuelve filas nuevas."""
    try:
        p = json.loads(Path(ruta or settings.CLIMA_PRONOSTICO_JSON).read_text())
        emitido = datetime.fromisoformat(p["generado"].replace("Z", "+00:00")).replace(minute=0, second=0, microsecond=0)
        hoy = datetime.fromisoformat(p["hoy_local"]).date()
    except (OSError, ValueError, KeyError):
        return 0
    filas = []
    for zona in (p.get("zonas") or {}).values():
        for punto in zona.get("puntos") or []:
            anterior = {f: pr for f, pr in PronosticoEmitido.objects.filter(punto=punto["id"]).order_by("emitido").values_list("fecha", "prob20")}
            for d in punto.get("dias") or []:
                fecha = datetime.fromisoformat(d["fecha"]).date()
                prob = d.get("prob") or {}
                if fecha in anterior and anterior[fecha] == prob.get("20"):
                    continue
                filas.append(PronosticoEmitido(punto=punto["id"], emitido=emitido, fecha=fecha, anticipacion=(fecha - hoy).days,
                                               prob10=prob.get("10"), prob20=prob.get("20"), prob50=prob.get("50"), consenso=d.get("consenso"),
                                               n_modelos=d.get("n_modelos") or 0, mediana_mm=d.get("mm_modelos_mediana"), nivel=d.get("nivel") or "",
                                               calibrado=bool(d.get("calibrado"))))
    return len(PronosticoEmitido.objects.bulk_create(filas, ignore_conflicts=True))


# ── Verificación ─────────────────────────────────────────────────────────────
def observado(desde, hasta):
    """{(punto, día): mm} con lo que llovió: el máximo entre las estaciones del punto con el día completo.

    No cuentan los sensores marcados como dañados en ese día.
    """
    salida = {}
    with connection.cursor() as c:
        for punto in PUNTOS:
            if not punto["estaciones"]:
                continue
            c.execute(
                """SELECT dia, max(mm) FROM (
                     SELECT (h.hora - interval '6 hours')::date AS dia, h.estacion_id, sum(h.suma) AS mm, count(*) AS horas
                     FROM clima_horaria h JOIN clima_estacion e ON e.id = h.estacion_id
                     WHERE h.variable = 'lluvia_mm' AND e.fuente || '/' || e.codigo = ANY(%s)
                       AND h.hora >= %s AND h.hora < %s
                       AND NOT EXISTS (SELECT 1 FROM clima_estaciondanada d WHERE d.estacion_id = h.estacion_id AND d.variable = 'lluvia_mm'
                                       AND h.hora >= d.desde AND (d.hasta IS NULL OR h.hora < d.hasta))
                     GROUP BY 1, 2 HAVING count(*) >= %s) x GROUP BY 1""",
                [punto["estaciones"], datetime.combine(desde, datetime.min.time(), GALAPAGOS), datetime.combine(hasta, datetime.min.time(), GALAPAGOS) + timedelta(days=1), HORAS_MINIMAS],
            )
            for dia, mm in c.fetchall():
                salida[(punto["id"], dia)] = round(mm, 1)
    return salida


def _ultimo(consulta, orden, clave, campos):
    """De cada combinación de `clave` se queda con la última fila según `orden`."""
    vistos = {}
    for fila in consulta.order_by(orden).values(*clave, *campos):
        vistos[tuple(fila[k] for k in clave)] = fila
    return vistos.values()


def verificar(dias=45, hoy=None):
    """Compara lo pronosticado con lo que llovió en los últimos `dias`. Devuelve un resumen para la API.

    - Por modelo y anticipación: error medio, sesgo, y cuántos días de lluvia fuerte avisó o se le pasaron.
    - Por punto y anticipación: el puntaje de Brier de la probabilidad publicada, frente a decir siempre
      la frecuencia observada (habilidad > 0 significa que aporta).
    """
    hoy = hoy or datetime.now(GALAPAGOS).date()
    desde = hoy - timedelta(days=dias)
    obs = observado(desde, hoy - timedelta(days=1))  # el día de hoy no ha terminado
    eventos = sum(1 for v in obs.values() if v >= UMBRAL_MM)

    modelos = {}
    for f in _ultimo(PronosticoModelo.objects.filter(fecha__gte=desde, fecha__lt=hoy, anticipacion__gte=0), "obtenido", ["punto", "modelo", "fecha", "anticipacion"], ["mm", "prob20"]):
        o = obs.get((f["punto"], f["fecha"]))
        if o is None or f["mm"] is None:
            continue
        m = modelos.setdefault((f["modelo"], f["anticipacion"]), {"n": 0, "err": 0.0, "sesgo": 0.0, "eventos": 0, "avisados": 0, "falsas": 0, "brier": 0.0, "nb": 0})
        m["n"] += 1
        m["err"] += abs(f["mm"] - o)
        m["sesgo"] += f["mm"] - o
        fuerte, dijo = o >= UMBRAL_MM, f["mm"] >= UMBRAL_MM
        m["eventos"] += fuerte
        m["avisados"] += fuerte and dijo
        m["falsas"] += dijo and not fuerte
        if f["prob20"] is not None:
            m["brier"] += (f["prob20"] - fuerte) ** 2
            m["nb"] += 1
    por_modelo = [
        {"modelo": mo, "anticipacion": a, "dias": m["n"], "error_medio_mm": round(m["err"] / m["n"], 1), "sesgo_mm": round(m["sesgo"] / m["n"], 1),
         "dias_de_lluvia_fuerte": m["eventos"], "avisados": m["avisados"], "falsas_alarmas": m["falsas"],
         "brier": round(m["brier"] / m["nb"], 3) if m["nb"] else None}
        for (mo, a), m in sorted(modelos.items())
    ]

    publicados = {}
    for f in _ultimo(PronosticoEmitido.objects.filter(fecha__gte=desde, fecha__lt=hoy, anticipacion__gte=0, prob20__isnull=False), "emitido", ["punto", "fecha", "anticipacion"], ["prob20"]):
        o = obs.get((f["punto"], f["fecha"]))
        if o is None:
            continue
        p = publicados.setdefault((f["punto"], f["anticipacion"]), {"n": 0, "brier": 0.0, "eventos": 0})
        p["n"] += 1
        p["eventos"] += o >= UMBRAL_MM
        p["brier"] += (f["prob20"] - (o >= UMBRAL_MM)) ** 2
    por_punto = []
    for (punto, a), p in sorted(publicados.items()):
        base = p["eventos"] / p["n"]
        referencia = base * (1 - base)  # Brier de decir siempre la frecuencia observada
        por_punto.append({"punto": punto, "anticipacion": a, "dias": p["n"], "dias_de_lluvia_fuerte": p["eventos"], "brier": round(p["brier"] / p["n"], 3),
                          "habilidad": round(1 - (p["brier"] / p["n"]) / referencia, 2) if referencia > 0 else None})
    return {
        "desde": desde, "hasta": hoy - timedelta(days=1), "umbral_mm": UMBRAL_MM,
        "dias_observados": len(obs), "dias_de_lluvia_fuerte": eventos,
        "aviso": "Verificación automática y preliminar. Con pocos días de lluvia fuerte las cifras cambian mucho de una semana a otra.",
        "por_modelo": por_modelo, "publicado": por_punto,
        "guardado": {"modelos": PronosticoModelo.objects.count(), "publicados": PronosticoEmitido.objects.count()},
    }


# ── Recalibración con lo medido ──────────────────────────────────────────────
# Los modelos globales no ven la montaña de una isla pequeña: en noviembre de 2026 se quedaron
# cortos por 35–45 mm al día. Sus milímetros no sirven tal cual, pero sí ordenan bien los días:
# aquí se aprende, con los pares guardados, qué probabilidad de lluvia fuerte corresponde a
# cada cantidad pronosticada. Es una regresión logística de dos parámetros por grupo, sin
# librerías, validada dejando fuera un día cada vez.
import math  # noqa: E402

EN_CONSENSO = ("ecmwf_ifs025", "ecmwf_aifs025_single", "gfs_seamless", "icon_seamless", "ukmo_seamless", "meteofrance_seamless", "gem_seamless", "ecmwf_ifs")
PLAZOS = {0: "0-1", 1: "0-1", 2: "2-3", 3: "2-3", 4: "4-5", 5: "4-5"}
MINIMO_PARES, MINIMO_EVENTOS = 30, 6
TIPO = {p["id"]: p["tipo"] for p in PUNTOS}


def _mediana(valores):
    v = sorted(valores)
    return v[len(v) // 2] if len(v) % 2 else (v[len(v) // 2 - 1] + v[len(v) // 2]) / 2


def predictor(mm_modelos):
    """De lo que dicen los modelos a un solo número: el logaritmo de la media entre su mediana y su máximo.

    El máximo entra porque en estas islas el modelo que más llueve suele ser el menos equivocado.
    """
    return math.log1p((_mediana(mm_modelos) + max(mm_modelos)) / 2)


def _por_dia_de_emision(desde, hasta):
    """{(punto, fecha, anticipación): [mm de cada modelo del consenso]} con lo último que se supo ese día."""
    filas = _ultimo(PronosticoModelo.objects.filter(fecha__gte=desde, fecha__lte=hasta, anticipacion__gte=0, anticipacion__lte=5, modelo__in=EN_CONSENSO, mm__isnull=False),
                    "obtenido", ["punto", "modelo", "fecha", "anticipacion"], ["mm"])
    salida = {}
    for f in filas:
        salida.setdefault((f["punto"], f["fecha"], f["anticipacion"]), []).append(f["mm"])
    return {k: v for k, v in salida.items() if len(v) >= 4}


def _ajustar(pares, l2=0.05, vueltas=60):
    """Regresión logística P(fuerte) = 1 / (1 + e^-(a + b·x)) por Newton, con una penalización suave."""
    a = b = 0.0
    for _ in range(vueltas):
        ga = gb = haa = hab = hbb = 0.0
        for x, y in pares:
            p = 1 / (1 + math.exp(-max(-30, min(30, a + b * x))))
            ga += p - y
            gb += (p - y) * x
            w = p * (1 - p)
            haa += w
            hab += w * x
            hbb += w * x * x
        ga += l2 * a
        gb += l2 * b
        haa += l2
        hbb += l2
        det = haa * hbb - hab * hab
        if abs(det) < 1e-12:
            break
        da, db = (hbb * ga - hab * gb) / det, (haa * gb - hab * ga) / det
        a, b = a - da, b - db
        if abs(da) + abs(db) < 1e-7:
            break
    return a, b


def _prob(a, b, x):
    return 1 / (1 + math.exp(-max(-30, min(30, a + b * x))))


def recalibrar(dias=60, hoy=None, guardar=True):
    """Ajusta y valida una curva por grupo (alta, costa) y plazo. Devuelve la lista de resultados."""
    from .models import Calibracion

    hoy = hoy or datetime.now(GALAPAGOS).date()
    desde, hasta = hoy - timedelta(days=dias), hoy - timedelta(days=1)
    obs = observado(desde, hasta)
    grupos = {}
    for (punto, fecha, ant), mm in _por_dia_de_emision(desde, hasta).items():
        o = obs.get((punto, fecha))
        if o is not None:
            grupos.setdefault((TIPO[punto], PLAZOS[ant]), []).append((fecha, predictor(mm), 1.0 if o >= UMBRAL_MM else 0.0))
    resultados = []
    for (grupo, plazo), filas in sorted(grupos.items()):
        eventos = int(sum(y for _, _, y in filas))
        if len(filas) < MINIMO_PARES or eventos < MINIMO_EVENTOS or eventos > len(filas) - MINIMO_EVENTOS:
            continue  # sin días de los dos tipos no hay nada que aprender
        # Validación: se deja fuera un día entero cada vez (todos sus puntos y plazos), se ajusta con el resto y se predice.
        errores = base = 0.0
        for dia in sorted({f for f, _, _ in filas}):
            dentro = [(x, y) for f, x, y in filas if f != dia]
            fuera = [(x, y) for f, x, y in filas if f == dia]
            a, b = _ajustar(dentro)
            frecuencia = sum(y for _, y in dentro) / len(dentro)
            errores += sum((_prob(a, b, x) - y) ** 2 for x, y in fuera)
            base += sum((frecuencia - y) ** 2 for _, y in fuera)
        a, b = _ajustar([(x, y) for _, x, y in filas])
        r = {"grupo": grupo, "plazo": plazo, "a": round(a, 4), "b": round(b, 4), "dias": len(filas), "eventos": eventos,
             "brier": round(errores / len(filas), 4), "brier_base": round(base / len(filas), 4),
             "habilidad": round(1 - errores / base, 3) if base > 0 else None, "desde": desde, "hasta": hasta}
        resultados.append(r)
        if guardar:
            Calibracion.objects.create(**r)
    return resultados


def vigentes():
    """La última calibración de cada grupo y plazo que demostró aportar (habilidad > 0)."""
    from .models import Calibracion

    salida = {}
    for c in Calibracion.objects.order_by("creada"):
        salida[(c.grupo, c.plazo)] = c
    return {k: c for k, c in salida.items() if c.habilidad is not None and c.habilidad > 0}


def proximos_dias(hoy=None):
    """Para cada punto y cada uno de los próximos días: lo publicado, lo recalibrado y lo que dicen los modelos."""
    hoy = hoy or datetime.now(GALAPAGOS).date()
    curvas = vigentes()
    modelos = _ultimo(PronosticoModelo.objects.filter(fecha__gte=hoy, fecha__lte=hoy + timedelta(days=5), mm__isnull=False), "obtenido", ["punto", "modelo", "fecha"], ["mm", "prob20", "obtenido"])
    por_dia = {}
    for f in modelos:
        por_dia.setdefault((f["punto"], f["fecha"]), {})[f["modelo"]] = f
    publicado = {(f["punto"], f["fecha"]): f for f in _ultimo(PronosticoEmitido.objects.filter(fecha__gte=hoy), "emitido", ["punto", "fecha"], ["prob20", "nivel", "emitido"])}
    puntos = []
    for punto in PUNTOS:
        dias = []
        for i in range(6):
            fecha = hoy + timedelta(days=i)
            m = por_dia.get((punto["id"], fecha), {})
            mm = [m[k]["mm"] for k in EN_CONSENSO if k in m]
            conjuntos = [v["prob20"] for k, v in m.items() if k.startswith("conjunto:") and v["prob20"] is not None]
            curva = curvas.get((punto["tipo"], PLAZOS.get(i, "")))
            pub = publicado.get((punto["id"], fecha))
            dias.append({
                "fecha": fecha, "anticipacion": i,
                "publicado": {"prob20": pub["prob20"], "nivel": pub["nivel"]} if pub else None,
                "recalibrado": round(_prob(curva.a, curva.b, predictor(mm)), 2) if curva and len(mm) >= 4 else None,
                "modelos_mm": {"mediana": round(_mediana(mm), 1), "maximo": round(max(mm), 1), "n": len(mm)} if mm else None,
                "conjuntos_prob20_cruda": round(sum(conjuntos) / len(conjuntos), 2) if conjuntos else None,
            })
        puntos.append({"id": punto["id"], "nombre": punto["nombre"], "zona": punto["zona"], "tipo": punto["tipo"], "dias": dias})
    return {
        "hoy": hoy, "umbral_mm": UMBRAL_MM,
        "aviso": "Pronóstico experimental, no oficial. «publicado» es el del panel; «recalibrado» es una curva nueva ajustada con la lluvia medida en las últimas semanas, todavía en evaluación. El pronóstico oficial es del INAMHI.",
        "calibraciones": [{"grupo": c.grupo, "plazo": c.plazo, "dias": c.dias, "eventos": c.eventos, "habilidad": c.habilidad, "creada": c.creada} for c in curvas.values()],
        "puntos": puntos,
    }


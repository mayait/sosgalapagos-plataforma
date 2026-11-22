"""La señal de lluvia fuerte que se publica: de lo que dicen los modelos a una probabilidad por zona.

Es un pronóstico de modelos; NO es un dato oficial ni una alerta. El oficial es el del INAMHI.

Qué se publica y por qué (evaluación con 2024–2026, en el repositorio de datos, clima/pronostico/fase0/):
- Los modelos globales se quedan muy cortos en milímetros en las islas, pero sí «suben» los días en
  que llueve fuerte. Por eso la señal no usa sus milímetros. Usa el **consenso**: el percentil de cada
  modelo dentro de su propia climatología en ese punto (datos/pronostico_calibracion.json), promediado
  entre los modelos. Una curva logística ajustada con la lluvia medida convierte el consenso en la
  probabilidad de que alguna estación de la zona supere 10, 20 o 50 mm en el día.
- Los conjuntos se usan solo para repartir la lluvia en bloques de 6 horas de las próximas 72 horas
  (cuándo se concentra), no para la probabilidad.

Todo sale de PronosticoCorrida (lo que guardó clima/fuentes/modelos.py).
"""
import bisect
import datetime as dt
import json
import math
from pathlib import Path

from .fuentes.base import GALAPAGOS, UTC
from .fuentes.modelos import CONJUNTOS, DETALLE, DETERMINISTAS, DIAS, ZONAS

DATOS = Path(__file__).resolve().parent / "datos"
REGLAS = json.loads((DATOS / "pronostico_reglas.json").read_text())
CAL = json.loads((DATOS / "pronostico_calibracion.json").read_text())


def _iso(t):
    return t.astimezone(UTC).strftime("%Y-%m-%dT%H:%MZ") if t else None


def _local(t):
    return t.astimezone(GALAPAGOS).strftime("%Y-%m-%dT%H:%M") if t else None


def percentil(climatologia, x):
    """Percentil (rango medio, como en la evaluación) de x en la lista de cuantiles."""
    i, j = bisect.bisect_left(climatologia, x), bisect.bisect_right(climatologia, x)
    return ((i + j) / 2) / len(climatologia)


def _cercano(objetivo, disponibles):
    """Clave disponible más cercana a la anticipación objetivo (en empate, la mayor)."""
    return str(min((int(k) for k in disponibles), key=lambda k: (abs(k - objetivo), -k)))


def _pct(xs, q):
    xs = sorted(xs)
    k = (len(xs) - 1) * q
    i = int(k)
    return xs[i] + (xs[min(i + 1, len(xs) - 1)] - xs[i]) * (k - i)


def senal(punto, modelos_dia, fecha, dias_adelante):
    """modelos_dia: {modelo: mm del día}. Devuelve consenso, probabilidades calibradas y nivel, o None.

    En el archivo con que se calibró, «anticipación 1» usa corridas listas hasta la madrugada del
    mismo día: corresponde a «hoy». Por eso el día k usa la anticipación k+1.
    """
    anticipacion = dias_adelante + 1
    climatologia = (CAL.get("climatologia") or {}).get(punto, {})
    percentiles = {}
    for m in CAL["modelos_consenso"]:
        x, c = modelos_dia.get(m), climatologia.get(m)
        if x is None or not c:
            continue
        percentiles[m] = percentil(c[_cercano(anticipacion, c)], x)
    if len(percentiles) < REGLAS["modelos_minimos"]:
        return None
    consenso = sum(percentiles.values()) / len(percentiles)
    grupo = CAL["grupo_punto"].get(punto, {})
    temporada = "lluviosa" if int(fecha[5:7]) in CAL["temporada_lluviosa_meses"] else "garua"
    por_grupo = CAL["calibracion"].get(grupo.get("grupo"), {}).get(temporada, {})
    plazo = _cercano(anticipacion, por_grupo) if por_grupo else None
    curvas = por_grupo.get(plazo, {}) if plazo else {}
    principal = str(REGLAS["umbral_principal"])
    prob, estado = {}, {}
    for umbral, c in curvas.items():
        estado[umbral] = c.get("estado", "sin_datos")
        if estado[umbral] == "ok":
            prob[umbral] = round(1 / (1 + math.exp(-(c["a"] + c["b"] * consenso))), 3)
        elif estado[umbral] == "sin_eventos":
            prob[umbral] = 0.0  # en esta época no se midió ningún día así
        else:
            prob[umbral] = None  # sin habilidad demostrada o pocos datos: no se publica una cifra
    c20, p20 = curvas.get(principal, {}), prob.get(principal)
    # El nivel se decide con la cifra que se publica (redondeada a 5 %), para que no se contradigan.
    p20r = None if p20 is None else round(p20 * 20) / 20
    nivel = "no_evaluable" if p20r is None else next(n["id"] for n in REGLAS["niveles"] if p20r >= n.get("desde", 2) - 1e-9)
    return {"consenso": round(consenso, 3), "n_modelos": len(percentiles), "prob": prob, "nivel": nivel,
            "estado_20": estado.get(principal, "sin_datos"), "frec_normal_20": c20.get("frec_base"),
            "temporada": temporada, "anticipacion_calibracion": plazo, "calibrado": grupo.get("calibrado", False),
            "grupo": grupo.get("grupo"), "prestada_de": c20.get("prestada_de"),
            "percentiles": {m: round(v, 2) for m, v in percentiles.items()}}


def _ultimas():
    """La última corrida recibida de cada modelo: {(tipo, modelo): PronosticoCorrida}."""
    from .models import PronosticoCorrida

    salida = {}
    for c in PronosticoCorrida.objects.order_by("tipo", "modelo", "-recibido").distinct("tipo", "modelo"):
        salida[(c.tipo, c.modelo)] = c
    return salida


def publicado(ahora=None):
    """El pronóstico tal como lo lee el panel (pronostico.json)."""
    ahora = ahora or dt.datetime.now(UTC)
    local = ahora.astimezone(GALAPAGOS)
    hoy = local.strftime("%Y-%m-%d")
    bloque_actual = f"{hoy}T{local.hour // 6 * 6:02d}"
    edad_max = dt.timedelta(hours=REGLAS["edad_maxima_horas"])
    ultimas = _ultimas()
    det = {m: c for (tipo, m), c in ultimas.items() if tipo == "determinista"}
    # Vigente: recibido hace poco y, si se conoce su corrida, que no sea vieja.
    vigentes = {m for m, c in det.items() if ahora - c.recibido < edad_max and not (c.corrida and ahora - c.corrida >= edad_max)}
    conj = {m: c for (tipo, m), c in ultimas.items() if tipo == "conjunto" and ahora - (c.corrida or c.recibido) < edad_max}

    zonas = {}
    for z, zona in ZONAS.items():
        puntos = []
        for p in zona["puntos"]:
            pid = p["id"]
            dias = []
            for k in range(DIAS):
                if k == 0 and local.hour >= 18:
                    continue  # «hoy» casi terminado: lo que queda está en los bloques de 6 horas
                fecha = (local + dt.timedelta(days=k)).strftime("%Y-%m-%d")
                mm = {m: det[m].datos.get(pid, {}).get("dias", {}).get(fecha) for m in vigentes}
                mm = {m: v for m, v in mm.items() if v is not None}
                s = senal(pid, mm, fecha, k)
                if s:
                    dias.append({"fecha": fecha, **s, "mm_modelos_mediana": round(_pct([mm[m] for m in s["percentiles"]], .5), 1)})
            # Bloques de 6 horas (próximas 72): mediana y percentil 90 de los miembros, promediados entre conjuntos.
            bloques = []
            por_conjunto = [c.datos.get(pid, {}).get("bloques6h", {}) for c in conj.values()]
            for b in sorted({b for x in por_conjunto for b in x}):
                if b < bloque_actual:
                    continue
                valores = [x[b] for x in por_conjunto if b in x]
                if len(valores) < 2:
                    continue
                bloques.append({"inicio": b + ":00", "n_conjuntos": len(valores),
                                "mediana": round(sum(_pct(v, .5) for v in valores) / len(valores), 1),
                                "p90": round(sum(_pct(v, .9) for v in valores) / len(valores), 1)})
                if len(bloques) >= 12:
                    break
            detalle = None
            h = det[DETALLE].datos.get(pid, {}).get("horario") if DETALLE in vigentes else None
            if h:
                corte = ahora.strftime("%Y-%m-%dT%H:%M")
                serie = [(_local(dt.datetime.fromisoformat(t).replace(tzinfo=UTC)), v) for t, v in zip(h["t"], h["mm"]) if v is not None and t > corte][:72]
                detalle = {"modelo": DETERMINISTAS[DETALLE][0], "hora_local_fin": [x[0] for x in serie], "mm": [round(x[1], 1) for x in serie]}
            puntos.append({"id": pid, "nombre": p["nombre"], "tipo": p["tipo"], "dias": dias, "bloques6h": bloques, "detalle": detalle})
        zonas[z] = {"nombre": zona["nombre"], "puntos": puntos}

    modelos = []
    for m, (nombre, _) in DETERMINISTAS.items():
        c = det.get(m)
        modelos.append({"id": m, "nombre": nombre, "tipo": "determinista", "miembros": 1, "en_consenso": m in CAL["modelos_consenso"],
                        "corrida_utc": _iso(c and c.corrida), "corrida_local": _local(c and c.corrida), "disponible_local": _local(c and c.disponible),
                        "recibido_local": _local(c and c.recibido), "vigente": m in vigentes})
    for m, _, nombre, miembros in CONJUNTOS:
        c = ultimas.get(("conjunto", m))
        modelos.append({"id": m, "nombre": nombre, "tipo": "conjunto", "miembros": miembros, "en_consenso": False,
                        "corrida_utc": _iso(c and c.corrida), "corrida_local": _local(c and c.corrida), "disponible_local": _local(c and c.disponible),
                        "recibido_local": _local(c and c.recibido), "vigente": m in conj})
    return {"generado": ahora.strftime("%Y-%m-%dT%H:%M:%SZ"), "generado_local": local.strftime("%Y-%m-%dT%H:%M"),
            "hoy_local": hoy, "modelos": modelos, "zonas": zonas,
            "reglas": {k: REGLAS[k] for k in ("version", "umbral_principal", "dias_fiables", "niveles", "grupos", "aviso", "explicacion_horas", "evaluacion")}}

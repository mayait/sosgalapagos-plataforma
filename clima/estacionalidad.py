# SOS Galápagos · © 2026 Universidad San Francisco de Quito (USFQ) · Autor: Julián Maya <jamaya@usfq.edu.ec>
# Todos los derechos reservados. Usar, copiar, modificar o derivar de este código requiere permiso escrito del autor (ver LICENSE).
"""Estacionalidad de la lluvia por estación, con las series diarias largas guardadas en la base.

Para cada serie calcula:
  - climatología mensual de totales: media, p10, mediana, p90 (meses con ≥ 80 % de días);
  - compuesto de años de El Niño fuerte (ONI ≥ 1,5): media mensual de jul(Y)–jun(Y+1);
  - probabilidad suavizada (±15 días, circular) de un día con ≥ 1, ≥ 10 y ≥ 25 mm, por semana del año;
  - lluvia en 24 h para periodos de retorno de 2, 5, 10, 25 y 50 años (Gumbel, método de momentos,
    sobre máximos anuales de años con ≥ 80 % de días);
  - totales mensuales del año en curso y del anterior.

Es un modelo estadístico propio, no un dato oficial.

Series: FCD (Puerto Ayora desde 1965 y Bellavista 1987–2019; licencia CC BY-NC-SA, se cargan con
`manage.py clima_importar fcd`), el histórico diario del GSC desde 2015 y los días completos
(≥ 20 h) que va juntando el recolector (el INAMHI M0191 continúa la serie de Puerto Ayora).
"""
import datetime as dt
import math
import statistics

from django.db import connection

NINO = [1965, 1972, 1982, 1987, 1991, 1997, 2009, 2015, 2023]  # año de inicio del episodio (ONI ≥ 1,5)
SERIES = [  # id, nombre, isla, operador, altitud, estaciones (la primera manda; las siguientes rellenan)
    ("puerto-ayora", "Puerto Ayora", "Santa Cruz", "FCD + INAMHI", 6, ["fcd/puerto-ayora", "inamhi/M0191"]),
    ("bellavista", "Bellavista", "Santa Cruz", "FCD", 194, ["fcd/bellavista"]),
    ("junco", "El Junco", "San Cristóbal", "GSC-USFQ", 548, ["gsc/junco"]),
    ("cerro_alto", "Cerro Alto", "San Cristóbal", "GSC-USFQ", 517, ["gsc/cerro_alto"]),
    ("mirador", "El Mirador", "San Cristóbal", "GSC-USFQ", 387, ["gsc/mirador"]),
    ("merceditas", "Merceditas", "San Cristóbal", "GSC-USFQ", 100, ["gsc/merceditas"]),
]


def dias_de(clave):
    """{fecha: mm} de una estación: su diario histórico y, donde falte, los días completos medidos."""
    fuente, codigo = clave.split("/", 1)
    salida = {}
    with connection.cursor() as c:
        c.execute("""SELECT (o.ts - interval '5 hours')::date, o.valor FROM clima_observacion o JOIN clima_estacion e ON e.id = o.estacion_id
                     WHERE e.fuente = %s AND e.codigo = %s AND o.variable = 'lluvia_dia_mm' AND o.valor IS NOT NULL""", [fuente, codigo])
        salida.update(dict(c.fetchall()))
        c.execute("""SELECT (h.hora - interval '6 hours')::date, sum(h.suma), count(*) FROM clima_horaria h JOIN clima_estacion e ON e.id = h.estacion_id
                     WHERE e.fuente = %s AND e.codigo = %s AND h.variable = 'lluvia_mm' GROUP BY 1""", [fuente, codigo])
        for dia, mm, horas in c.fetchall():
            if horas >= 20:
                salida.setdefault(dia, round(mm, 1))
    return salida


def _pct(xs, p):
    xs = sorted(xs)
    if not xs:
        return None
    k = (len(xs) - 1) * p
    i = int(k)
    return xs[i] + (xs[min(i + 1, len(xs) - 1)] - xs[i]) * (k - i)


def modelo(dias, hoy=None):
    if len(dias) < 365:
        return None
    meses = {}
    for d, v in dias.items():
        meses.setdefault((d.year, d.month), []).append(v)
    total = {k: sum(v) for k, v in meses.items()
             if len(v) >= 0.8 * (dt.date(k[0] + k[1] // 12, k[1] % 12 + 1, 1) - dt.date(k[0], k[1], 1)).days}
    mensual = []
    for m in range(1, 13):
        xs = [v for (_, mm), v in total.items() if mm == m]
        mensual.append({"mes": m, "n": len(xs), "media": round(statistics.mean(xs), 1) if xs else None,
                        "p10": round(_pct(xs, .1), 1) if xs else None, "p50": round(_pct(xs, .5), 1) if xs else None,
                        "p90": round(_pct(xs, .9), 1) if xs else None})
    nino = []
    for m in range(1, 13):
        xs = [total[(y + (1 if m <= 6 else 0), m)] for y in NINO if (y + (1 if m <= 6 else 0), m) in total]
        nino.append(round(statistics.mean(xs), 1) if xs else None)
    # Probabilidad por día del año, suavizada ±15 días.
    por_dia = [[] for _ in range(366)]
    for d, v in dias.items():
        por_dia[min(d.timetuple().tm_yday, 365) - 1].append(v)
    prob = {}
    for umbral in (1, 10, 25):
        semanal = []
        for semana in range(52):
            centro = semana * 7 + 3
            xs = [v for k in range(centro - 15, centro + 16) for v in por_dia[k % 365]]
            semanal.append(round(sum(x >= umbral for x in xs) / len(xs), 4) if xs else None)
        prob[str(umbral)] = semanal
    # Máximos anuales y Gumbel.
    anios = {}
    for d, v in dias.items():
        anios.setdefault(d.year, []).append(v)
    maximos = {y: max(v) for y, v in anios.items() if len(v) >= 0.8 * 365}
    retorno = None
    if len(maximos) >= 8:
        xs = list(maximos.values())
        beta = statistics.stdev(xs) * math.sqrt(6) / math.pi
        mu = statistics.mean(xs) - 0.5772 * beta
        retorno = {str(T): round(mu - beta * math.log(-math.log(1 - 1 / T)), 0) for T in (2, 5, 10, 25, 50)}
    hoy = hoy or dt.date.today()
    actual = {str(y): [round(total[(y, m)], 1) if (y, m) in total else (round(sum(meses[(y, m)]), 1) if (y, m) in meses else None)
                       for m in range(1, 13)] for y in (hoy.year - 1, hoy.year)}
    completo = {str(y): [(y, m) in total for m in range(1, 13)] for y in (hoy.year - 1, hoy.year)}
    mayores = sorted(maximos.items(), key=lambda x: -x[1])[:5]
    return {"desde": min(dias).isoformat(), "hasta": max(dias).isoformat(), "dias": len(dias),
            "anios_completos": len(maximos), "mensual": mensual, "nino": nino, "nino_anios": NINO,
            "prob_semanal": prob, "retorno_24h": retorno, "max_anual_top": [[y, round(v, 1)] for y, v in mayores],
            "anios": actual, "mes_completo": completo}


def calcular():
    salida = []
    for sid, nombre, isla, operador, altitud, estaciones in SERIES:
        dias = {}
        for clave in estaciones:
            for d, v in dias_de(clave).items():
                dias.setdefault(d, v)
        m = modelo(dias)
        if m:
            salida.append({"id": sid, "nombre": nombre, "isla": isla, "operador": operador, "altitud_m": altitud, **m})
    return {"generado": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "series": salida}

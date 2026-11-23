# SOS Galápagos · © 2026 Universidad San Francisco de Quito (USFQ) · Autor: Julián Maya <jamaya@usfq.edu.ec>
# Licencia Apache 2.0 (ver LICENSE y NOTICE): puede reutilizarse dando crédito.
"""Mareas para el panel: predicción astronómica, nivel medido por los mareógrafos y anomalía.

- La predicción astronómica (datos/mareas_prediccion.json) la genera el repositorio de datos
  (clima/scripts/05_mareas.py) con años de registros del UHSLC. Es un modelo propio, no la tabla oficial.
- Lo medido son los mareógrafos de la red IOC (clima/fuentes/ioc.py).
- La anomalía es lo medido menos lo predicho; en 2026 recoge sobre todo la señal de El Niño.
- Para los puertos sin mareógrafo, las pleamares salen de la tabla oficial del INOCAR y, si falta,
  de Stormglass; el oleaje, de Stormglass (o de Open-Meteo si Stormglass no tiene datos).

Las alturas de la predicción van en cm respecto del nivel medio 2017–2024 de cada mareógrafo.
"""
import datetime as dt
import json
from pathlib import Path

from django.db import connection

from .fuentes.base import UTC

ARCHIVO = Path(__file__).resolve().parent / "datos" / "mareas_prediccion.json"
VENTANA_H = 72
_memoria = {}
# Puertos sin mareógrafo: identificador que usa el panel → puerto de las tablas del mar.
SIN_MAREOGRAFO = {"baquerizo": ("san-cristobal", "Puerto Baquerizo Moreno"), "villamil": ("isabela", "Puerto Villamil")}


def prediccion():
    if ARCHIVO.exists() and _memoria.get("mtime") != ARCHIVO.stat().st_mtime:
        _memoria.update(mtime=ARCHIVO.stat().st_mtime, datos=json.loads(ARCHIVO.read_text()))
    return _memoria.get("datos")


def _z(t):
    return t.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _de_z(texto):
    return dt.datetime.fromisoformat(texto.replace("Z", "+00:00"))


def calcular(ahora=None):
    P = prediccion()
    if not P:
        return None
    ahora = ahora or dt.datetime.now(UTC)
    paso = dt.timedelta(minutes=P["paso_min"])
    inicio = (ahora - dt.timedelta(hours=VENTANA_H)).replace(second=0, microsecond=0)
    inicio -= dt.timedelta(minutes=inicio.minute % P["paso_min"])
    fin = ahora + dt.timedelta(hours=VENTANA_H)
    salida = {"referencia": "nivel medio 2017–2024 de cada mareógrafo", "metodo": P["metodo"], "estaciones": {}}
    for cod, e in P["estaciones"].items():
        i0, n = int((inicio - _de_z(e["t0"])) / paso), int((fin - inicio) / paso)
        if i0 < 0 or i0 + n > len(e["h_cm"]):
            continue  # la predicción no cubre este tramo: hay que regenerarla en el repositorio de datos
        predicho, medio = e["h_cm"][i0:i0 + n], e["nivel_medio_ref_cm_cero_uhslc"]
        # Lo medido (cero UHSLC, en metros) → cm sobre el nivel medio, en bloques del mismo paso.
        medido, grupos = [None] * n, {}
        with connection.cursor() as c:
            c.execute("""SELECT o.ts, o.valor FROM clima_observacion o JOIN clima_estacion s ON s.id = o.estacion_id
                         WHERE s.fuente = 'ioc' AND s.codigo = %s AND o.variable = 'nivel_mar_m' AND o.ts >= %s AND o.valor IS NOT NULL""", [cod, inicio])
            for ts, v in c.fetchall():
                k = int((ts - inicio) / paso)
                if 0 <= k < n:
                    grupos.setdefault(k, []).append(v * 100 - medio)
        for k, vs in grupos.items():
            medido[k] = round(sum(vs) / len(vs), 1)
        # Anomalía: medido − predicho en las últimas 6 horas.
        k_ahora = int((ahora - inicio) / paso)
        diferencias = [medido[k] - predicho[k] for k in range(max(0, k_ahora - 36), min(n, k_ahora + 1)) if medido[k] is not None]
        mensual = e.get("anomalia_mensual_cm", {})
        if len(diferencias) >= 12:
            anomalia, origen = round(sum(diferencias) / len(diferencias), 1), "mareógrafo, últimas 6 h"
        elif mensual:
            anomalia, origen = list(mensual.values())[-1], f"media mensual UHSLC {list(mensual)[-1]}"
        else:
            anomalia, origen = 0.0, "sin datos"
        proximos = [{"t": x[0], "tipo": "pleamar" if x[2] == "P" else "bajamar", "pred_cm": x[1], "esperado_cm": round(x[1] + anomalia, 1)}
                    for x in e["extremos"] if ahora <= _de_z(x[0]) <= fin]
        pleamares = [x for x in proximos if x["tipo"] == "pleamar"]
        salida["estaciones"][cod] = {
            "nombre": e["nombre"], "anomalia_cm": anomalia, "anomalia_fuente": origen,
            "anomalia_mensual_cm": dict(list(mensual.items())[-18:]), "validacion": e["validacion"],
            "t0": _z(inicio), "paso_min": P["paso_min"], "ahora_i": k_ahora,
            "pred_cm": predicho, "obs_cm": medido, "proximos": proximos[:8],
            "max_72h": max(pleamares, key=lambda x: x["esperado_cm"]) if pleamares else None,
        }
    salida["modelo"] = _sin_mareografo(ahora)
    return salida


def _sin_mareografo(ahora):
    """Pleamares y oleaje de los puertos sin mareógrafo, de las tablas del mar."""
    from .models import MareaExtremo, MarHora

    salida = {}
    for clave, (puerto, nombre) in SIN_MAREOGRAFO.items():
        fuente_marea = next((f for f in ("inocar", "stormglass") if MareaExtremo.objects.filter(puerto=puerto, fuente=f, ts__gte=ahora, tipo="P").exists()), None)
        pleamares = [{"t": _z(e.ts), "nivel_m": e.altura_m} for e in MareaExtremo.objects.filter(puerto=puerto, fuente=fuente_marea, ts__gte=ahora, tipo="P")[:6]] if fuente_marea else []
        referencia = {"inocar": "tabla oficial del INOCAR (sobre el nivel de bajamares de sicigia)", "stormglass": "Stormglass (sobre el nivel medio del mar)"}.get(fuente_marea)
        if not pleamares:  # sin tabla: los picos del nivel modelado
            niveles = list(MarHora.objects.filter(puerto=puerto, fuente="openmeteo", hora__gte=ahora - dt.timedelta(hours=1), nivel_m__isnull=False).order_by("hora").values_list("hora", "nivel_m"))
            for i in range(1, len(niveles) - 1):
                if niveles[i][0] >= ahora and niveles[i][1] >= niveles[i - 1][1] and niveles[i][1] > niveles[i + 1][1]:
                    pleamares.append({"t": _z(niveles[i][0]), "nivel_m": niveles[i][1]})
            pleamares, referencia = pleamares[:6], "modelo Open-Meteo (sobre el nivel medio del mar)" if pleamares else None
        ola = fuente_ola = obtenido = None
        for fuente, etiqueta in (("stormglass", "Stormglass"), ("openmeteo", "Open-Meteo")):
            horas = list(MarHora.objects.filter(puerto=puerto, fuente=fuente, hora__gte=ahora, hora__lte=ahora + dt.timedelta(hours=VENTANA_H), ola_m__isnull=False).values_list("ola_m", "obtenido"))
            if horas:
                ola, fuente_ola, obtenido = max(h[0] for h in horas), etiqueta, max(h[1] for h in horas)
                break
        if pleamares or ola is not None:
            salida[clave] = {"nombre": nombre, "pleamares": pleamares, "pleamares_fuente": referencia, "ola_max_m": ola, "ola_fuente": fuente_ola,
                             "generado": _z(obtenido) if obtenido else None}
    return salida

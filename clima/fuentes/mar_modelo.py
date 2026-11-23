# SOS Galápagos · © 2026 Universidad San Francisco de Quito (USFQ) · Autor: Julián Maya <jamaya@usfq.edu.ec>
# Licencia Apache 2.0 (ver LICENSE y NOTICE): puede reutilizarse dando crédito.
"""Nivel del mar y oleaje modelados (Open-Meteo Marine), para comparar con Stormglass y como reserva.

Marea más nivel modelados cada 15 minutos y altura de ola por hora, de los puertos sin mareógrafo
(Puerto Baquerizo Moreno y Puerto Villamil). Se guarda en MarHora con fuente «openmeteo».
Es un modelo: no es una medición ni la tabla oficial del INOCAR.
"""
import datetime as dt
import urllib.parse

from . import base

FUENTE = "mar_modelo"
PUERTOS = {"san-cristobal": ("Puerto Baquerizo Moreno", -0.902, -89.612), "isabela": ("Puerto Villamil", -0.962, -90.965)}


def filas_de(puerto, p, obtenido):
    from ..models import MarHora

    filas = {}
    m, h = p.get("minutely_15", {}), p.get("hourly", {})
    for t, nivel in zip(m.get("time", []), m.get("sea_level_height_msl", [])):
        filas[t] = MarHora(puerto=puerto, fuente="openmeteo", hora=dt.datetime.fromisoformat(t).replace(tzinfo=base.UTC), nivel_m=nivel, obtenido=obtenido)
    for t, ola in zip(h.get("time", []), h.get("wave_height", [])):
        if t in filas:
            filas[t].ola_m = ola
        else:
            filas[t] = MarHora(puerto=puerto, fuente="openmeteo", hora=dt.datetime.fromisoformat(t).replace(tzinfo=base.UTC), ola_m=ola, obtenido=obtenido)
    return list(filas.values())


def recoger(ahora=None, forzar=False):
    from ..models import MarHora

    ahora = ahora or dt.datetime.now(base.UTC)
    ultimo = MarHora.objects.filter(fuente="openmeteo").order_by("-obtenido").values_list("obtenido", flat=True).first()
    if not forzar and ultimo and (ahora - ultimo).total_seconds() < 3000:
        return 0  # una vez por hora basta
    q = urllib.parse.urlencode({"latitude": ",".join(str(v[1]) for v in PUERTOS.values()), "longitude": ",".join(str(v[2]) for v in PUERTOS.values()),
                                "minutely_15": "sea_level_height_msl", "hourly": "wave_height", "timezone": "GMT", "past_days": 1, "forecast_days": 3})
    d = base.http_json(f"{base.endpoint('CLIMA_OPENMETEO_MARINE_API')}?{q}", espera=60)
    d = d if isinstance(d, list) else [d]
    filas = [f for puerto, p in zip(PUERTOS, d) for f in filas_de(puerto, p, ahora)]
    MarHora.objects.bulk_create(filas, update_conflicts=True, unique_fields=["puerto", "fuente", "hora"], update_fields=["nivel_m", "ola_m", "obtenido"])
    return len(filas)

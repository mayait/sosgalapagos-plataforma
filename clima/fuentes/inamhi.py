# SOS Galápagos · © 2026 Universidad San Francisco de Quito (USFQ) · Autor: Julián Maya <jamaya@usfq.edu.ec>
# Todos los derechos reservados. Usar, copiar, modificar o derivar de este código requiere permiso escrito del autor (ver LICENSE).
"""INAMHI: estaciones automáticas de Puerto Ayora y Puerto Baquerizo Moreno.

Dos servicios: la lluvia de cada 5 minutos de las últimas ~6 horas (etiqueta = inicio del
intervalo) y un historial por hora de 90 días. El historial solo rellena las horas sin datos
de 5 minutos (tras un corte, por ejemplo), como filas de respaldo.

Sus horas son continentales (UTC−5).
"""
import datetime as dt
import json
import urllib.parse

from . import base

FUENTE = "inamhi"
ESTACIONES = {  # código: (lat y lon de la consulta, nombre oficial y localidad, isla, lat, lon, altitud)
    "M0191": (-0.745, -90.315, "CHARLES DARWIN 1 (M0191), Puerto Ayora", "Santa Cruz", -0.743056, -90.3025, 6),
    "M0221": (-0.901, -89.611, "SAN CRISTOBAL-GALAPAGOS (M0221), Puerto Baquerizo", "San Cristóbal", -0.904058, -89.614308, 6),
}


def _hora(fecha, minutos):
    return dt.datetime.fromisoformat(fecha).replace(tzinfo=base.CONTINENTE) + dt.timedelta(minutes=minutos)


def _registrar_estaciones():
    for cod, (_, _, nombre, isla, lat, lon, altitud) in ESTACIONES.items():
        base.estacion(FUENTE, cod, nombre, isla, lat, lon, altitud, "INAMHI")


def filas_de_5min(cod, d):
    """De la respuesta de 5 minutos de una estación a (filas, horas UTC que quedaron cubiertas)."""
    if not d.get("ok") or "intervalo_minutos" not in d:
        raise ValueError(f"respuesta inesperada para {cod}: {str(d)[:200]}")
    paso, inicio = d["intervalo_minutos"], d["inicio"]
    filas, horas = [], set()
    e = next((x for x in d.get("estaciones", []) if x.get("codigo") == cod), None)
    for i, v in enumerate((e or {}).get("mm") or []):
        if v is not None:
            t = _hora(d["fecha"], inicio + paso * i)
            filas.append((cod, "lluvia_mm", t, float(v)))
            horas.add(t.astimezone(base.UTC).replace(minute=0, second=0, microsecond=0))
    te = next((x for x in (d.get("temperatura") or {}).get("estaciones", []) if x.get("codigo") == cod), None)
    for i, v in enumerate((te or {}).get("serie") or []):
        if v is not None:
            filas.append((cod, "temp_c", _hora(d["fecha"], inicio + paso * i), float(v)))
    return filas, horas


def recoger(ahora=None):
    api = base.endpoint("CLIMA_INAMHI_API")
    _registrar_estaciones()
    filas, cubiertas, errores = [], set(), []
    for cod, (qlat, qlon, *_) in ESTACIONES.items():
        try:  # una estación sin datos frescos no deja sin datos a la otra
            nuevas, horas = filas_de_5min(cod, base.http_json(f"{api}/tiempo-real-5min/{qlat}/{qlon}"))
        except Exception as e:
            errores.append(f"{cod}: {type(e).__name__}: {e}"[:160])
            continue
        filas += nuevas
        cubiertas |= {(cod, h) for h in horas}
    n = base.guardar(FUENTE, filas)
    # Donde ya hay datos de 5 minutos, sobran las filas de respaldo de esa hora.
    for cod, hora in cubiertas:
        for variable in ("lluvia_mm", "temp_c"):
            base.borrar(FUENTE, cod, variable, desde=hora, hasta_antes_de=hora + dt.timedelta(hours=1), de_respaldo=True)
    # Una vez por hora: rellenar con el historial las horas sin 5 minutos.
    if (ahora or dt.datetime.now(base.UTC)).minute < 5:
        n += historial(dias=2)
    if len(errores) == len(ESTACIONES):  # ninguna respondió bien: la corrida cuenta como fallo
        raise ValueError("; ".join(errores)[:400])
    return n


def filas_de_historial(d):
    """Del historial por hora a filas de respaldo, solo para las horas sin lluvia de 5 minutos."""
    filas = []
    for f in d.get("filas", []):
        cod = f.get("codigo")
        if cod not in ESTACIONES:
            continue
        hora = dt.datetime.fromisoformat(f["hora"]).replace(tzinfo=base.CONTINENTE)
        if base.existe(FUENTE, cod, "lluvia_mm", desde=hora, hasta=hora + dt.timedelta(minutes=59, seconds=59), de_cinco_min=True):
            continue
        t = hora + dt.timedelta(minutes=30, seconds=base.HORARIO_SEG)
        if f.get("n_lluvia") and f.get("lluvia_mm") is not None:
            filas.append((cod, "lluvia_mm", t, float(f["lluvia_mm"])))
        if f.get("n_temp") and f.get("t_prom") is not None:
            filas.append((cod, "temp_c", t, float(f["t_prom"])))
    return filas


def historial(dias=2, archivo=None):
    """Carga el historial por hora, del servicio o de un JSON guardado."""
    if archivo:
        with open(archivo) as f:
            d = json.load(f)
    else:
        hoy = dt.datetime.now(base.CONTINENTE).date()
        q = urllib.parse.urlencode({"desde": (hoy - dt.timedelta(days=dias)).isoformat(), "hasta": hoy.isoformat(), "tipo": "estacion"})
        d = base.http_json(f"{base.endpoint('CLIMA_INAMHI_API')}/historial?{q}", espera=180)
    _registrar_estaciones()
    return base.guardar(FUENTE, filas_de_historial(d))

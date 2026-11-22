"""Calcula el nivel de lluvia peligrosa en Django, lo guarda y lo compara con el del recolector anterior."""
import logging
import time
from datetime import datetime, timedelta, timezone

from .models import Estado, NivelZona

registro = logging.getLogger(__name__)


def actualizar():
    """Una pasada: calcula para el mismo instante que el recolector anterior y anota si coinciden.

    Devuelve {zonas, coinciden, segundos}.
    """
    from reportes import clima as panel

    from . import nivel

    t0 = time.monotonic()
    viejo = (panel._leer() or {}).get("inundacion") or {}
    # Se calcula para el mismo instante que el anterior, así la comparación es justa.
    try:
        ahora = datetime.fromisoformat(viejo["calculado"].replace("Z", "+00:00"))
        if datetime.now(timezone.utc) - ahora > timedelta(minutes=20):
            ahora = None  # el anterior está parado: se calcula para ahora
    except (KeyError, ValueError):
        ahora = None
    resultado = nivel.calcular(ahora)
    calculado = datetime.fromisoformat(resultado["calculado"].replace("Z", "+00:00"))
    anteriores = {z.get("id"): z for z in viejo.get("zonas") or []} if ahora else {}
    coinciden = 0
    for z in resultado["zonas"]:
        a = anteriores.get(z["id"])
        igual = (a.get("nivel") == z["nivel"]) if a else None
        coinciden += bool(igual)
        NivelZona.objects.update_or_create(
            zona=z["id"], calculado=calculado,
            defaults={"nivel": z["nivel"], "instantaneo": z.get("nivel_instantaneo") or "", "silencio": bool(z.get("silencio")),
                      "lluvia": z.get("R") or {}, "anterior": (a or {}).get("nivel", ""), "coincide": igual},
        )
        if igual is False:
            registro.warning("Nivel distinto en %s: Django «%s», anterior «%s»", z["id"], z["nivel"], a.get("nivel"))
    resultado["segundos"] = round(time.monotonic() - t0, 2)
    Estado.objects.update_or_create(clave="inundacion", defaults={"datos": resultado, "generado": calculado})
    return {"zonas": len(resultado["zonas"]), "coinciden": coinciden, "comparadas": len(anteriores), "segundos": resultado["segundos"]}


def coincidencia(dias=7, ahora=None):
    """Qué tanto coincide el cálculo nuevo con el anterior: el criterio para reemplazarlo."""
    ahora = ahora or datetime.now(timezone.utc)
    filas = NivelZona.objects.filter(calculado__gte=ahora - timedelta(days=dias), coincide__isnull=False)
    total, iguales = filas.count(), filas.filter(coincide=True).count()
    primera = filas.order_by("calculado").values_list("calculado", flat=True).first()
    distintas = [{"zona": f.zona, "cuando": f.calculado, "django": f.nivel, "anterior": f.anterior} for f in filas.filter(coincide=False)[:10]]
    return {"comparaciones": total, "iguales": iguales, "coincidencia_pct": round(100 * iguales / total, 2) if total else None,
            "desde": primera, "dias_comparados": round((ahora - primera).total_seconds() / 86400, 1) if primera else 0, "ultimas_diferencias": distintas}

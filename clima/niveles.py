"""Calcula el nivel de lluvia peligrosa de cada zona y lo guarda: el vigente (Estado) y su historia (NivelZona)."""
import time
from datetime import datetime

from .models import Estado, NivelZona


def actualizar(ahora=None):
    """Una pasada. Devuelve {zonas, segundos}."""
    from . import nivel

    t0 = time.monotonic()
    resultado = nivel.calcular(ahora)
    calculado = datetime.fromisoformat(resultado["calculado"].replace("Z", "+00:00"))
    for z in resultado["zonas"]:
        NivelZona.objects.update_or_create(
            zona=z["id"], calculado=calculado,
            defaults={"nivel": z["nivel"], "instantaneo": z.get("nivel_instantaneo") or "", "silencio": bool(z.get("silencio")), "lluvia": z.get("R") or {}},
        )
    resultado["segundos"] = round(time.monotonic() - t0, 2)
    Estado.objects.update_or_create(clave="inundacion", defaults={"datos": resultado, "generado": calculado})
    return {"zonas": len(resultado["zonas"]), "segundos": resultado["segundos"]}

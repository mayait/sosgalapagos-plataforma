# SOS Galápagos · © 2026 Universidad San Francisco de Quito (USFQ) · Autor: Julián Maya <jamaya@usfq.edu.ec>
# Licencia Apache 2.0 (ver LICENSE y NOTICE): puede reutilizarse dando crédito.
"""El colector del satélite GOES-19.

  manage.py clima_satelite            una pasada
  manage.py clima_satelite --bucle    una pasada cada 5 minutos, para siempre (el servicio «satelite» de Compose)
  manage.py clima_satelite --horas 6  recupera hacia atrás tras un corte
"""
import time

from django.core.management.base import BaseCommand
from django.db import close_old_connections


class Command(BaseCommand):
    help = "Satélite GOES-19: estimación de lluvia y rayos por zona (no es una alerta oficial)"

    def add_arguments(self, parser):
        parser.add_argument("--bucle", action="store_true")
        parser.add_argument("--horas", type=float, default=1.0)
        parser.add_argument("--sin-glm", action="store_true")

    def handle(self, bucle, horas, sin_glm, **opciones):
        from clima.satelite import colector

        while True:
            inicio = time.monotonic()
            close_old_connections()
            try:
                self.stdout.write(str(colector.pasada(horas=horas, con_glm=not sin_glm)))
            except Exception as e:  # el bucle nunca se cae por una pasada mala
                self.stderr.write(f"pasada fallida: {type(e).__name__}: {e}")
            if not bucle:
                return
            time.sleep(max(20, 300 - (time.monotonic() - inicio)))

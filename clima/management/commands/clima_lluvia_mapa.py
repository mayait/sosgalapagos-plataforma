# SOS Galápagos · © 2026 Universidad San Francisco de Quito (USFQ) · Autor: Julián Maya <jamaya@usfq.edu.ec>
# Licencia Apache 2.0 (ver LICENSE y NOTICE): puede reutilizarse dando crédito.
"""Escribe el mapa de lluvia y viento de los modelos (lluvia-mapa.json) para el panel de /clima/.

  manage.py clima_lluvia_mapa                    solo si hay corrida nueva del IFS y pasaron 5 h (si no, no gasta nada)
  manage.py clima_lluvia_mapa --forzar           siempre (gasta ≈ 957 llamadas de Open-Meteo)
  manage.py clima_lluvia_mapa --destino CARPETA  por defecto, CLIMA_SALIDA

Es lluvia de MODELO, no medida ni oficial (ver clima/lluvia_mapa.py).
"""
import os

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from clima import lluvia_mapa


class Command(BaseCommand):
    help = "Escribe el mapa de lluvia y viento de los modelos para /clima/"

    def add_arguments(self, parser):
        parser.add_argument("--destino", default="", help="carpeta o archivo .json (por defecto CLIMA_SALIDA)")
        parser.add_argument("--forzar", action="store_true", help="aunque la corrida del IFS no haya cambiado")
        parser.add_argument("--horas", type=int, default=lluvia_mapa.HORAS)
        parser.add_argument("--paso", type=float, default=lluvia_mapa.PASO, help="grados de la rejilla")

    def handle(self, destino, forzar, horas, paso, **opciones):
        destino = destino or getattr(settings, "CLIMA_SALIDA", "") or os.environ.get("CLIMA_SALIDA", "")
        if not destino:
            raise CommandError("Falta --destino o CLIMA_SALIDA")
        if not forzar and not lluvia_mapa.hay_corrida_nueva(destino):
            self.stdout.write("sin corrida nueva del IFS: no se baja nada")
            return
        ruta = lluvia_mapa.exportar(destino, horas=horas, paso=paso)
        self.stdout.write(f"escrito {ruta} ({ruta.stat().st_size / 1024:.0f} KB)")

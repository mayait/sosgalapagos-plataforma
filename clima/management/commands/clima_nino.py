# SOS Galápagos · © 2026 Universidad San Francisco de Quito (USFQ) · Autor: Julián Maya <jamaya@usfq.edu.ec>
# Licencia Apache 2.0 (ver LICENSE y NOTICE): puede reutilizarse dando crédito.
"""El Niño y la ZCIT a mano: baja las fuentes y escribe nino.json, nino_mapa.json y zcit.json.

  manage.py clima_nino                       los tres archivos en CLIMA_SALIDA
  manage.py clima_nino --salida /tmp/nino    en otra carpeta (para probar sin tocar el panel)
  manage.py clima_nino --solo zcit           solo la ZCIT (o --solo nino)
  manage.py clima_nino --twd texto.txt       la ZCIT desde un texto guardado de la discusión del NHC
  manage.py clima_nino --sin-ia              sin el resumen en español del modelo de lenguaje
"""
import json
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand

from clima import nino, zcit


class Command(BaseCommand):
    help = "El Niño (índices, mar, boyas, MJO) y la ZCIT del NHC para el panel de clima"

    def add_arguments(self, parser):
        parser.add_argument("--salida", default=None)
        parser.add_argument("--solo", choices=["nino", "zcit"], default=None)
        parser.add_argument("--twd", default=None, help="archivo con el texto de la discusión del NHC")
        parser.add_argument("--sin-ia", action="store_true")

    def handle(self, salida, solo, twd, sin_ia, **opciones):
        destino = salida or settings.CLIMA_SALIDA
        if not destino:
            self.stderr.write("Indica --salida o define CLIMA_SALIDA.")
            return
        if solo in (None, "nino"):
            self.stdout.write("nino  " + json.dumps(nino.exportar(destino), ensure_ascii=False))
        if solo in (None, "zcit"):
            texto = Path(twd).read_text() if twd else None
            self.stdout.write("zcit  " + json.dumps(zcit.exportar(destino, texto=texto, con_ia=not sin_ia), ensure_ascii=False))

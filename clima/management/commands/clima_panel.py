# SOS Galápagos · © 2026 Universidad San Francisco de Quito (USFQ) · Autor: Julián Maya <jamaya@usfq.edu.ec>
# Licencia Apache 2.0 (ver LICENSE y NOTICE): puede reutilizarse dando crédito.
"""Los datos del panel de /clima/ y las fuentes, a mano.

  manage.py clima_panel --publicar            escribe estado, horario, diario y pronóstico en la carpeta que lee el panel
  manage.py clima_panel --recoger             corre una vez todas las fuentes configuradas
  manage.py clima_panel --recoger ioc inamhi  corre solo esas
  manage.py clima_panel --descargas           rehace los ZIP de descarga
"""
from django.core.management.base import BaseCommand

from clima import fuentes, panel


class Command(BaseCommand):
    help = "Datos del panel de clima y recolección a mano"

    def add_arguments(self, parser):
        parser.add_argument("--publicar", action="store_true")
        parser.add_argument("--recoger", nargs="*")
        parser.add_argument("--descargas", action="store_true")

    def handle(self, publicar, recoger, descargas: bool, **opciones):
        if recoger is not None:
            for fuente, r in fuentes.recolectar(recoger or None).items():
                self.stdout.write(f"{fuente:14} {r}")
        if publicar:
            self.stdout.write(str(panel.publicar()))
        if descargas:
            from clima import descargas as modulo

            self.stdout.write(f"{modulo.publicar()} archivos ZIP")
        if recoger is None and not publicar and not descargas:
            self.stdout.write("Indica --publicar, --recoger o --descargas.")

# SOS Galápagos · © 2026 Universidad San Francisco de Quito (USFQ) · Autor: Julián Maya <jamaya@usfq.edu.ec>
# Licencia Apache 2.0 (ver LICENSE y NOTICE): puede reutilizarse dando crédito.
"""Cargas puntuales de datos históricos. Ninguna corre sola.

  manage.py clima_importar fcd puerto-ayora ruta/climate_puerto-ayora.csv   serie diaria de la Fundación Charles Darwin
  manage.py clima_importar ierse ruta/a/crudos                              histórico de IERSE en CSV (repositorio de datos)
  manage.py clima_importar gsc-historico                                    lluvia diaria del GSC desde 2015
  manage.py clima_importar inamhi ruta/historial.json                       historial por hora del INAMHI, guardado
  manage.py clima_importar tempest 2026-10-25                               Tempest desde esa fecha (UTC)
  manage.py clima_importar ambient 2026-10-01                               Ambient Weather desde esa fecha (UTC)
  manage.py clima_importar recalcular wunderground/casa_marina 2026-11-01   rehace la lluvia desde el acumulado guardado

Cada fuente conserva su licencia (LICENCIA-DATOS.md). Las series de la FCD son CC BY-NC-SA.
"""
import csv
import datetime as dt

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from clima.fuentes import acumulado, ambient, base, gsc, ierse, inamhi, tempest

# Coordenadas aproximadas de las dos estaciones históricas de la FCD.
FCD = {"puerto-ayora": ("Puerto Ayora (FCD)", -0.7438, -90.302, 6), "bellavista": ("Bellavista (FCD)", -0.6925, -90.3272, 194)}


def importar_fcd(codigo, ruta):
    """Lluvia diaria de la FCD. Se guarda como lluvia_dia_mm a las 00:00 de la hora continental, igual que el histórico del GSC."""
    nombre, lat, lon, altitud = FCD[codigo]
    base.estacion("fcd", codigo, nombre, "Santa Cruz", lat, lon, altitud, "Fundación Charles Darwin")
    filas = []
    with open(ruta, newline="") as f:
        for r in csv.DictReader(f):
            try:
                filas.append((codigo, "lluvia_dia_mm", dt.datetime.fromisoformat(r["observation_date"]).replace(tzinfo=base.CONTINENTE), float(r["precipitation"])))
            except (ValueError, KeyError, TypeError):
                continue
    return base.guardar("fcd", filas)


class Command(BaseCommand):
    help = "Cargas puntuales de datos históricos del clima"

    def add_arguments(self, parser):
        parser.add_argument("que", choices=["fcd", "ierse", "gsc-historico", "inamhi", "tempest", "ambient", "recalcular"])
        parser.add_argument("argumentos", nargs="*")

    def handle(self, que, argumentos, **opciones):
        fecha = lambda s: dt.datetime.fromisoformat(s).replace(tzinfo=base.UTC)  # noqa: E731
        try:
            with transaction.atomic():
                if que == "fcd":
                    if argumentos[0] not in FCD:
                        raise CommandError(f"Serie desconocida. Opciones: {', '.join(FCD)}")
                    n = importar_fcd(argumentos[0], argumentos[1])
                elif que == "ierse":
                    n = ierse.importar(argumentos[0])
                elif que == "gsc-historico":
                    n = gsc.importar_historico()
                elif que == "inamhi":
                    n = inamhi.historial(archivo=argumentos[0])
                elif que == "tempest":
                    n = tempest.recoger(desde=fecha(argumentos[0]))
                elif que == "ambient":
                    n = ambient.recoger(desde=fecha(argumentos[0]))
                else:
                    n = acumulado.recalcular(argumentos[0], fecha(argumentos[1]))
                base.resumir()
        except IndexError:
            raise CommandError("Faltan argumentos: mira la ayuda al inicio de clima/management/commands/clima_importar.py")
        self.stdout.write(f"{que}: {n} filas")

"""Carga el diccionario de zonas desde las capas del repo sosgalapagos-datos.

Uso: manage.py cargar_zonas [carpeta de capas]
Se puede correr las veces que haga falta: actualiza lo que ya existe y no borra nada.
"""
import json
from pathlib import Path

from django.conf import settings
from django.contrib.gis.geos import GEOSGeometry
from django.core.management.base import BaseCommand

from zonas.models import TipoZona, Zona

# Qué zona de /clima corresponde a cada isla cuando el barrio no dice más.
CLIMA_POR_ISLA = {"Santa Cruz": "la-cascada", "San Cristóbal": "san-cristobal", "Isabela": "isabela"}
# Parte alta de Santa Cruz: usa su propia zona de clima.
PARTE_ALTA = {"Bellavista", "Santa Rosa", "El Cascajo", "Cascajo", "El Camote", "Occidente"}

CAPAS = [("barrios.geojson", TipoZona.BARRIO, "nombre"), ("limite_urbano.geojson", TipoZona.SECTOR, "nombre")]


class Command(BaseCommand):
    help = "Carga barrios y sectores desde las capas de geodatos"

    def add_arguments(self, parser):
        parser.add_argument("carpeta", nargs="?", default=str(settings.CAPAS_DIR))

    def handle(self, carpeta, **opciones):
        total = 0
        for archivo, tipo, campo in CAPAS:
            ruta = Path(carpeta) / archivo
            if not ruta.exists():
                self.stderr.write(f"No encuentro {ruta}")
                continue
            for f in json.loads(ruta.read_text())["features"]:
                p = f["properties"]
                nombre, isla = (p.get(campo) or "").strip(), (p.get("isla") or "").strip()
                if not nombre or not isla:
                    continue
                clima = "santa-cruz-alta" if nombre in PARTE_ALTA else CLIMA_POR_ISLA.get(isla, "")
                Zona.objects.update_or_create(
                    nombre=nombre,
                    tipo=tipo,
                    isla=isla,
                    defaults={
                        "geometria": GEOSGeometry(json.dumps(f["geometry"]), srid=4326),
                        "fuente": p.get("fuente", ""),
                        "zona_clima": clima,
                    },
                )
                total += 1
        self.stdout.write(f"Zonas cargadas o actualizadas: {total}")

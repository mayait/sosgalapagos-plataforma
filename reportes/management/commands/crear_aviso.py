# SOS Galápagos · © 2026 Universidad San Francisco de Quito (USFQ) · Autor: Julián Maya <jamaya@usfq.edu.ec>
# Licencia Apache 2.0 (ver LICENSE y NOTICE): puede reutilizarse dando crédito.
"""Crea un aviso de coordinación desde la consola: entra confirmado y con su contenido visible.

Sirve para lo que no llega por el formulario: un centro de acopio con nombre propio,
varias fotos y un plazo largo.

Uso:
  manage.py crear_aviso --tipo donar_colaborar --lat -0.89553 --lon -89.60884 \\
      --titulo "Centro de acopio USFQ San Cristóbal" --nota "Se reciben…" \\
      --dias 14 --foto /ruta/1.jpg --foto /ruta/2.jpg

Si ya hay un aviso vivo del mismo tipo a menos de 50 m, no crea otro: lo dice y sale.
Las fotos se guardan sin metadatos, como todas.
"""
from datetime import timedelta

from django.contrib.gis.geos import Point
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from reportes import fotos, reglas
from reportes.models import FotoReporte, Fuente, TipoRiesgo
from zonas.models import zona_de


class Command(BaseCommand):
    help = "Crea un aviso de coordinación (confirmado y visible)"

    def add_arguments(self, parser):
        parser.add_argument("--tipo", required=True, help="Código del tipo de aviso")
        parser.add_argument("--lat", type=float, required=True)
        parser.add_argument("--lon", type=float, required=True)
        parser.add_argument("--titulo", default="")
        parser.add_argument("--nota", default="")
        parser.add_argument("--dias", type=float, default=0, help="Días de vida. Sin esto, el plazo del tipo")
        parser.add_argument("--foto", action="append", default=[], help="Ruta de una foto. Se puede repetir")

    def handle(self, tipo, lat, lon, titulo, nota, dias, foto, **opciones):
        try:
            tipo = TipoRiesgo.objects.get(codigo=tipo)
        except TipoRiesgo.DoesNotExist:
            raise CommandError(f"No existe el tipo «{tipo}». Tipos: {', '.join(TipoRiesgo.objects.values_list('codigo', flat=True))}")
        if len(titulo) > 80 or len(nota) > 280:
            raise CommandError("El título admite 80 caracteres y la nota, 280.")
        punto = Point(lon, lat, srid=4326)
        if reglas.buscar_duplicado(tipo, punto):
            raise CommandError("Ya hay un aviso vivo de ese tipo en ese lugar. No se creó otro.")
        limpias = []
        for ruta in foto:
            with open(ruta, "rb") as archivo:
                limpias.append(fotos.procesar(archivo)[0])
        ahora = timezone.now()
        reporte = reglas.crear_reporte(
            tipo=tipo, punto=punto, huella="coordinacion", fuente=Fuente.COORDINADOR, titulo=titulo, nota=nota,
            vence_en=ahora + timedelta(days=dias) if dias else None, zona=zona_de(punto),
            foto=limpias[0] if limpias else None,
        ).reporte
        for orden, extra in enumerate(limpias[1:], start=1):
            FotoReporte.objects.create(reporte=reporte, foto=extra, orden=orden)
        self.stdout.write(f"Creado {reporte.id_publico}: {reporte.nombre} · vence {reporte.vence_en:%Y-%m-%d %H:%M} UTC · {len(limpias)} fotos")

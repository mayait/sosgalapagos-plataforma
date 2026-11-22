"""Encola cada minuto las tareas periódicas. Las ejecuta el trabajador (manage.py db_worker).

El marco de tareas de Django no trae un planificador, así que este proceso hace
solo eso: poner en la cola. Si se cae, el mapa sigue retirando lo vencido.
"""
import time

from django.conf import settings
from django.core.management.base import BaseCommand

from clima.tareas import guardar_pronostico, recalibrar_pronostico, sincronizar_clima
from entradas.tareas import purgar
from reportes.tareas import cerrar_vencidos


class Command(BaseCommand):
    help = "Encola las tareas periódicas cada minuto"

    def handle(self, **opciones):
        vuelta = 0
        while True:
            cerrar_vencidos.enqueue()
            if settings.CLIMA_SQLITE and vuelta % 5 == 2:  # cada cinco minutos, tras la corrida del recolector
                sincronizar_clima.enqueue()
            if settings.CLIMA_PRONOSTICO_DIR and vuelta % 60 == 9:  # cada hora
                guardar_pronostico.enqueue()
            if settings.CLIMA_PRONOSTICO_DIR and vuelta % 1440 == 30:  # una vez al día: aprende de lo que llovió ayer
                recalibrar_pronostico.enqueue()
            if vuelta % 360 == 0:  # cada seis horas: borra el texto viejo de WhatsApp
                purgar.enqueue()
            vuelta += 1
            time.sleep(60)

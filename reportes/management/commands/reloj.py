# SOS Galápagos · © 2026 Universidad San Francisco de Quito (USFQ) · Autor: Julián Maya <jamaya@usfq.edu.ec>
# Todos los derechos reservados. Usar, copiar, modificar o derivar de este código requiere permiso escrito del autor (ver LICENSE).
"""Encola cada minuto las tareas periódicas. Las ejecuta el trabajador (manage.py db_worker).

El marco de tareas de Django no trae un planificador, así que este proceso hace
solo eso: poner en la cola. Si se cae, el mapa sigue retirando lo vencido.
"""
import time

from django.conf import settings
from django.core.management.base import BaseCommand

from clima.tareas import actualizar_lluvia_mapa, actualizar_mar, actualizar_nino, actualizar_oficiales, ciclo_clima, guardar_pronostico, publicar_descargas, recalibrar_pronostico, revisar_alertas
from entradas.tareas import purgar
from reportes.tareas import cerrar_vencidos


class Command(BaseCommand):
    help = "Encola las tareas periódicas cada minuto"

    def handle(self, **opciones):
        vuelta = 0
        while True:
            cerrar_vencidos.enqueue()
            if settings.CLIMA_RECOGER and vuelta % 5 == 0:  # cada cinco minutos: fuentes, nivel y panel
                ciclo_clima.enqueue()
            if settings.CLIMA_RECOGER and vuelta % 60 == 9:  # cada hora
                guardar_pronostico.enqueue()
            if settings.CLIMA_RECOGER and vuelta % 1440 == 30:  # una vez al día: aprende de lo que llovió ayer
                recalibrar_pronostico.enqueue()
            if vuelta % 5 == 4:       # cada cinco minutos: ¿algo merece aviso?
                revisar_alertas.enqueue()
            if settings.CLIMA_RECOGER and settings.CLIMA_SALIDA and vuelta % 60 == 17:
                publicar_descargas.enqueue()
            if vuelta % 60 == 13:     # cada hora: pronóstico del INAMHI y boletines nuevos
                actualizar_oficiales.enqueue()
            if vuelta % 720 == 20:    # dos veces al día: mareas y oleaje (Stormglass da 10 llamadas diarias por llave)
                actualizar_mar.enqueue()
            if settings.CLIMA_RECOGER and settings.CLIMA_SALIDA and vuelta % 60 == 41:  # cada hora: mapa de lluvia, si hay corrida nueva
                actualizar_lluvia_mapa.enqueue()
            if settings.CLIMA_SALIDA and vuelta % 360 == 45:  # cada seis horas: El Niño y la ZCIT (las fuentes cambian una a cuatro veces al día)
                actualizar_nino.enqueue()
            if vuelta % 360 == 0:  # cada seis horas: borra el texto viejo de WhatsApp
                purgar.enqueue()
            vuelta += 1
            time.sleep(60)

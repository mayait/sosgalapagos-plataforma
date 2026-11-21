"""Tareas en segundo plano. Las encola el reloj (manage.py reloj) cada minuto."""
from django.tasks import task

from . import reglas


@task
def cerrar_vencidos():
    return reglas.cerrar_vencidos()

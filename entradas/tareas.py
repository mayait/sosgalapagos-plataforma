"""Tareas en segundo plano de WhatsApp."""
from django.tasks import task


@task
def procesar_mensaje(mensaje_id):
    from . import flujo

    return flujo.procesar(mensaje_id)


@task
def purgar():
    from . import flujo

    return list(flujo.purgar())

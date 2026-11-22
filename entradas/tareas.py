# SOS Galápagos · © 2026 Universidad San Francisco de Quito (USFQ) · Autor: Julián Maya <jamaya@usfq.edu.ec>
# Todos los derechos reservados. Usar, copiar, modificar o derivar de este código requiere permiso escrito del autor (ver LICENSE).
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

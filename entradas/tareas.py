# SOS Galápagos · © 2026 Universidad San Francisco de Quito (USFQ) · Autor: Julián Maya <jamaya@usfq.edu.ec>
# Licencia Apache 2.0 (ver LICENSE y NOTICE): puede reutilizarse dando crédito.
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

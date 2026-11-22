"""Tareas periódicas del clima. Las encola el reloj."""
from django.tasks import task


@task
def sincronizar_clima():
    from .sincronizar import sincronizar

    s = sincronizar()
    return {"leidas": s.leidas, "cambiadas": s.cambiadas, "borradas": s.borradas, "segundos": s.segundos, "error": s.error}


@task
def guardar_pronostico():
    from . import pronostico

    leidos, nuevas = pronostico.guardar_archivo()
    return {"archivos": leidos, "modelos": nuevas, "publicados": pronostico.guardar_emitido()}


@task
def recalibrar_pronostico():
    from . import pronostico

    return [{k: str(v) for k, v in r.items()} for r in pronostico.recalibrar()]


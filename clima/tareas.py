"""Tareas periódicas del clima. Las encola el reloj."""
from django.tasks import task


@task
def sincronizar_clima():
    from .sincronizar import sincronizar

    s = sincronizar()
    return {"leidas": s.leidas, "cambiadas": s.cambiadas, "borradas": s.borradas, "segundos": s.segundos, "error": s.error}

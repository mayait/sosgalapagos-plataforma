# SOS Galápagos · © 2026 Universidad San Francisco de Quito (USFQ) · Autor: Julián Maya <jamaya@usfq.edu.ec>
# Todos los derechos reservados. Usar, copiar, modificar o derivar de este código requiere permiso escrito del autor (ver LICENSE).
"""Tareas en segundo plano. Las encola el reloj (manage.py reloj) cada minuto."""
from django.tasks import task

from . import reglas


@task
def cerrar_vencidos():
    return reglas.cerrar_vencidos()


@task
def avisar_reporte(reporte_id):
    """Manda el aviso del navegador de un peligro confirmado."""
    from . import avisos
    from .models import Reporte

    reporte = Reporte.objects.filter(pk=reporte_id).select_related("tipo", "zona").first()
    return avisos.de_reporte(reporte) if reporte else 0


@task
def avisar_bienvenida(suscripcion_id):
    from . import avisos
    from .models import SuscripcionPush

    s = SuscripcionPush.objects.filter(pk=suscripcion_id).first()
    return avisos.bienvenida(s) if s else 0


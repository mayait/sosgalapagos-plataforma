"""Avisos del navegador (Web Push). Llegan a quien instaló la app o aceptó los avisos.

Un aviso solo lleva lo que ya es público en el mapa: el tipo, la zona y el enlace.
"""
import json
import logging

from django.conf import settings
from django.utils import timezone

from .models import SuscripcionPush

registro = logging.getLogger(__name__)


def activos():
    return bool(settings.PUSH_PUBLICA and settings.PUSH_PRIVADA)


def enviar(titulo, cuerpo, enlace, etiqueta=""):
    """Manda un aviso a todas las suscripciones. Devuelve cuántas lo recibieron.

    Las suscripciones que el navegador ya dio de baja (404 o 410) se retiran.
    """
    if not activos():
        return 0
    from pywebpush import WebPushException, webpush

    carga = json.dumps({"titulo": titulo, "cuerpo": cuerpo, "enlace": enlace, "etiqueta": etiqueta})
    entregados = 0
    for s in SuscripcionPush.objects.all():
        try:
            webpush(
                subscription_info={"endpoint": s.direccion, "keys": {"p256dh": s.p256dh, "auth": s.auth}},
                data=carga,
                vapid_private_key=settings.PUSH_PRIVADA,
                vapid_claims={"sub": settings.PUSH_CONTACTO},
                ttl=6 * 3600,
                timeout=10,
            )
            entregados += 1
            SuscripcionPush.objects.filter(pk=s.pk).update(ultimo_envio=timezone.now())
        except WebPushException as error:
            codigo = getattr(error.response, "status_code", None)
            if codigo in (404, 410):
                s.delete()  # el navegador ya no existe o retiró el permiso
            else:
                registro.warning("Aviso no entregado (%s)", codigo)
        except Exception:
            registro.exception("Aviso no entregado")
    return entregados


def de_reporte(reporte):
    """Aviso de un peligro confirmado."""
    zona = f" en {reporte.zona.nombre}" if reporte.zona else ""
    grave = {"no_pasar": "No pasar. ", "peligro_vida": "Peligro de vida. "}.get(reporte.gravedad, "")
    return enviar(
        titulo=f"{reporte.nombre}{zona}",
        cuerpo=f"{grave}Reporte confirmado. Información preliminar, no oficial. Emergencias: 911.",
        enlace=f"/riesgos/?r={reporte.id_publico}",
        etiqueta=reporte.id_publico,
    )

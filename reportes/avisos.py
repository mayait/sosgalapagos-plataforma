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


def _entregar(s, carga):
    """Manda una carga a una suscripción. True si llegó; retira la suscripción si el navegador ya no existe."""
    from pywebpush import WebPushException, webpush

    try:
        webpush(
            subscription_info={"endpoint": s.direccion, "keys": {"p256dh": s.p256dh, "auth": s.auth}},
            data=carga,
            vapid_private_key=settings.PUSH_PRIVADA,
            vapid_claims={"sub": settings.PUSH_CONTACTO},
            ttl=6 * 3600,
            timeout=10,
        )
        SuscripcionPush.objects.filter(pk=s.pk).update(ultimo_envio=timezone.now())
        return True
    except WebPushException as error:
        codigo = getattr(error.response, "status_code", None)
        if codigo in (404, 410):
            s.delete()  # el navegador ya no existe o retiró el permiso
        else:
            registro.warning("Aviso no entregado (%s)", codigo)
    except Exception:
        registro.exception("Aviso no entregado")
    return False


def enviar(titulo, cuerpo, enlace, etiqueta="", a=None):
    """Manda un aviso a todas las suscripciones (o solo a las de `a`). Devuelve cuántas lo recibieron."""
    if not activos():
        return 0
    carga = json.dumps({"titulo": titulo, "cuerpo": cuerpo, "enlace": enlace, "etiqueta": etiqueta})
    return sum(_entregar(s, carga) for s in (a if a is not None else SuscripcionPush.objects.all()))


def bienvenida(suscripcion):
    """Aviso de prueba al suscribirse: así la persona sabe que le llegan."""
    return enviar(
        "Avisos encendidos",
        "Así te llegarán los avisos de SOS Galápagos. Información preliminar, no oficial. Emergencias: 911.",
        "/riesgos/",
        "bienvenida",
        a=[suscripcion],
    )


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

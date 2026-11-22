# SOS Galápagos · © 2026 Universidad San Francisco de Quito (USFQ) · Autor: Julián Maya <jamaya@usfq.edu.ec>
# Todos los derechos reservados. Usar, copiar, modificar o derivar de este código requiere permiso escrito del autor (ver LICENSE).
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
    """Aviso de un peligro confirmado, a quienes pidieron el tema «peligros» de esa isla."""
    from clima import alertas

    isla = {"Santa Cruz": "santa-cruz", "San Cristóbal": "san-cristobal", "Isabela": "isabela"}.get(reporte.zona.isla if reporte.zona else "", "")
    zona = f" en {reporte.zona.nombre}" if reporte.zona else ""
    grave = {"no_pasar": "No pasar. ", "peligro_vida": "Peligro de vida. "}.get(reporte.gravedad, "")
    # Solo un peligro de vida confirmado puede sonar de noche, y solo a quien lo pidió.
    aviso = alertas.emitir("peligros", isla, f"reporte:{reporte.id_publico}", f"{reporte.nombre}{zona}",
                           f"{grave}Reporte confirmado. Información preliminar, no oficial. Emergencias: 911.", f"/riesgos/?r={reporte.id_publico}",
                           urgente=reporte.gravedad == "peligro_vida")
    return aviso.entregados if aviso else 0

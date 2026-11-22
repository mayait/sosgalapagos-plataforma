# SOS Galápagos · © 2026 Universidad San Francisco de Quito (USFQ) · Autor: Julián Maya <jamaya@usfq.edu.ec>
# Todos los derechos reservados. Usar, copiar, modificar o derivar de este código requiere permiso escrito del autor (ver LICENSE).
"""El relevo de IERSE: la puerta por donde entra lo que una máquina en Ecuador pide por nosotros.

IERSE solo responde a conexiones desde Ecuador. La máquina de relevo (despliegue/relevo/relevo.py)
no sabe nada de IERSE: pregunta aquí qué pedir, lo pide y devuelve las respuestas tal cual. Así
toda la lógica vive en esta aplicación y el relevo se puede mover de máquina sin tocar código.

Seguridad: el relevo se identifica con CLIMA_RELEVO_LLAVE. Si esa llave se filtrara, lo único
que alguien podría hacer es entregar mediciones falsas de IERSE; por eso lo que llega se valida
entero (clima/fuentes/ierse.py) y se limita su tamaño.
"""
import hmac
import json
import time

from django.conf import settings
from django.db import transaction

from . import fuentes
from .fuentes import base, ierse

TAMANO_MAXIMO = 8 * 1024 * 1024


def autorizado(request):
    llave = settings.CLIMA_RELEVO_LLAVE
    return bool(llave) and hmac.compare_digest(request.headers.get("X-Llave", ""), llave)


def pedidos():
    lista, _ = ierse.pedidos()
    return {"pedidos": lista, "agente": base.AGENTE}


def recibir(cuerpo):
    """cuerpo: JSON {respuestas: {id: contenido}, errores: [texto]}. Devuelve {guardadas, pendiente}."""
    t0 = time.monotonic()
    if len(cuerpo) > TAMANO_MAXIMO:
        return {"error": "demasiado grande"}
    try:
        datos = json.loads(cuerpo)
        respuestas = datos["respuestas"]
        assert isinstance(respuestas, dict)
    except (ValueError, KeyError, TypeError, AssertionError):
        return {"error": "formato inesperado"}
    errores = [str(e)[:120] for e in (datos.get("errores") or [])[:5]]
    if not respuestas:  # el relevo no pudo hablar con IERSE: queda anotado como fallo de la fuente
        fuentes.anotar("ierse", t0, error="; ".join(errores) or "el relevo no obtuvo respuestas")
        return {"guardadas": 0, "pendiente": False}
    with transaction.atomic():
        guardadas = ierse.procesar(respuestas)
        base.resumir(ierse.desde_del_resumen(respuestas))
    fuentes.anotar("ierse", t0, guardadas)
    _, pendiente = ierse.pedidos()
    return {"guardadas": guardadas, "pendiente": pendiente}

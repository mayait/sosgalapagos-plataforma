# SOS Galápagos · © 2026 Universidad San Francisco de Quito (USFQ) · Autor: Julián Maya <jamaya@usfq.edu.ec>
# Todos los derechos reservados. Usar, copiar, modificar o derivar de este código requiere permiso escrito del autor (ver LICENSE).
"""Lo que pasó y no tiene un punto en el mapa, para la línea del tiempo.

Reúne tres cosas en una sola lista:
- los avisos que se mandaron a los teléfonos (o que se retuvieron por ser de noche);
- los boletines y advertencias oficiales que la app `clima` lee del INAMHI y del INOCAR;
- los sucesos que coordinación escribe a mano: comunicados, noticias, informes, notas.

Un suceso puede ser de una zona o de todo Galápagos. Nada aquí lleva datos personales.
"""
from datetime import timedelta

from django.utils import timezone

from .models import Suceso

# Isla de los avisos → zonas de la línea del tiempo que le corresponden.
ZONAS_DE_ISLA = {"santa-cruz": ["sc", "sc-alta"], "san-cristobal": ["sx", "sx-alta"], "isabela": ["is"]}
TEMA = {"lluvia": "Aviso de lluvia", "pronostico": "Aviso del pronóstico", "mar": "Aviso de oleaje", "oficiales": "Aviso de un boletín oficial",
        "peligros": "Aviso de un peligro confirmado", "resumen": "Resumen de la noche"}
BOLETIN = {"advertencia": "Advertencia del INAMHI", "oleaje": "Boletín de oleaje del INOCAR", "erfen": "Boletín ERFEN (El Niño)"}


def _zonas(zona):
    """De una zona guardada a la lista de zonas de la línea del tiempo. Lista vacía: todo Galápagos."""
    if not zona:
        return []
    return ZONAS_DE_ISLA.get(zona, [zona])


def sucesos(desde=None, hasta=None):
    """Lista de sucesos entre dos instantes, del más reciente al más antiguo."""
    from clima.models import AvisoEnviado, Boletin

    hasta = hasta or timezone.now()
    desde = desde or hasta - timedelta(days=62)
    lista = []
    for a in AvisoEnviado.objects.filter(creado__gte=desde, creado__lte=hasta).exclude(titulo__startswith="("):
        if a.tema == "oficiales" or a.clave.startswith("boletin:"):
            continue  # el boletín ya sale por su cuenta, con su enlace
        lista.append({
            "t": a.creado, "clase": "aviso", "titulo": a.titulo, "texto": a.cuerpo, "fuente": TEMA.get(a.tema, "Aviso"),
            "detalle": "no se envió: era de noche" if a.retenido and not a.entregados else (f"enviado a {a.entregados} teléfono{'s' if a.entregados != 1 else ''}" if a.entregados else "sin teléfonos suscritos a este tema"),
            "retenido": bool(a.retenido and not a.entregados), "enlace": a.enlace, "zonas": _zonas(a.zona),
        })
    for b in Boletin.objects.filter(visto_en__gte=desde, visto_en__lte=hasta, afecta_galapagos=True):
        cuando = b.emitido or b.visto_en
        lista.append({
            "t": cuando, "clase": "oficial", "titulo": f"{BOLETIN.get(b.tipo, 'Boletín oficial')}{' n.º ' + b.numero if b.numero else ''}",
            "texto": b.resumen, "fuente": b.fuente.upper(),
            "detalle": ("vigente hasta el " + timezone.localtime(b.vigente_hasta, timezone.get_fixed_timezone(-360)).strftime("%d-%m %H:%M") if b.vigente_hasta else "")
                       + ("" if b.revisado else " · resumen automático: lee el documento oficial"),
            "retenido": False, "enlace": b.enlace, "zonas": [],
        })
    for s in Suceso.objects.filter(visible=True, ocurrido__gte=desde, ocurrido__lte=hasta):
        lista.append({
            "t": s.ocurrido, "clase": s.clase, "titulo": s.titulo, "texto": s.texto, "fuente": s.fuente,
            "detalle": ("vigente hasta el " + timezone.localtime(s.hasta, timezone.get_fixed_timezone(-360)).strftime("%d-%m %H:%M")) if s.hasta else "",
            "retenido": False, "enlace": s.enlace, "zonas": _zonas(s.zona),
        })
    return sorted(lista, key=lambda x: x["t"], reverse=True)

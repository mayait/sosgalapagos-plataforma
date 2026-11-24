# SOS Galápagos · © 2026 Universidad San Francisco de Quito (USFQ) · Autor: Julián Maya <jamaya@usfq.edu.ec>
# Licencia Apache 2.0 (ver LICENSE y NOTICE): puede reutilizarse dando crédito.
"""Lo que pasó y no tiene un punto en el mapa, para la línea del tiempo.

Reúne tres cosas en una sola lista:
- los avisos que se mandaron a los teléfonos (o que se retuvieron por ser de noche);
- los boletines y advertencias oficiales que la app `clima` lee del INAMHI y del INOCAR, y los
  informes de situación (SITREP) de la Secretaría Nacional de Gestión de Riesgos;
- los sucesos que coordinación escribe a mano: comunicados, noticias, informes, notas.

Un suceso puede ser de una zona o de todo Galápagos. Nada aquí lleva datos personales.
"""
from datetime import timedelta

from django.db.models import Q
from django.utils import timezone

from .models import Suceso

# Isla de los avisos → zonas de la línea del tiempo que le corresponden.
ZONAS_DE_ISLA = {"santa-cruz": ["sc", "sc-alta"], "san-cristobal": ["sx", "sx-alta"], "isabela": ["is"]}
TEMA = {"lluvia": "Aviso de lluvia", "pronostico": "Aviso del pronóstico", "mar": "Aviso de oleaje", "oficiales": "Aviso de un boletín oficial",
        "peligros": "Aviso de un peligro confirmado", "resumen": "Resumen de la noche"}
BOLETIN = {"advertencia": "Advertencia del INAMHI", "oleaje": "Boletín de oleaje del INOCAR", "erfen": "Boletín ERFEN (El Niño)", "sitrep": "SITREP nacional de la SNGR"}
SIGLA = {"inamhi": "INAMHI", "inocar": "INOCAR", "sngr": "SNGR"}
GALAPAGOS = timezone.get_fixed_timezone(-360)


def _zonas(zona):
    """De una zona guardada a la lista de zonas de la línea del tiempo. Lista vacía: todo Galápagos."""
    if not zona:
        return []
    return ZONAS_DE_ISLA.get(zona, [zona])


def _titulo_boletin(b):
    return f"{BOLETIN.get(b.tipo, 'Boletín oficial')}{' n.º ' + b.numero if b.numero else ''}"


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
    # Los SITREP salen siempre: son el informe nacional de la emergencia, nombre o no a Galápagos ese día.
    for b in Boletin.objects.filter(Q(afecta_galapagos=True) | Q(tipo="sitrep"), visto_en__gte=desde, visto_en__lte=hasta):
        cuando = b.emitido or b.visto_en
        lista.append({
            "t": cuando, "clase": "oficial", "titulo": _titulo_boletin(b),
            "texto": b.resumen, "fuente": SIGLA.get(b.fuente, b.fuente.upper()), "institucion": b.fuente,
            "detalle": " · ".join(x for x in (("vigente hasta el " + timezone.localtime(b.vigente_hasta, GALAPAGOS).strftime("%d-%m %H:%M")) if b.vigente_hasta else "",
                                              "" if b.revisado or not b.resumen else "resumen automático: el documento oficial es el que vale") if x),
            "retenido": False, "enlace": b.enlace, "zonas": [],
        })
    for s in Suceso.objects.filter(visible=True, ocurrido__gte=desde, ocurrido__lte=hasta):
        lista.append({
            "t": s.ocurrido, "clase": s.clase, "titulo": s.titulo, "texto": s.texto, "fuente": s.fuente or s.get_institucion_display(), "institucion": s.institucion,
            "detalle": ("vigente hasta el " + timezone.localtime(s.hasta, GALAPAGOS).strftime("%d-%m %H:%M")) if s.hasta else "",
            "retenido": False, "enlace": s.destino, "zonas": _zonas(s.zona),
        })
    return sorted(lista, key=lambda x: x["t"], reverse=True)


# Qué se muestra en «Documentos oficiales» de la portada, y en qué orden: lo último de cada uno.
# (institución, tipo de boletín que se lee solo o None si lo sube coordinación, nombre corto, qué es)
EN_PORTADA = [
    ("inamhi", "advertencia", "INAMHI", "Advertencia meteorológica"),
    ("sngr", "sitrep", "SNGR", "Informe de situación (SITREP)"),
    ("inocar", "oleaje", "INOCAR", "Boletín de oleaje"),
    ("inocar", "erfen", "INOCAR · ERFEN", "Boletín de El Niño"),
    ("gad-santa-cruz", None, "GAD de Santa Cruz", "Informe o comunicado"),
    ("gad-san-cristobal", None, "GAD de San Cristóbal", "Informe o comunicado"),
    ("gad-isabela", None, "GAD de Isabela", "Informe o comunicado"),
    ("coe", None, "COE", "Resolución o comunicado"),
    ("cgreg", None, "Consejo de Gobierno", "Informe o comunicado"),
]


def ultimos_oficiales(ahora=None):
    """El último documento oficial de cada institución, para la portada. Solo salen las que tienen alguno."""
    from clima.models import Boletin

    ahora = ahora or timezone.now()
    lista = []
    for institucion, tipo, nombre, que_es in EN_PORTADA:
        if tipo:
            b = Boletin.objects.filter(fuente=institucion, tipo=tipo).order_by("-visto_en").first()
            if not b:
                continue
            lista.append({
                "institucion": institucion, "nombre": nombre, "que_es": que_es, "titulo": _titulo_boletin(b), "resumen": b.resumen,
                "fecha": b.emitido or b.visto_en, "enlace": b.enlace, "nombra_galapagos": b.afecta_galapagos, "nivel": b.nivel,
                "vigente": bool(b.vigente_hasta and b.vigente_hasta >= ahora), "vigente_hasta": b.vigente_hasta,
                "infografia": (b.datos or {}).get("infografia", ""), "resumen_automatico": bool(b.extraido_con and not b.revisado),
            })
        else:
            s = Suceso.objects.filter(visible=True, clase="oficial", institucion=institucion).order_by("-ocurrido").first()
            if not s:
                continue
            lista.append({
                "institucion": institucion, "nombre": nombre, "que_es": que_es, "titulo": s.titulo, "resumen": s.texto,
                "fecha": s.ocurrido, "enlace": s.destino, "nombra_galapagos": True, "nivel": "",
                "vigente": bool(s.hasta and s.hasta >= ahora), "vigente_hasta": s.hasta, "infografia": "", "resumen_automatico": False,
            })
    return {"generado": ahora, "todos": "/riesgos/informe/?ver=oficial", "documentos": lista}


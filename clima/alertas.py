"""Alertas por tema: cada persona elige de qué quiere enterarse y de qué islas.

Temas:
  peligros    un peligro confirmado en el mapa
  lluvia      el nivel de lluvia peligrosa de la isla sube a «alto» o «muy alto» (lo medido)
  pronostico  mañana se espera lluvia fuerte (señal alta del pronóstico)
  mar         oleaje fuerte o pleamar muy alta
  oficiales   una advertencia o un boletín oficial nuevo que nombra a Galápagos

Cada aviso lleva una clave: el mismo no sale dos veces. Todo es información preliminar, no
oficial, salvo los boletines, que enlazan al documento de la institución.
"""
from datetime import datetime, timedelta, timezone

from .consultas import GALAPAGOS
from .models import AvisoEnviado

TEMAS = {
    "peligros": "Peligros confirmados en el mapa",
    "lluvia": "Lluvia peligrosa ahora en mi isla",
    "pronostico": "Lluvia fuerte esperada para mañana",
    "mar": "Oleaje fuerte y pleamares muy altas",
    "oficiales": "Advertencias y boletines oficiales (INAMHI, INOCAR)",
}
ZONAS = {"santa-cruz": "Santa Cruz", "san-cristobal": "San Cristóbal", "isabela": "Isabela"}
ZONA_DE_CLIMA = {"la-cascada": "santa-cruz", "santa-cruz-alta": "santa-cruz", "san-cristobal": "san-cristobal", "isabela": "isabela"}
POR_DEFECTO = ["peligros", "lluvia", "oficiales"]
OLA_FUERTE_M = 2.5  # umbral preliminar para avisar de oleaje


def destinatarios(tema, zona=""):
    """Suscripciones que pidieron ese tema y esa isla (o no eligieron islas: todas)."""
    from reportes.models import SuscripcionPush

    return [s for s in SuscripcionPush.objects.all()
            if tema in (s.temas or POR_DEFECTO) and (not zona or not s.zonas or zona in s.zonas)]


def emitir(tema, zona, clave, titulo, cuerpo, enlace="/riesgos/"):
    """Manda un aviso una sola vez. Devuelve el AvisoEnviado, o None si esa clave ya había salido."""
    from reportes import avisos

    aviso, nuevo = AvisoEnviado.objects.get_or_create(clave=clave[:120], defaults={"tema": tema, "zona": zona, "titulo": titulo[:120], "cuerpo": cuerpo[:300], "enlace": enlace[:200]})
    if not nuevo:
        return None
    aviso.entregados = avisos.enviar(titulo[:120], cuerpo[:300], enlace, etiqueta=clave[:60], a=destinatarios(tema, zona))
    aviso.save(update_fields=["entregados"])
    return aviso


def revisar(ahora=None):
    """Mira si algo merece aviso: lluvia medida, pronóstico de mañana, mar y boletines. Devuelve los emitidos."""
    ahora = ahora or datetime.now(timezone.utc)
    return [a for a in (_lluvia(ahora) + _pronostico(ahora) + _mar(ahora) + _oficiales(ahora)) if a]


def _lluvia(ahora):
    from reportes import clima as panel

    inundacion = (panel.estado() or {}).get("inundacion") or {}
    local = ahora.astimezone(GALAPAGOS)
    bloque = f"{local:%Y-%m-%d}-{local.hour // 8}"  # como mucho uno cada 8 horas por isla y nivel
    # Una isla puede tener varias zonas en alerta: sale un solo aviso, con la de nivel más alto.
    peor = {}
    for z in inundacion.get("zonas") or []:
        nivel, isla = (z.get("nivel") or "").lower(), ZONA_DE_CLIMA.get(z.get("id"))
        if nivel in ("alto", "muy alto") and isla and (isla not in peor or (nivel == "muy alto" and peor[isla][0] != "muy alto")):
            peor[isla] = (nivel, z)
    salida = []
    for isla, (nivel, z) in peor.items():
        lluvia = (z.get("R") or {}).get("R24h")
        salida.append(emitir("lluvia", isla, f"lluvia:{isla}:{nivel}:{bloque}", f"Lluvia peligrosa en {ZONAS[isla]}: nivel {nivel}",
                             f"{z.get('zona', '')}. " + (f"Han caído {round(lluvia)} mm en 24 horas. " if lluvia else "") + "Aléjate de quebradas y zonas bajas. Estimación preliminar, no oficial. Emergencias: 911.",
                             f"/clima/?zona={z['id']}"))
    return salida


def _pronostico(ahora):
    from .models import PronosticoEmitido
    from .pronostico import PUNTOS

    local = ahora.astimezone(GALAPAGOS)
    if not 16 <= local.hour <= 20:  # se avisa por la tarde, para el día siguiente
        return []
    manana = local.date() + timedelta(days=1)
    salida, zonas = [], {}
    for punto in PUNTOS:
        f = PronosticoEmitido.objects.filter(punto=punto["id"], fecha=manana).order_by("-emitido").first()
        if f and f.nivel == "alta" and f.prob20:
            zona = ZONA_DE_CLIMA[punto["zona"]]
            zonas[zona] = max(zonas.get(zona, 0), f.prob20)
    for zona, prob in zonas.items():
        salida.append(emitir("pronostico", zona, f"pronostico:{zona}:{manana}", f"Mañana puede llover fuerte en {ZONAS[zona]}",
                             f"El pronóstico da {round(prob * 100)} % de probabilidad de 20 mm o más en la parte alta. Es experimental y puede fallar; el oficial es del INAMHI.",
                             "/clima/"))
    return salida


def _mar(ahora):
    from .mar import PUERTOS
    from .models import MarHora

    salida = []
    for puerto, p in PUERTOS.items():
        pico = MarHora.objects.filter(puerto=puerto, hora__gte=ahora, hora__lte=ahora + timedelta(hours=36), ola_m__gte=OLA_FUERTE_M).order_by("-ola_m").first()
        if pico:
            cuando = pico.hora.astimezone(GALAPAGOS)
            salida.append(emitir("mar", p["zona"], f"mar:{puerto}:{cuando:%Y-%m-%d}", f"Oleaje fuerte en {p['nombre']}",
                                 f"Se esperan olas de hasta {pico.ola_m:.1f} m hacia las {cuando:%H} h del {cuando:%d-%m}. Pronóstico de un modelo, no oficial: sigue los avisos de la Armada.",
                                 "/clima/"))
    return salida


def _oficiales(ahora):
    from .models import Boletin

    salida = []
    nombres = {"advertencia": "Advertencia del INAMHI", "oleaje": "Boletín de oleaje del INOCAR", "erfen": "Boletín ERFEN (El Niño)"}
    for b in Boletin.objects.filter(afecta_galapagos=True, visto_en__gte=ahora - timedelta(hours=12)):
        if b.vigente_hasta and b.vigente_hasta < ahora:
            continue
        tema = "mar" if b.tipo == "oleaje" else "oficiales"
        salida.append(emitir(tema, "", f"boletin:{b.huella[:24]}", f"{nombres.get(b.tipo, 'Boletín oficial')}{' n.º ' + b.numero if b.numero else ''}",
                             (b.resumen or "Hay un boletín oficial nuevo que nombra a Galápagos.")[:230] + " Lee el documento oficial.", b.enlace or "/clima/"))
    return salida

# SOS Galápagos · © 2026 Universidad San Francisco de Quito (USFQ) · Autor: Julián Maya <jamaya@usfq.edu.ec>
# Licencia Apache 2.0 (ver LICENSE y NOTICE): puede reutilizarse dando crédito.
"""Avisos a los teléfonos: cada persona elige de qué quiere enterarse y de qué islas.

Temas:
  peligros    un peligro confirmado en el mapa
  lluvia      está lloviendo fuerte AHORA en la isla (lo medido en la última hora)
  pronostico  mañana se espera lluvia fuerte (señal alta del pronóstico)
  mar         oleaje fuerte
  oficiales   una advertencia o un boletín oficial nuevo que nombra a Galápagos

Reglas (rehechas el 22-nov-2026, tras un aviso que asustó sin motivo a las 2 de la mañana):

1. **De noche no se manda nada.** Entre las 21:00 y las 06:00 (hora de Galápagos) los avisos quedan
   retenidos y a las 06:00 sale un solo resumen de lo que pasó. La única excepción es lo urgente
   (llueve muy fuerte ahora, o un peligro de vida confirmado), y solo para quien pidió recibirlo de noche.
2. **La lluvia se avisa si está lloviendo ahora.** Antes bastaba que el nivel siguiera «muy alto» por
   lo acumulado en 24 horas: avisó de «lluvia peligrosa» cuando ya no llovía. Ahora hace falta lluvia
   medida en la última hora y que lo instantáneo, no lo acumulado, esté en «alto» o más.
3. **El texto dice lo que se midió y dónde, sin órdenes ni adjetivos.** No dice «peligrosa» ni «aléjate».
4. Cada aviso lleva una clave: el mismo no sale dos veces. Todos, enviados o retenidos, se ven en la
   línea del tiempo (/riesgos/informe/).

Todo es información preliminar, no oficial, salvo los boletines, que enlazan al documento de la institución.
"""
from datetime import datetime, timedelta, timezone

from .consultas import GALAPAGOS
from .models import AvisoEnviado

TEMAS = {
    "peligros": "Peligros confirmados en el mapa",
    "lluvia": "Cuando llueve fuerte en mi isla",
    "pronostico": "Lluvia fuerte esperada para mañana",
    "mar": "Oleaje fuerte",
    "oficiales": "Advertencias y boletines oficiales (INAMHI, INOCAR)",
}
ZONAS = {"santa-cruz": "Santa Cruz", "san-cristobal": "San Cristóbal", "isabela": "Isabela"}
ZONA_DE_CLIMA = {"la-cascada": "santa-cruz", "santa-cruz-alta": "santa-cruz", "san-cristobal": "san-cristobal", "isabela": "isabela"}
POR_DEFECTO = ["peligros", "lluvia", "oficiales"]
OLA_FUERTE_M = 2.5       # umbral preliminar para avisar de oleaje
SILENCIO = (21, 6)       # de las 21:00 a las 06:00, hora de Galápagos, no se manda nada
LLUVIA_AHORA_MM = 5      # lluvia mínima en la última hora para decir «está lloviendo» (preliminar)


def es_de_noche(ahora):
    hora = ahora.astimezone(GALAPAGOS).hour
    return hora >= SILENCIO[0] or hora < SILENCIO[1]


def destinatarios(tema, zona="", solo_de_noche=False):
    """Suscripciones que pidieron ese tema y esa isla (o no eligieron islas: todas)."""
    from reportes.models import SuscripcionPush

    return [s for s in SuscripcionPush.objects.all()
            if tema in (s.temas or POR_DEFECTO) and (not zona or not s.zonas or zona in s.zonas) and (s.de_noche or not solo_de_noche)]


def emitir(tema, zona, clave, titulo, cuerpo, enlace="/riesgos/", urgente=False, ahora=None):
    """Registra un aviso una sola vez y lo manda, salvo de noche. Devuelve el AvisoEnviado, o None si esa clave ya había salido."""
    from reportes import avisos

    ahora = ahora or datetime.now(timezone.utc)
    noche = es_de_noche(ahora)
    aviso, nuevo = AvisoEnviado.objects.get_or_create(clave=clave[:120], defaults={
        "tema": tema, "zona": zona, "titulo": titulo[:120], "cuerpo": cuerpo[:300], "enlace": enlace[:200], "urgente": urgente, "retenido": noche})
    if not nuevo:
        return None
    if noche and not urgente:
        return aviso  # espera al resumen de la mañana
    aviso.entregados = avisos.enviar(titulo[:120], cuerpo[:300], enlace, etiqueta=clave[:60], a=destinatarios(tema, zona, solo_de_noche=noche))
    aviso.save(update_fields=["entregados"])
    return aviso


def revisar(ahora=None):
    """Mira si algo merece aviso: lluvia medida, pronóstico de mañana, mar y boletines. Devuelve los emitidos."""
    ahora = ahora or datetime.now(timezone.utc)
    return [a for a in (_lluvia(ahora) + _pronostico(ahora) + _mar(ahora) + _oficiales(ahora) + _resumen_de_la_noche(ahora)) if a]


def _lluvia(ahora):
    from reportes import clima as panel

    inundacion = (panel.estado() or {}).get("inundacion") or {}
    local = ahora.astimezone(GALAPAGOS)
    bloque = f"{local:%Y-%m-%d}-{local.hour // 6}"  # como mucho uno cada 6 horas por isla e intensidad
    # Una isla puede tener varias zonas con lluvia: sale un solo aviso, con la que más llueve ahora.
    peor = {}
    for z in inundacion.get("zonas") or []:
        ahora_mismo, isla = (z.get("nivel_instantaneo") or "").lower(), ZONA_DE_CLIMA.get(z.get("id"))
        ultima_hora = (z.get("R") or {}).get("R1h") or 0
        # Tiene que estar lloviendo: lo acumulado de ayer no es motivo de aviso.
        if ahora_mismo not in ("alto", "muy alto") or not isla or ultima_hora < LLUVIA_AHORA_MM:
            continue
        if isla not in peor or ultima_hora > ((peor[isla][1].get("R") or {}).get("R1h") or 0):
            peor[isla] = (ahora_mismo, z)
    salida = []
    for isla, (intensidad, z) in peor.items():
        R = z.get("R") or {}
        muy = intensidad == "muy alto"
        medido = f"{round(R['R1h'])} mm en la última hora" + (f" y {round(R['R3h'])} en tres horas" if R.get("R3h") and R["R3h"] > R["R1h"] + 1 else "")
        consejo = "Evita cruzar quebradas y calles con agua." if muy else "Si vives junto a una quebrada o en una zona baja, mantente atento."
        salida.append(emitir("lluvia", isla, f"lluvia:{isla}:{intensidad}:{bloque}", f"Llueve {'muy ' if muy else ''}fuerte en {ZONAS[isla]}",
                             f"{z.get('zona', '')}: {medido}. {consejo} Medición preliminar, no oficial.",
                             f"/clima/?zona={z['id']}", urgente=muy, ahora=ahora))
    return salida


def _resumen_de_la_noche(ahora):
    """A las 06:00, un solo aviso con lo que se retuvo durante la noche."""
    local = ahora.astimezone(GALAPAGOS)
    if local.hour != SILENCIO[1]:
        return []
    pendientes = list(AvisoEnviado.objects.filter(retenido=True, resumido=False, creado__gte=ahora - timedelta(hours=12)).order_by("creado"))
    if not pendientes:
        return []
    AvisoEnviado.objects.filter(pk__in=[a.pk for a in pendientes]).update(resumido=True)
    # Lo que ya llegó de noche a alguien (lo urgente, a quien lo pidió) se cuenta igual: el resumen es para todos.
    lineas = [f"{a.creado.astimezone(GALAPAGOS):%H:%M} {a.titulo}" for a in pendientes]
    cuerpo = " · ".join(lineas)
    if len(cuerpo) > 250:
        cuerpo = " · ".join(lineas[:3]) + f" · y {len(lineas) - 3} más"
    from reportes import avisos
    from reportes.models import SuscripcionPush

    resumen, nuevo = AvisoEnviado.objects.get_or_create(clave=f"resumen:{local:%Y-%m-%d}", defaults={
        "tema": "resumen", "zona": "", "titulo": "Esta noche en Galápagos", "cuerpo": cuerpo[:300], "enlace": "/riesgos/informe/"})
    if not nuevo:
        return []
    temas = {a.tema for a in pendientes}
    quienes = [s for s in SuscripcionPush.objects.all() if temas & set(s.temas or POR_DEFECTO)]
    resumen.entregados = avisos.enviar(resumen.titulo, resumen.cuerpo, resumen.enlace, etiqueta=resumen.clave, a=quienes)
    resumen.save(update_fields=["entregados"])
    return [resumen]


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
                             "/clima/", ahora=ahora))
    return salida


def _mar(ahora):
    from .mar import PUERTOS
    from .models import MarHora

    salida = []
    for puerto, p in PUERTOS.items():
        pico = MarHora.objects.filter(puerto=puerto, fuente="stormglass", hora__gte=ahora, hora__lte=ahora + timedelta(hours=36), ola_m__gte=OLA_FUERTE_M).order_by("-ola_m").first()
        if pico:
            cuando = pico.hora.astimezone(GALAPAGOS)
            salida.append(emitir("mar", p["zona"], f"mar:{puerto}:{cuando:%Y-%m-%d}", f"Oleaje fuerte en {p['nombre']}",
                                 f"Se esperan olas de hasta {pico.ola_m:.1f} m hacia las {cuando:%H} h del {cuando:%d-%m}. Pronóstico de un modelo, no oficial: sigue los avisos de la Armada.",
                                 "/clima/", ahora=ahora))
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
                             (b.resumen or "Hay un boletín oficial nuevo que nombra a Galápagos.")[:230] + " Lee el documento oficial.", b.enlace or "/clima/", ahora=ahora))
    return salida

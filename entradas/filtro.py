# SOS Galápagos · © 2026 Universidad San Francisco de Quito (USFQ) · Autor: Julián Maya <jamaya@usfq.edu.ec>
# Todos los derechos reservados. Usar, copiar, modificar o derivar de este código requiere permiso escrito del autor (ver LICENSE).
"""Primer filtro de los mensajes de WhatsApp: reglas y expresiones regulares, sin modelo.

Decide si un mensaje parece material para SOS Galápagos (un peligro, un daño, algo bueno,
un lugar donde ayudar) o si es una conversación cualquiera. Es barato y corre en el
servidor: lo que no pasa este filtro no se guarda ni se manda a ningún modelo de lenguaje.

Devuelve un puntaje y los motivos, para poder ajustar las reglas mirando casos reales.
"""
import re
import unicodedata
from dataclasses import dataclass, field

UMBRAL = 3  # puntaje mínimo para tratar el mensaje como material (preliminar)


def sin_tildes(texto):
    return "".join(c for c in unicodedata.normalize("NFD", texto or "") if unicodedata.category(c) != "Mn").lower()


# Quien escribe esto quiere reportar: pasa siempre.
LLAMADA = re.compile(r"\bsos\s*galapagos\b|#\s*sos\b|#\s*reporte\b|^\s*report(e|ar|o)\b|\bquiero reportar\b|\bpara el mapa\b")

TEMAS = {
    "agua": re.compile(r"\binund\w+|\banegad[oa]s?\b|\bagua (en|hasta|por|a la|al|corre|sube|baja|llega|entra|entro|se metio)\b|\bse (esta )?(desborda|desbordo|metio el agua)\b|\bcorrentada\b|\bencharcad[oa]\b|\bcreciente\b|\b(quebrada|canada|encanada)s?\b"),
    "via": re.compile(r"\b(via|calle|camino|carretera|paso|puente|vereda)\s+(esta\s+)?(cerrad[oa]|cortad[oa]|bloquead[oa]|intransitable|destruid[oa]|hundid[oa]|caid[oa])\b|\bno (se puede|hay) pas(ar|o)\b|\bderrumbe\b|\bdeslave\b|\bdeslizamiento\b|\barbol caido\b"),
    "infraestructura": re.compile(r"\bsin (luz|agua|energia|internet|senal)\b|\bcable (caido|suelto|en el suelo)\b"),
    "ayuda": re.compile(r"\b(centro|punto|lugar) de acopio\b|\b(reciben|recibimos|se reciben|estan recibiendo)\b.*\b(donacion|viveres|ropa|agua|kits?|colchones|alimentos)\b|\bdonaciones?\b|\b(olla comun|almuerzos? gratis|reparten|estan repartiendo|entregan|voluntari[oa]s?)\b|\brefugio\b"),
    # Lo que la gente vio y sirve para afinar el mapa: «aquí no pasó nada», «aquí siempre se inunda», «aquí llegó hasta…».
    "observacion": re.compile(r"\b(aqui|aca|por aqui|en mi (casa|barrio|calle)|en este (barrio|sector))\b.*\b(todo (esta )?(bien|tranquilo|normal|seco)|no (paso|pasa|ha pasado) nada|no (se inundo|se inunda|llego el agua|entro el agua|hubo agua))\b|\btodo (esta )?(bien|tranquilo|seco) (aqui|aca|por aqui|en)\b|\b(siempre|cada vez que llueve|todos los anos) se (inunda|llena|empoza)\b|\bzona de riesgo\b|\b(ayer|anoche|esa noche|el (lunes|martes|miercoles|jueves|viernes|sabado|domingo)) (se inundo|llego el agua|entro el agua|subio el agua)\b"),
    "bueno": re.compile(r"\bya (volvio|regreso|hay) (la )?(luz|agua|senal|internet|paso)\b|\bya (se puede pasar|habilitaron|limpiaron|abrieron)\b|\bbuena noticia\b"),
}
# Daño en infraestructura: una obra pública y una palabra de daño, en cualquier orden.
OBRA = re.compile(r"\b(tuberia|alcantarilla(do)?|poste|puente|via|calle|carretera|acera|vereda|muro|muelle|malecon|escuela|colegio|centro de salud|hospital|tanque|transformador|alumbrado|cableado|parque|cancha|semaforo)s?\b")
DANO = re.compile(r"\b(dano|danad[oa]|rot[oa]|colaps\w*|hundi\w*|socavon|hueco|bache|fuga|grieta|agrietad[oa]|caid[oa]|se cayo|destruid[oa]|destrozad[oa]|levantad[oa]|peligros[oa])s?\b")
# Pistas de lugar: sin lugar no hay reporte, pero suman para decidir.
LUGAR = re.compile(r"\b(barrio|sector|calle|av\.?|avenida|pasaje|callejon|via a|frente a|junto a|esquina|diagonal a|km|kilometro|entrada a|en (el|la|los|las) [a-z])")
ENLACE_MAPA = re.compile(r"https?://(maps\.app\.goo\.gl|goo\.gl/maps|(www\.)?google\.[a-z.]+/maps|maps\.google\.[a-z.]+|maps\.apple\.com|waze\.com)/\S*", re.I)
# Conversación cualquiera: resta.
RUIDO = re.compile(r"^(hola|buen[oa]s? (dias|tardes|noches)|gracias|ok|okey|jaja+|listo|dale|si|no|👍|🙏)[\s.!?]*$")
REENVIO = re.compile(r"\b(cadena|reenviado|compart[ae]n|pasen la voz)\b")


@dataclass
class Veredicto:
    puntaje: int = 0
    motivos: list = field(default_factory=list)
    temas: list = field(default_factory=list)

    @property
    def es_material(self):
        return self.puntaje >= UMBRAL


def evaluar(texto="", tiene_foto=False, tiene_ubicacion=False, conversacion_abierta=False):
    """Puntúa un mensaje. Con una conversación abierta casi todo cuenta: la persona está respondiendo."""
    t = sin_tildes(texto)
    v = Veredicto()

    def suma(puntos, motivo):
        v.puntaje += puntos
        v.motivos.append(f"{'+' if puntos > 0 else ''}{puntos} {motivo}")

    if conversacion_abierta:
        suma(UMBRAL, "conversación abierta")
    if LLAMADA.search(t):
        suma(UMBRAL, "pide reportar")
    for tema, patron in TEMAS.items():
        if patron.search(t):
            v.temas.append(tema)
    if "infraestructura" not in v.temas and OBRA.search(t) and DANO.search(t):
        v.temas.append("infraestructura")
    if v.temas:
        suma(2, "tema: " + ", ".join(v.temas))
    if tiene_foto:
        suma(1, "trae foto")
    if tiene_ubicacion or ENLACE_MAPA.search(texto or ""):
        suma(1, "trae ubicación")
    if LUGAR.search(t):
        suma(1, "nombra un lugar")
    if RUIDO.match(t) and not conversacion_abierta:
        suma(-3, "saludo o respuesta corta")
    if REENVIO.search(t):
        suma(-1, "parece una cadena")
    if len(t) > 900:
        suma(-1, "texto muy largo")
    return v

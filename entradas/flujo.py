"""Lo que pasa con un mensaje de WhatsApp, de principio a fin.

1. `recibir` (rápido, sin modelo): descarta lo que no es de un chat permitido y lo que no
   pasa el filtro de reglas. Lo descartado no se guarda.
2. `procesar` (en segundo plano): un modelo de lenguaje saca los datos, se reúnen con lo
   que la persona ya dijo, se pregunta lo que falte y, cuando está completo, se publica y
   se le responde con el enlace y sus puntos.

Un aviso necesita: qué pasa, dónde (lo más exacto posible) y, si es un lugar que recibe
donaciones, un teléfono de contacto. El nombre para los puntos se pregunta después de
publicar: nunca frena un aviso.
"""
import base64
import hashlib
import logging
import re
from datetime import timedelta

from django.conf import settings
from django.contrib.gis.geos import Point
from django.core.files.base import ContentFile
from django.utils import timezone

from reportes import fotos, reglas
from reportes.models import Fuente, Gravedad, Profundidad, Reporte, TipoRiesgo
from zonas.models import zona_de

from . import filtro, ia, lugar, openwa
from .models import Canal, Conversacion, EstadoCola, MensajeEntrante

registro = logging.getLogger(__name__)

PIDE_UBICACION = (
    "¿Dónde es exactamente? Lo mejor es tu *ubicación*: toca el clip (📎) → Ubicación → «Enviar mi ubicación actual» "
    "si estás ahí, o mueve el pin al lugar. También sirve un enlace de Google Maps o, si no, la dirección exacta "
    "(barrio, calle y una referencia)."
)
PIDE_QUE_PASA = "Cuéntame en una frase qué está pasando ahí. Si puedes, manda también una foto (sin caras ni documentos)."
PIDE_CONTACTO = "¿A qué teléfono puede llamar la gente antes de ir a ese lugar? Es el contacto del sitio, no el tuyo. Si no hay, responde «no hay»."
PIDE_NOMBRE = "¿Con qué nombre o apodo quieres aparecer en la tabla de puntos? Si prefieres no aparecer, responde «no»."
NEGATIVAS = re.compile(r"^\s*(no|no hay|no tengo|ninguno|anonimo|prefiero no|paso|no se)\b", re.I)


# ── Identidad sin guardar el número ──────────────────────────────────────────
def _fernet():
    from cryptography.fernet import Fernet

    return Fernet(base64.urlsafe_b64encode(hashlib.sha256(("chat:" + settings.SECRET_KEY).encode()).digest()))


def cifrar(chat):
    return _fernet().encrypt(chat.encode()).decode()


def descifrar(cifrado):
    return _fernet().decrypt(cifrado.encode()).decode()


def huella_de_chat(chat, autor=""):
    """Resumen con clave de la persona. En un grupo, cada autor es una persona distinta."""
    return reglas.huella_de(f"wa:{chat}|{autor if autor and autor != chat else ''}")


def permitido(mensaje):
    if settings.WHATSAPP_MODO not in ("ensayo", "activo") or mensaje.propio:
        return False
    if mensaje.chat in settings.WHATSAPP_CHATS:
        return True
    return settings.WHATSAPP_DIRECTOS and not mensaje.es_grupo and mensaje.chat.endswith(("@c.us", "@lid", "@s.whatsapp.net"))


# ── 1. Recibir ───────────────────────────────────────────────────────────────
def recibir(carga):
    """Devuelve el MensajeEntrante guardado, o None si el mensaje no se atiende."""
    mensaje = carga if isinstance(carga, openwa.Mensaje) else openwa.normalizar(carga)
    if not mensaje or not permitido(mensaje):
        return None
    if mensaje.id and MensajeEntrante.objects.filter(id_externo=mensaje.id).exists():
        return None  # el servidor reintenta: ya se procesó
    huella = huella_de_chat(mensaje.chat, mensaje.autor)
    reciente = timezone.now() - timedelta(minutes=settings.WHATSAPP_CONVERSACION_MIN)
    conversacion = Conversacion.objects.filter(chat_hash=huella).first()
    abierta = bool(conversacion and conversacion.actualizada_en > reciente and (conversacion.borrador or conversacion.espera))
    veredicto = filtro.evaluar(mensaje.texto, mensaje.tiene_foto, mensaje.lat is not None, conversacion_abierta=abierta)
    if not veredicto.es_material:
        return None  # conversación cualquiera: no se guarda nada
    if not conversacion:
        conversacion = Conversacion.objects.create(chat_hash=huella, chat_cifrado=cifrar(mensaje.chat), es_grupo=mensaje.es_grupo)
    elif not abierta:
        conversacion.borrador, conversacion.espera, conversacion.intentos = {}, "", 0  # empieza un aviso nuevo
        conversacion.save()
    return MensajeEntrante.objects.create(
        canal=Canal.WHATSAPP_GRUPO if mensaje.es_grupo else Canal.WHATSAPP_DIRECTO,
        remitente_hash=huella,
        id_externo=mensaje.id,
        conversacion=conversacion,
        texto=mensaje.texto[:2000],
        candidato={"tipo_mensaje": mensaje.tipo, "lat": mensaje.lat, "lon": mensaje.lon, "tiene_foto": mensaje.tiene_foto,
                   "filtro": veredicto.motivos, "pide_reportar": bool(filtro.LLAMADA.search(filtro.sin_tildes(mensaje.texto)))},
    )


# ── 2. Procesar ──────────────────────────────────────────────────────────────
def _foto_limpia(crudo):
    """La foto vuelta a codificar, sin metadatos, en base64 para guardarla en el borrador."""
    from io import BytesIO

    try:
        limpia, _ = fotos.procesar(BytesIO(crudo))
        return base64.b64encode(limpia.read()).decode()
    except Exception:
        return ""


def _responder(conversacion, mensaje, texto):
    mensaje.respuesta = texto
    mensaje.save(update_fields=["respuesta"])
    if not texto or settings.WHATSAPP_MODO != "activo":
        return  # en ensayo queda escrito lo que se habría respondido
    if conversacion.es_grupo and not settings.WHATSAPP_RESPONDER_EN_GRUPOS:
        return
    try:
        openwa.enviar_texto(descifrar(conversacion.chat_cifrado), texto)
    except Exception:
        registro.exception("No se pudo responder por WhatsApp")


def _preguntar(conversacion, mensaje, que, texto):
    conversacion.intentos = conversacion.intentos + 1 if conversacion.espera == que else 1
    conversacion.espera = que
    conversacion.save()
    _responder(conversacion, mensaje, texto)
    return texto


def _tomar_nombre(conversacion, mensaje):
    """La persona responde a «¿con qué nombre quieres aparecer?»."""
    texto = mensaje.texto.strip()
    conversacion.espera, conversacion.intentos = "", 0
    conversacion.save()
    if not texto or NEGATIVAS.match(filtro.sin_tildes(texto)):
        return "Listo, sin nombre. Tus puntos se siguen sumando. Gracias por avisar."
    nombre = reglas.limpiar_nombre(re.sub(r"^(me llamo|soy|mi nombre es|ponme|pon)\s+", "", texto, flags=re.I).strip(" .!"))
    if not nombre or len(nombre.split()) > 4:
        return "No pude tomar ese nombre. Escríbeme solo el nombre o apodo, sin números."
    reglas.sumar_puntos(mensaje.remitente_hash, 0, nombre=nombre)
    colaborador = reglas.colaborador_de(mensaje.remitente_hash)
    return f"Gracias, {nombre}. Llevas {colaborador.puntos} puntos. La tabla está en {settings.SITIO_URL}/riesgos/puntos/"


def procesar(mensaje_id, foto=None):
    """Atiende un mensaje ya recibido. Devuelve lo que se respondió (o se habría respondido)."""
    mensaje = MensajeEntrante.objects.select_related("conversacion").get(pk=mensaje_id)
    conversacion = mensaje.conversacion
    b = dict(conversacion.borrador or {})
    c = mensaje.candidato or {}

    if conversacion.espera == "nombre" and not c.get("tiene_foto") and c.get("lat") is None and len(mensaje.texto) <= 60:
        respuesta = _tomar_nombre(conversacion, mensaje)
        mensaje.estado_cola = EstadoCola.PUBLICADO if conversacion.ultimo_reporte_id else EstadoCola.DESCARTADO
        mensaje.reporte = conversacion.ultimo_reporte
        mensaje.save(update_fields=["estado_cola", "reporte"])
        _responder(conversacion, mensaje, respuesta)
        return respuesta

    # La foto: se baja del servidor de WhatsApp, se limpia y se guarda con el borrador.
    if c.get("tiene_foto"):
        crudo = foto or (openwa.bajar_foto(descifrar(conversacion.chat_cifrado), mensaje.id_externo) if settings.OPENWA_LLAVE else None)
        if crudo:
            b["foto"] = _foto_limpia(crudo) or b.get("foto", "")

    tipos = list(TipoRiesgo.objects.filter(activo=True))
    textos = [m.texto for m in conversacion.mensajes.order_by("-recibido_en")[:6]][::-1]
    e = ia.extraer(textos, base64.b64decode(b["foto"]) if b.get("foto") else None, tipos, b, conversacion.espera)

    codigos = {t.codigo: t for t in tipos}
    # Si la persona está respondiendo a una pregunta (dónde, qué teléfono), el tipo ya dicho no cambia.
    respondiendo = conversacion.espera in ("ubicacion", "contacto") and b.get("tipo") in codigos
    if e.tipo in codigos and not respondiendo:
        b["tipo"] = e.tipo
    for campo in ("titulo", "descripcion", "direccion", "gravedad", "profundidad"):
        valor = getattr(e, campo)
        if valor:
            b[campo] = valor
    telefono = e.contacto
    if not telefono and conversacion.espera == "contacto":
        hallado = re.search(r"(?<!\d)\+?\d[\d\s-]{6,13}\d(?!\d)", mensaje.texto)  # respondió solo con el número
        telefono = hallado.group(0) if hallado else None
    if telefono:
        b["contacto"] = re.sub(r"[^\d+]", "", telefono)[:40]

    # El lugar, por orden de confianza.
    exacto = None
    if lugar.en_galapagos(c.get("lat"), c.get("lon")):
        exacto = (c["lat"], c["lon"])
    exacto = exacto or lugar.de_enlace(mensaje.texto) or lugar.de_coordenadas(mensaje.texto)
    if exacto:
        b["lat"], b["lon"], b["aproximado"] = exacto[0], exacto[1], False
    elif "lat" not in b:
        zona = lugar.de_zona(" ".join(filter(None, [b.get("direccion"), mensaje.texto])))
        if zona:
            b["zona_lat"], b["zona_lon"], b["zona_nombre"] = zona[1], zona[2], zona[0].nombre

    conversacion.borrador = b
    tipo = codigos.get(b.get("tipo"))
    tiene_algo = tipo or b.get("foto") or "lat" in b

    if not e.es_reporte and not tiene_algo:
        conversacion.save()
        mensaje.estado_cola = EstadoCola.DESCARTADO
        mensaje.save(update_fields=["estado_cola"])
        respuesta = PIDE_QUE_PASA + " Y dime dónde es." if c.get("pide_reportar") else ""
        if respuesta:
            return _preguntar(conversacion, mensaje, "que_pasa", respuesta)
        return ""

    if not tipo or not b.get("descripcion"):
        if conversacion.espera == "que_pasa" and conversacion.intentos >= 2:
            return _pasar_a_coordinacion(conversacion, mensaje)
        return _preguntar(conversacion, mensaje, "que_pasa", PIDE_QUE_PASA)

    if "lat" not in b:
        ya_pregunte = conversacion.espera == "ubicacion"
        if "zona_lat" in b and (ya_pregunte or e.no_puede_ubicar):
            # No pudo mandar el punto: se publica en el centro del barrio y se dice que es aproximado.
            b["lat"], b["lon"], b["aproximado"] = b["zona_lat"], b["zona_lon"], True
        elif ya_pregunte and conversacion.intentos >= 2:
            return _pasar_a_coordinacion(conversacion, mensaje)
        else:
            return _preguntar(conversacion, mensaje, "ubicacion", PIDE_UBICACION)

    if tipo.pide_contacto and not b.get("contacto"):
        sin_contacto = conversacion.espera == "contacto" and (NEGATIVAS.match(filtro.sin_tildes(mensaje.texto)) or conversacion.intentos >= 2)
        if not sin_contacto:
            conversacion.borrador = b
            return _preguntar(conversacion, mensaje, "contacto", PIDE_CONTACTO)

    return _publicar(conversacion, mensaje, tipo, b)


def _pasar_a_coordinacion(conversacion, mensaje):
    """No se pudo completar: queda en la cola para que una persona lo revise."""
    mensaje.candidato = {**(mensaje.candidato or {}), "borrador": {k: v for k, v in conversacion.borrador.items() if k != "foto"}}
    mensaje.estado_cola = EstadoCola.PENDIENTE
    mensaje.save(update_fields=["candidato", "estado_cola"])
    conversacion.espera, conversacion.intentos = "", 0
    conversacion.save()
    respuesta = "Gracias. Con lo que tengo no alcanzo a ponerlo en el mapa; lo paso a coordinación para que lo revise una persona. Si es una emergencia, llama al 911."
    _responder(conversacion, mensaje, respuesta)
    return respuesta


def _publicar(conversacion, mensaje, tipo, b):
    huella = mensaje.remitente_hash
    hace_una_hora = timezone.now() - timedelta(hours=1)
    if Reporte.objects.filter(huella=huella, creado_en__gt=hace_una_hora).count() >= settings.LIMITE_REPORTES_HORA:
        respuesta = "Ya enviaste muchos avisos en la última hora. Si es una emergencia, llama al 911."
        _responder(conversacion, mensaje, respuesta)
        return respuesta

    punto = Point(float(b["lon"]), float(b["lat"]), srid=4326)
    aproximado = bool(b.get("aproximado"))
    nota = b.get("descripcion", "")[:280]
    if aproximado and b.get("direccion"):
        nota = (nota + f" (Ubicación aproximada: {b['direccion']}.)")[:280]

    if settings.WHATSAPP_MODO != "activo":
        respuesta = f"[ensayo] Se publicaría «{b.get('titulo') or tipo.nombre}» en {punto.y:.5f}, {punto.x:.5f}{' (aproximado)' if aproximado else ''}."
        mensaje.candidato = {**(mensaje.candidato or {}), "borrador": {k: v for k, v in b.items() if k != "foto"}}
        mensaje.save(update_fields=["candidato"])
        conversacion.borrador, conversacion.espera, conversacion.intentos = {}, "", 0
        conversacion.save()
        _responder(conversacion, mensaje, respuesta)
        return respuesta

    resultado = reglas.crear_reporte(
        tipo=tipo,
        punto=punto,
        huella=huella,
        fuente=Fuente.WHATSAPP,
        titulo=(b.get("titulo") or "")[:80],
        nota=nota,
        foto=ContentFile(base64.b64decode(b["foto"]), name="foto.jpg") if b.get("foto") else None,
        contacto=b.get("contacto", ""),
        gravedad=b.get("gravedad") if b.get("gravedad") in Gravedad.values else Gravedad.CUIDADO,
        profundidad=b.get("profundidad") if b.get("profundidad") in Profundidad.values else Profundidad.SIN_DATO,
        precision_m=500 if aproximado else None,
        zona=zona_de(punto),
    )
    r = resultado.reporte
    mensaje.reporte, mensaje.estado_cola = r, EstadoCola.PUBLICADO
    mensaje.save(update_fields=["reporte", "estado_cola"])
    conversacion.borrador, conversacion.espera, conversacion.intentos, conversacion.ultimo_reporte = {}, "", 0, r
    conversacion.save()

    enlace = f"{settings.SITIO_URL}/riesgos/?r={r.id_publico}"
    colaborador = resultado.colaborador
    if resultado.duplicado:
        partes = [f"Eso ya estaba en el mapa. Tu aviso confirma que sigue ahí y renueva su plazo:\n{enlace}"]
    else:
        partes = [
            f"✅ Publicado: *{r.nombre}*{' · ' + r.zona.nombre if r.zona else ''}\n{enlace}",
            "Ya aparece en el mapa como «por verificar». La foto y el texto se ven cuando coordinación los revise."
            + (" La ubicación es aproximada: si puedes, mándame el punto exacto." if aproximado else ""),
        ]
    total = colaborador.puntos if colaborador else resultado.puntos
    partes.append(f"Ganaste {resultado.puntos} puntos" + (f", {colaborador.nombre}" if colaborador and colaborador.nombre else "") + f". Llevas {total}.")
    if tipo.clase == "riesgo":
        partes.append("Si hay personas en peligro, llama al 911.")
    respuesta = "\n\n".join(partes)
    if not (colaborador and colaborador.nombre):
        respuesta += "\n\n" + PIDE_NOMBRE
        conversacion.espera = "nombre"
        conversacion.save()
    _responder(conversacion, mensaje, respuesta)
    return respuesta


# ── Limpieza ─────────────────────────────────────────────────────────────────
def purgar(ahora=None):
    """Borra el texto de los mensajes viejos y las conversaciones sin actividad. No toca los reportes."""
    limite = (ahora or timezone.now()) - timedelta(days=settings.WHATSAPP_RETENCION_DIAS)
    textos = MensajeEntrante.objects.filter(recibido_en__lt=limite).exclude(texto="", respuesta="").update(texto="", respuesta="")
    conversaciones, _ = Conversacion.objects.filter(actualizada_en__lt=limite).delete()
    return textos, conversaciones

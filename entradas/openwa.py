# SOS Galápagos · © 2026 Universidad San Francisco de Quito (USFQ) · Autor: Julián Maya <jamaya@usfq.edu.ec>
# Licencia Apache 2.0 (ver LICENSE y NOTICE): puede reutilizarse dando crédito.
"""Cliente mínimo del servidor de WhatsApp (OpenWA): leer lo que llega, bajar una foto y responder.

No guarda nada. Las direcciones son las de la API del servidor: /api/sessions/<sesión>/…
con la llave en la cabecera X-API-Key.
"""
import base64
import json
import urllib.error
import urllib.request
from dataclasses import dataclass
from urllib.parse import quote

from django.conf import settings


@dataclass
class Mensaje:
    """Un mensaje entrante, ya sin las diferencias de formato entre el webhook y la API."""

    id: str
    chat: str            # identificador del chat (persona o grupo)
    autor: str           # quien escribe (en un grupo, distinto del chat)
    es_grupo: bool
    tipo: str            # text, image, location…
    texto: str
    lat: float | None = None
    lon: float | None = None
    tiene_foto: bool = False
    foto: bytes | None = None
    propio: bool = False


def _numero(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def normalizar(carga):
    """Convierte lo que manda el webhook (o una fila de la API) en un Mensaje. None si no es un mensaje entrante.

    Formato comprobado el 22-nov-2026 (evento «message.received»): el mensaje viene en «data», con
    id, from, to, chatId, body, type, timestamp, fromMe, isGroup, contact y, en una ubicación,
    location {latitude, longitude, description}. El «id» es el que pide la descarga de la foto.
    Se aceptan también otras envolturas («message», «payload») por si cambia la versión.
    """
    m = carga
    for clave in ("data", "payload", "message"):
        if isinstance(m, dict) and isinstance(m.get(clave), dict):
            m = m[clave]
    if not isinstance(m, dict):
        return None
    chat = m.get("chatId") or m.get("from") or ""
    if not chat:
        return None
    propio = bool(m.get("fromMe")) or m.get("direction") == "outgoing"
    tipo = (m.get("type") or "text").lower()
    meta = m.get("metadata") if isinstance(m.get("metadata"), dict) else {}
    donde = m.get("location") if isinstance(m.get("location"), dict) else meta.get("location") if isinstance(meta.get("location"), dict) else {}
    lat = _numero(donde.get("latitude", donde.get("lat", m.get("latitude", m.get("lat", meta.get("latitude"))))))
    lon = _numero(donde.get("longitude", donde.get("lng", donde.get("lon", m.get("longitude", m.get("lng", meta.get("longitude")))))))
    texto = m.get("caption") or m.get("body") or m.get("text") or ""
    if tipo in ("image", "location", "video", "sticker", "audio", "voice", "document") and not m.get("caption"):
        # En estos tipos «body» puede traer la miniatura en base64, no un texto.
        texto = "" if len(texto) > 400 or texto.startswith("/9j/") else texto
        if tipo == "location":
            texto = donde.get("description") or donde.get("name") or donde.get("address") or ""
    foto = None
    medio = m.get("media") if isinstance(m.get("media"), dict) else {}
    if tipo == "image" and medio.get("data"):
        try:
            foto = base64.b64decode(medio["data"])
        except Exception:
            foto = None
    return Mensaje(
        id=str(m.get("waMessageId") or m.get("messageId") or m.get("id") or ""),
        chat=chat,
        autor=m.get("author") or m.get("participant") or m.get("from") or chat,
        es_grupo=bool(m.get("isGroup")) or chat.endswith("@g.us"),
        tipo=tipo,
        texto=str(texto).strip(),
        lat=lat,
        lon=lon,
        tiene_foto=tipo == "image",
        foto=foto,
        propio=propio,
    )


def _pedir(ruta, datos=None, crudo=False):
    if not (settings.OPENWA_URL and settings.OPENWA_LLAVE and settings.OPENWA_SESION):
        raise RuntimeError("Falta configurar OPENWA_URL, OPENWA_LLAVE u OPENWA_SESION")
    url = f"{settings.OPENWA_URL}/api/sessions/{settings.OPENWA_SESION}{ruta}"
    cabeceras = {"X-API-Key": settings.OPENWA_LLAVE, "Accept": "*/*"}
    cuerpo = None
    if datos is not None:
        cuerpo = json.dumps(datos).encode()
        cabeceras["Content-Type"] = "application/json"
    with urllib.request.urlopen(urllib.request.Request(url, data=cuerpo, headers=cabeceras), timeout=30) as r:
        contenido = r.read()
    return contenido if crudo else (json.loads(contenido) if contenido else {})


def enviar_texto(chat, texto):
    return _pedir("/messages/send-text", {"chatId": chat, "text": texto})


def bajar_foto(chat, id_mensaje):
    """Los bytes de la foto de un mensaje, o None si no se pudo."""
    try:
        return _pedir(f"/messages/{quote(chat, safe='')}/{quote(id_mensaje, safe='')}/media", crudo=True)
    except (urllib.error.URLError, RuntimeError, TimeoutError):
        return None

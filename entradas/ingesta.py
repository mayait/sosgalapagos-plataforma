# SOS Galápagos · © 2026 Universidad San Francisco de Quito (USFQ) · Autor: Julián Maya <jamaya@usfq.edu.ec>
# Licencia Apache 2.0 (ver LICENSE y NOTICE): puede reutilizarse dando crédito.
"""Lo que sube cada hora la Mac de coordinación desde los grupos de WhatsApp.

La descarga y la clasificación corren en la Mac (despliegue/ingesta/). Aquí solo llega un
elemento ya limpio: una foto (o un fotograma de un video), la hora del mensaje, el texto sin
nombres ni teléfonos, la clasificación y, si es segura, la ubicación. El servidor nunca recibe
el grupo, el remitente, el video ni la carpeta.

Por si algo se le escapó a la Mac, aquí se vuelve a limpiar: la foto se recodifica sin
metadatos y los números largos del texto se ocultan.

1. Con ubicación segura: va al mapa por reglas.crear_reporte, como cualquier reporte (sus
   duplicados incluidos). Si la foto pide revisión, el punto sale sin foto y la foto queda
   para coordinación.
2. Sin ubicación segura: va a «Ayúdanos a ubicar» (reportes.PorUbicar), o a revisión si la
   foto lo pide.

Cada elemento lleva un `id_origen` (un resumen que da la Mac): si llega dos veces, la segunda
no hace nada.
"""
import json
import re
from datetime import datetime, timedelta

from django.conf import settings
from django.contrib.gis.geos import Point
from django.utils import timezone

from reportes import fotos, reglas
from reportes.models import EstadoUbicar, Fuente, PorUbicar, TipoRiesgo
from zonas.models import zona_de

from . import lugar

ID_ORIGEN = re.compile(r"^[a-z0-9:_-]{8,80}$")
HUELLA_INGESTA = "ingesta:whatsapp"  # una sola «persona» para toda la entrada: no suma puntos a nadie


class Rechazo(Exception):
    def __init__(self, mensaje, estado=400):
        super().__init__(mensaje)
        self.estado = estado


def _hora(valor):
    try:
        hora = datetime.fromisoformat((valor or "").replace("Z", "+00:00"))
    except ValueError:
        raise Rechazo("visto_en no es una fecha ISO")
    if hora.tzinfo is None:
        raise Rechazo("visto_en debe llevar zona horaria")
    ahora = timezone.now()
    if hora > ahora + timedelta(minutes=10) or hora < ahora - timedelta(days=60):
        raise Rechazo("visto_en fuera de rango")
    return hora


def _ubicacion(datos):
    lat, lon = datos.get("lat"), datos.get("lon")
    if lat in (None, "") and lon in (None, ""):
        return None
    try:
        lat, lon = float(lat), float(lon)
    except (TypeError, ValueError):
        raise Rechazo("lat y lon deben ser números")
    if not lugar.en_galapagos(lat, lon):
        raise Rechazo("la ubicación queda fuera de Galápagos")
    return Point(lon, lat, srid=4326)


def _foto(archivo):
    if not archivo:
        return None
    if archivo.size > settings.INGESTA_MAX_BYTES:
        raise Rechazo("la foto pesa demasiado", 413)
    try:
        limpia, _ = fotos.procesar(archivo)  # se recodifica: no queda ningún metadato
    except Exception:
        raise Rechazo("no se pudo leer la foto")
    return limpia


def _clasificacion(valor):
    if not valor:
        return {}
    if len(valor) > 4000:
        raise Rechazo("clasificación demasiado larga")
    try:
        dato = json.loads(valor)
    except ValueError:
        raise Rechazo("clasificación ilegible")
    return dato if isinstance(dato, dict) else {}


def recibir(datos, archivo=None, ahora=None):
    """Guarda un elemento. `datos` es el formulario (QueryDict o dict); `archivo`, la foto subida.

    Devuelve un dict con lo que se hizo: {"destino": "mapa" | "ubicar" | "revision", "ya": bool, ...}.
    Lanza Rechazo si el elemento no vale.
    """
    ahora = ahora or timezone.now()
    id_origen = (datos.get("id_origen") or "").strip().lower()
    if not ID_ORIGEN.match(id_origen):
        raise Rechazo("id_origen inválido")
    ya = PorUbicar.objects.filter(id_origen=id_origen).first()
    if ya:
        return {"ya": True, "destino": _destino(ya), "id": ya.id_publico}

    hace_una_hora = ahora - timedelta(hours=1)
    if PorUbicar.objects.filter(id_origen__isnull=False, creado_en__gt=hace_una_hora).count() >= settings.INGESTA_LIMITE_HORA:
        raise Rechazo("demasiados elementos en la última hora", 429)

    visto_en = _hora(datos.get("visto_en"))
    punto = _ubicacion(datos)
    texto = reglas.ocultar_numeros((datos.get("texto") or "").strip())[:280]
    foto = _foto(archivo)
    if not foto and not texto:
        raise Rechazo("hace falta una foto o un texto")
    revisar = str(datos.get("revisar") or "") in ("1", "true", "si")
    motivo = (datos.get("motivo") or "").strip()[:200]
    tipo = TipoRiesgo.objects.filter(codigo=datos.get("tipo") or "", activo=True).first()
    clasificacion = _clasificacion(datos.get("clasificacion"))
    huella = reglas.huella_de(HUELLA_INGESTA)

    item = PorUbicar(
        id_origen=id_origen, visto_en=visto_en, texto=texto, tipo=tipo, huella=huella,
        es_video=str(datos.get("es_video") or "") in ("1", "true"), clasificacion=clasificacion,
        estado=EstadoUbicar.REVISION if revisar else EstadoUbicar.PENDIENTE, motivo_revision=motivo if revisar else "",
    )
    if foto:
        foto.seek(0)
        item.foto.save("foto.jpg", foto, save=False)
        item.huella_foto = _resumen(item.foto)
        # La misma foto reenviada a varios grupos: se pide ubicar una sola vez.
        repetida = PorUbicar.objects.filter(huella_foto=item.huella_foto).exclude(estado=EstadoUbicar.DESCARTADO).first()
        if repetida and not punto:
            item.estado, item.motivo_revision = EstadoUbicar.DESCARTADO, f"Foto repetida de {repetida.id_publico}"
    if not punto:
        zona = lugar.de_zona(texto) if texto else None
        item.pista = zona[0] if zona else None
        item.save()
        return {"ya": False, "destino": _destino(item), "id": item.id_publico}

    # Con ubicación segura: al mapa por el camino de siempre.
    tipo = tipo or TipoRiesgo.objects.filter(codigo=settings.UBICAR_TIPO_POR_DEFECTO).first()
    resultado = reglas.crear_reporte(
        tipo=tipo, punto=punto, huella=huella, fuente=Fuente.WHATSAPP, visto_en=visto_en, ahora=ahora,
        # Una foto que pide revisión no sale con el punto: queda guardada aquí para coordinación.
        foto=None if revisar or not foto else _copia(item.foto), nota=texto, zona=zona_de(punto),
    )
    item.reporte = resultado.reporte
    if not revisar:
        item.estado = EstadoUbicar.UBICADO
    item.save()
    return {"ya": False, "destino": _destino(item), "id": item.id_publico, "reporte": resultado.reporte.id_publico, "duplicado": resultado.duplicado}


def _destino(item):
    if item.estado == EstadoUbicar.REVISION:
        return "revision"
    if item.estado == EstadoUbicar.DESCARTADO:
        return "repetida"
    return "mapa" if item.reporte_id else "ubicar"


def _resumen(campo):
    import hashlib

    campo.open("rb")
    try:
        return hashlib.sha256(campo.read()).hexdigest()
    finally:
        campo.seek(0)


def _copia(campo):
    from django.core.files.base import ContentFile

    campo.open("rb")
    datos = campo.read()
    campo.seek(0)
    return ContentFile(datos, name="foto.jpg")

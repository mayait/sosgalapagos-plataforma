# SOS Galápagos · © 2026 Universidad San Francisco de Quito (USFQ) · Autor: Julián Maya <jamaya@usfq.edu.ec>
# Licencia Apache 2.0 (ver LICENSE y NOTICE): puede reutilizarse dando crédito.
"""Reglas de vida del reporte. Aquí está toda la lógica; las vistas y la API solo llaman.

1. vence_en = visto_en + plazo del tipo.
2. «Sigue ahí» renueva el plazo desde ese momento.
3. «Ya bajó»: la primera pasa el reporte a «bajando»; la segunda, desde otro
   dispositivo, lo cierra.
4. Un reporte nuevo del mismo tipo a menos de 50 m de uno vivo se guarda como
   confirmación «sigue ahí» del existente.
5. Un reporte cerrado nunca se borra: queda en el archivo.

Los umbrales están en plataforma/ajustes.py y son preliminares.
"""
import hashlib
import hmac
import re
from dataclasses import dataclass
from datetime import timedelta

from django.conf import settings
from django.contrib.gis.measure import D
from django.db import transaction
from django.utils import timezone

from .models import Colaborador, Confirmacion, Estado, Fuente, MotivoCierre, Reporte, TipoConfirmacion


def calcular_vence(visto_en, plazo_horas):
    return visto_en + timedelta(hours=plazo_horas)


def huella_de(identificador):
    """Huella anónima: resumen con clave del identificador aleatorio del dispositivo.

    El identificador lo crea el servidor en una cookie. No se toma ninguna
    característica del navegador ni del teléfono.
    """
    return hmac.new(settings.SECRET_KEY.encode(), identificador.encode(), hashlib.sha256).hexdigest()


@dataclass
class Resultado:
    reporte: Reporte
    duplicado: bool = False  # True si se guardó como confirmación de uno existente
    puntos: int = 0  # los que ganó quien reporta con este aviso
    colaborador: Colaborador | None = None


# ── Puntos: publicar suma ────────────────────────────────────────────────────
def colaborador_de(huella):
    return Colaborador.objects.filter(huella=huella).first() if huella else None


def sumar_puntos(huella, puntos, nombre="", aviso=False):
    """Suma puntos a quien reporta y, si dio un nombre o apodo, lo guarda. Devuelve los puntos sumados."""
    if not huella:
        return 0
    from django.db.models import F

    colaborador, _ = Colaborador.objects.get_or_create(huella=huella)
    nombre = limpiar_nombre(nombre)
    cambios = {"puntos": F("puntos") + puntos}
    if aviso:
        cambios["avisos"] = F("avisos") + 1
    if nombre:
        cambios["nombre"] = nombre
    Colaborador.objects.filter(pk=colaborador.pk).update(**cambios)
    return puntos


def limpiar_nombre(nombre):
    """Un nombre o apodo corto, sin teléfonos ni correos: es lo único que se ve en la tabla."""
    import re

    nombre = re.sub(r"\s+", " ", (nombre or "").strip())[:40]
    if re.search(r"\d{6,}|@|https?:", nombre):
        return ""
    return nombre


def tabla_de_puntos(limite=50):
    return Colaborador.objects.filter(visible=True, puntos__gt=0).exclude(nombre="")[:limite]


def buscar_duplicado(tipo, punto, ahora=None):
    return (
        Reporte.objects.vivos(ahora)
        .filter(tipo=tipo, punto__distance_lte=(punto, D(m=settings.DUPLICADO_METROS)))
        .order_by("-visto_en")
        .first()
    )


# Siete o más dígitos seguidos (con espacios, puntos o guiones): un teléfono o una cédula.
NUMERO_PERSONAL = re.compile(r"\+?\d(?:[\s.\-]?\d){6,}")


def ocultar_numeros(texto):
    """Lo que la gente escribe se publica al instante; los teléfonos y cédulas no."""
    return NUMERO_PERSONAL.sub("[número oculto]", texto or "")


@transaction.atomic
def crear_reporte(*, tipo, punto, huella, fuente=Fuente.VECINO, visto_en=None, ahora=None, vence_en=None, nombre_autor="", **campos):
    """Crea un reporte o, si ya hay uno igual muy cerca, lo confirma.

    Los reportes de vecinos y de WhatsApp entran «por verificar», con la foto y la nota
    ya publicadas (los números largos de la nota se ocultan). Los de coordinación e
    instituciones entran confirmados.
    """
    ahora = ahora or timezone.now()
    visto_en = visto_en or ahora
    existente = buscar_duplicado(tipo, punto, ahora)
    if existente:
        confirmar(existente, TipoConfirmacion.SIGUE_AHI, huella, ahora=ahora)
        puntos = sumar_puntos(huella, settings.PUNTOS["confirmacion"], nombre=nombre_autor)
        foto = campos.get("foto")
        if foto and not existente.foto:
            # La foto nueva completa al reporte original; sigue oculta hasta que la vean.
            existente.foto = foto
            existente.save(update_fields=["foto"])
        return Resultado(existente, duplicado=True, puntos=puntos, colaborador=colaborador_de(huella))

    de_confianza = fuente in (Fuente.COORDINADOR, Fuente.INSTITUCION)
    if not de_confianza and campos.get("nota"):
        campos["nota"] = ocultar_numeros(campos["nota"])
    reporte = Reporte(
        tipo=tipo,
        punto=punto,
        huella=huella,
        fuente=fuente,
        visto_en=visto_en,
        # Coordinación puede fijar el vencimiento (un centro de acopio dura más que su plazo por defecto).
        vence_en=vence_en or calcular_vence(visto_en, tipo.plazo_horas),
        estado=Estado.CONFIRMADO if de_confianza else Estado.POR_VERIFICAR,
        # Todo se publica al instante (decisión de Julián, 23-nov-2026); coordinación oculta o corrige después.
        contenido_visible=True,
        **campos,
    )
    puntos = settings.PUNTOS["reporte"] + (settings.PUNTOS["foto"] if campos.get("foto") else 0)
    sumar_puntos(huella, puntos, nombre=nombre_autor, aviso=True)
    reporte.autor = colaborador_de(huella)
    reporte.save()
    if de_confianza and tipo.clase == "riesgo":
        from .tareas import avisar_reporte  # aquí, para no importar en círculo

        transaction.on_commit(lambda: avisar_reporte.enqueue(reporte.pk))
    return Resultado(reporte, puntos=puntos, colaborador=reporte.autor)


@transaction.atomic
def confirmar(reporte, tipo, huella, ahora=None):
    """Registra «sigue ahí» o «ya bajó» y aplica sus efectos. Devuelve el reporte."""
    ahora = ahora or timezone.now()
    reporte = Reporte.objects.select_for_update().get(pk=reporte.pk)
    if reporte.estado == Estado.CERRADO:
        return reporte
    Confirmacion.objects.create(reporte=reporte, tipo=tipo, huella=huella, fecha=ahora)

    if tipo == TipoConfirmacion.SIGUE_AHI:
        reporte.vence_en = calcular_vence(ahora, reporte.tipo.plazo_horas)
        if reporte.estado == Estado.BAJANDO:
            # Alguien lo volvió a ver: los «ya bajó» anteriores dejan de contar.
            reporte.estado = Estado.CONFIRMADO
        reporte.save(update_fields=["vence_en", "estado"])
        return reporte

    desde = (
        reporte.confirmaciones.filter(tipo=TipoConfirmacion.SIGUE_AHI).values_list("fecha", flat=True).first()
    )
    ya_bajo = reporte.confirmaciones.filter(tipo=TipoConfirmacion.YA_BAJO)
    if desde:
        ya_bajo = ya_bajo.filter(fecha__gt=desde)
    dispositivos = ya_bajo.values("huella").distinct().count()
    if dispositivos >= settings.YA_BAJO_PARA_CERRAR:
        cerrar(reporte, MotivoCierre.YA_BAJO, ahora)
    else:
        reporte.estado = Estado.BAJANDO
        reporte.save(update_fields=["estado"])
    return reporte


def cerrar(reporte, motivo, ahora=None):
    reporte.estado = Estado.CERRADO
    reporte.motivo_cierre = motivo
    reporte.cerrado_en = ahora or timezone.now()
    reporte.save(update_fields=["estado", "motivo_cierre", "cerrado_en"])
    return reporte


def cerrar_vencidos(ahora=None):
    """Marca como cerrados los reportes cuyo plazo pasó. Devuelve cuántos cerró.

    Es solo el trámite: el mapa ya dejó de mostrarlos por el filtro de vivos().
    La hora de cierre que se guarda es la del vencimiento, no la de esta corrida.
    """
    ahora = ahora or timezone.now()
    vencidos = Reporte.objects.exclude(estado=Estado.CERRADO).filter(vence_en__lte=ahora)
    cerrados = 0
    for reporte in vencidos:
        cerrar(reporte, MotivoCierre.VENCIO, reporte.vence_en)
        cerrados += 1
    return cerrados


def gravedad_sugerida(profundidad):
    """Gravedad que el formulario propone según la profundidad. La persona puede cambiarla.

    «Peligro de vida» nunca se propone solo: lo elige quien reporta.
    """
    from .models import Gravedad, Profundidad

    if profundidad in (Profundidad.RODILLA, Profundidad.CINTURA, Profundidad.PUERTA_AUTO):
        return Gravedad.NO_PASAR
    return Gravedad.CUIDADO

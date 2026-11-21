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
from dataclasses import dataclass
from datetime import timedelta

from django.conf import settings
from django.contrib.gis.measure import D
from django.db import transaction
from django.utils import timezone

from .models import Confirmacion, Estado, Fuente, MotivoCierre, Reporte, TipoConfirmacion


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


def buscar_duplicado(tipo, punto, ahora=None):
    return (
        Reporte.objects.vivos(ahora)
        .filter(tipo=tipo, punto__distance_lte=(punto, D(m=settings.DUPLICADO_METROS)))
        .order_by("-visto_en")
        .first()
    )


@transaction.atomic
def crear_reporte(*, tipo, punto, huella, fuente=Fuente.VECINO, visto_en=None, ahora=None, vence_en=None, **campos):
    """Crea un reporte o, si ya hay uno igual muy cerca, lo confirma.

    Los reportes de vecinos y de WhatsApp entran «por verificar» y con la foto y
    la nota ocultas. Los de coordinación e instituciones entran confirmados.
    """
    ahora = ahora or timezone.now()
    visto_en = visto_en or ahora
    existente = buscar_duplicado(tipo, punto, ahora)
    if existente:
        confirmar(existente, TipoConfirmacion.SIGUE_AHI, huella, ahora=ahora)
        foto = campos.get("foto")
        if foto and not existente.foto:
            # La foto nueva completa al reporte original; sigue oculta hasta que la vean.
            existente.foto = foto
            existente.save(update_fields=["foto"])
        return Resultado(existente, duplicado=True)

    de_confianza = fuente in (Fuente.COORDINADOR, Fuente.INSTITUCION)
    reporte = Reporte(
        tipo=tipo,
        punto=punto,
        huella=huella,
        fuente=fuente,
        visto_en=visto_en,
        # Coordinación puede fijar el vencimiento (un centro de acopio dura más que su plazo por defecto).
        vence_en=vence_en or calcular_vence(visto_en, tipo.plazo_horas),
        estado=Estado.CONFIRMADO if de_confianza else Estado.POR_VERIFICAR,
        contenido_visible=de_confianza,
        **campos,
    )
    reporte.save()
    return Resultado(reporte)


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

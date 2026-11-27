# SOS Galápagos · © 2026 Universidad San Francisco de Quito (USFQ) · Autor: Julián Maya <jamaya@usfq.edu.ec>
# Licencia Apache 2.0 (ver LICENSE y NOTICE): puede reutilizarse dando crédito.
"""Reglas de vida del reporte. Aquí está toda la lógica; las vistas y la API solo llaman.

1. vence_en = visto_en + plazo del tipo.
2. «Sigue ahí» renueva el plazo desde ese momento.
3. «Ya bajó»: la primera pasa el reporte a «bajando»; la segunda, desde otro
   dispositivo, lo cierra.
4. Un reporte nuevo del mismo tipo a menos de 50 m de uno vivo se guarda como
   confirmación «sigue ahí» del existente. Uno visto hace más de su plazo, no: entra
   propio y ya vencido (solo a la línea del tiempo).
5. Un reporte cerrado nunca se borra: queda en el archivo.
6. «Ayúdanos a ubicar»: una foto sin lugar pasa al mapa cuando dos personas distintas la
   ubican a menos de 100 m entre sí (en el punto medio de las que coinciden), o en cuanto
   la ubica alguien de coordinación. Ver proponer_ubicacion.

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
from django.db.models import F
from django.utils import timezone

from .models import Colaborador, Confirmacion, Estado, EstadoUbicar, Fuente, MotivoCierre, PorUbicar, Reporte, TipoConfirmacion, TipoRiesgo, Ubicacion


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


def tabla_de_ubicadores(limite=20):
    """Quién ha ubicado más fotos que pasaron al mapa. Solo el nombre o apodo que cada persona eligió."""
    return Colaborador.objects.filter(visible=True, ubicados__gt=0).exclude(nombre="").order_by("-ubicados", "creado_en")[:limite]


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
    # Una foto vieja (que llega tarde de un grupo o que la comunidad ubica días después) no dice
    # que algo «sigue ahí»: si su plazo ya pasó, entra como reporte propio, ya vencido, a la
    # línea del tiempo, y no renueva ningún reporte vivo.
    vieja = calcular_vence(visto_en, tipo.plazo_horas) <= ahora
    existente = None if vieja else buscar_duplicado(tipo, punto, ahora)
    if existente:
        confirmar(existente, TipoConfirmacion.SIGUE_AHI, huella, ahora=min(visto_en, ahora))
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
    if reporte.estado == Estado.CERRADO or reporte.fuente == Fuente.ANTERIOR:
        return reporte  # el historial de la coordinación anterior no se renueva: nunca vuelve al mapa
    Confirmacion.objects.create(reporte=reporte, tipo=tipo, huella=huella, fecha=ahora)

    if tipo == TipoConfirmacion.SIGUE_AHI:
        # Renueva desde que se vio, sin acortar nunca lo que ya tenía.
        reporte.vence_en = max(reporte.vence_en, calcular_vence(ahora, reporte.tipo.plazo_horas))
        if reporte.estado == Estado.BAJANDO:
            # Alguien lo volvió a ver: los «ya bajó» anteriores dejan de contar.
            reporte.estado = Estado.CONFIRMADO
        reporte.save(update_fields=["vence_en", "estado"])
        return reporte

    if reporte.fuente in (Fuente.COORDINADOR, Fuente.INSTITUCION, Fuente.COMUNITARIO):
        # Un refugio o un punto que puso coordinación, una institución o el informe de un barrio (las encañadas
        # obstruidas de Tomás de Berlanga) no lo quitan dos vecinos: su «ya no está» queda registrado y
        # coordinación decide en el admin.
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


# ── «Ayúdanos a ubicar» ──────────────────────────────────────────────────────
@dataclass
class ResultadoUbicar:
    aceptada: bool = False          # la foto pasó al mapa con esta propuesta
    reporte: Reporte | None = None
    puntos: int = 0                 # los que ganó quien propuso, contando el premio si se aceptó
    coinciden: int = 1              # cuántas personas (con esta) la ponen en el mismo lugar
    faltan: int = 0                 # cuántas más hacen falta para que pase al mapa
    error: str = ""


def _centro(puntos):
    from django.contrib.gis.geos import Point

    return Point(sum(p.x for p in puntos) / len(puntos), sum(p.y for p in puntos) / len(puntos), srid=4326)


def _metros(a, b):
    """Distancia aproximada en metros entre dos puntos cercanos (latitud de Galápagos ≈ 0)."""
    import math

    dx = (a.x - b.x) * 111320 * math.cos(math.radians((a.y + b.y) / 2))
    dy = (a.y - b.y) * 110540
    return math.hypot(dx, dy)


@transaction.atomic
def proponer_ubicacion(por_ubicar, punto, huella, *, texto="", nombre="", de_coordinacion=False, ahora=None):
    """Guarda dónde cree una persona que se tomó la foto y, si coincide con otra, la pasa al mapa.

    Regla (preliminar, umbrales en los ajustes):
    - Cada persona (huella) tiene una sola propuesta por foto; si vuelve a marcar, se corrige la suya.
    - Pasa al mapa cuando UBICAR_COINCIDENCIAS personas distintas la ponen a menos de UBICAR_METROS
      de esta propuesta. El punto es el medio de las que coinciden.
    - Una propuesta de coordinación (sesión del admin) la pasa al mapa sola, en su punto.
    - Proponer da PUNTOS["ubicar"]; si la foto pasa al mapa, cada persona que coincidió gana
      además PUNTOS["ubicar_acertada"] y una foto ubicada en la tabla. Así no se ganan puntos
      marcando al azar.
    """
    ahora = ahora or timezone.now()
    item = PorUbicar.objects.select_for_update().get(pk=por_ubicar.pk)
    if item.estado != EstadoUbicar.PENDIENTE:
        return ResultadoUbicar(error="Esta foto ya no espera ubicación. Gracias.")
    if not huella:
        return ResultadoUbicar(error="No pudimos reconocer este teléfono. Recarga la página.")
    texto = ocultar_numeros((texto or "").strip())[:280]
    propuesta, nueva = Ubicacion.objects.update_or_create(
        por_ubicar=item, huella=huella, defaults={"punto": punto, "texto": texto, "de_coordinacion": de_coordinacion}
    )
    puntos = sumar_puntos(huella, settings.PUNTOS["ubicar"] if nueva else 0, nombre=nombre)
    propuesta.autor = colaborador_de(huella)
    propuesta.save(update_fields=["autor"])

    cerca = [u for u in item.ubicaciones.all() if _metros(u.punto, punto) <= settings.UBICAR_METROS]
    personas = {u.huella for u in cerca}
    if not de_coordinacion and len(personas) < settings.UBICAR_COINCIDENCIAS:
        return ResultadoUbicar(puntos=puntos, coinciden=len(personas), faltan=settings.UBICAR_COINCIDENCIAS - len(personas))

    acertadas = [propuesta] if de_coordinacion else cerca
    reporte = _aceptar(item, acertadas, punto if de_coordinacion else _centro([u.punto for u in cerca]), ahora)
    premio = settings.PUNTOS["ubicar_acertada"]
    for u in acertadas:
        sumar_puntos(u.huella, premio)
        Colaborador.objects.filter(huella=u.huella).update(ubicados=F("ubicados") + 1)
    Ubicacion.objects.filter(pk__in=[u.pk for u in acertadas]).update(acertada=True)
    return ResultadoUbicar(aceptada=True, reporte=reporte, puntos=puntos + premio, coinciden=len(personas))


def _aceptar(item, acertadas, punto, ahora):
    """Convierte la foto ubicada en un reporte por el camino de siempre (duplicados incluidos)."""
    from django.core.files.base import ContentFile

    from zonas.models import zona_de

    tipo = item.tipo or TipoRiesgo.objects.filter(codigo=settings.UBICAR_TIPO_POR_DEFECTO).first()
    precision = max([round(_metros(u.punto, punto)) for u in acertadas] + [10])
    foto = None
    if item.foto:
        item.foto.open("rb")
        foto = ContentFile(item.foto.read(), name="foto.jpg")
        item.foto.close()
    resultado = crear_reporte(
        tipo=tipo,
        punto=punto,
        huella=item.huella or f"ubicar:{item.id_publico}",
        fuente=Fuente.WHATSAPP,
        visto_en=item.visto_en,
        ahora=ahora,
        foto=foto,
        nota=item.texto,
        precision_m=precision,
        zona=zona_de(punto),
    )
    item.estado, item.reporte = EstadoUbicar.UBICADO, resultado.reporte
    item.save(update_fields=["estado", "reporte"])
    return resultado.reporte


def aprobar_por_ubicar(item):
    """Coordinación revisó la foto y puede verse: pasa a la lista o, si ya tenía punto, a su reporte."""
    if item.estado != EstadoUbicar.REVISION:
        return item
    if item.reporte_id:
        reporte = item.reporte
        if item.foto and not reporte.foto:
            from django.core.files.base import ContentFile

            item.foto.open("rb")
            reporte.foto.save("foto.jpg", ContentFile(item.foto.read()), save=False)
            item.foto.close()
            reporte.save(update_fields=["foto"])
        item.estado = EstadoUbicar.UBICADO
    else:
        item.estado = EstadoUbicar.PENDIENTE
    item.motivo_revision = ""
    item.save(update_fields=["estado", "motivo_revision"])
    return item

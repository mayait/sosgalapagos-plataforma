# SOS Galápagos · © 2026 Universidad San Francisco de Quito (USFQ) · Autor: Julián Maya <jamaya@usfq.edu.ec>
# Licencia Apache 2.0 (ver LICENSE y NOTICE): puede reutilizarse dando crédito.
"""Modelos de los reportes de riesgo.

Un reporte es un lugar de peligro visto en una fecha. Vive un plazo que depende
de su tipo y se retira solo. Nunca se borra: al cerrarse pasa al archivo del evento.
Las reglas (plazos, duplicados, confirmaciones) están en reportes/reglas.py.
"""
import secrets
import uuid

from django.contrib.gis.db import models
from django.utils import timezone

ALFABETO_ID = "23456789abcdefghjkmnpqrstuvwxyz"  # sin 0, 1, i, l, o: se dictan sin confusión


def nuevo_id_publico():
    return "".join(secrets.choice(ALFABETO_ID) for _ in range(8))


DOCUMENTO_MAX_BYTES = 25 * 1024 * 1024


class Clase(models.TextChoices):
    # No todo lo que se avisa es un peligro: también hay cosas buenas y lugares donde ayudar.
    RIESGO = "riesgo", "Un peligro"
    BUENO = "bueno", "Algo bueno"
    AYUDA = "ayuda", "Dónde donar o colaborar"
    # Lo que la gente vio y sirve para afinar el mapa de riesgo: «aquí no se inundó», «aquí sí», «esto siempre se inunda».
    OBSERVA = "observa", "Ayúdanos a mejorar el mapa"


class TipoRiesgo(models.Model):
    """Tipo de aviso. Nació para los riesgos y conserva el nombre; hoy también cubre lo bueno y la ayuda."""

    codigo = models.SlugField("código", max_length=30, unique=True)
    clase = models.CharField(max_length=8, choices=Clase, default=Clase.RIESGO)
    nombre = models.CharField(max_length=60)
    icono = models.CharField(max_length=30, help_text="Nombre del icono en estaticos/mapa/iconos.svg")
    plazo_horas = models.PositiveIntegerField("plazo de vida (horas)")
    orden = models.PositiveSmallIntegerField(default=0)
    activo = models.BooleanField(default=True)
    # Un lugar que recibe donaciones necesita un teléfono al que llamar antes de ir.
    pide_contacto = models.BooleanField("pide un teléfono de contacto", default=False)
    # Un daño en infraestructura dura lo que tarde el arreglo: quien avisa dice cuánto cree que estará así.
    pide_duracion = models.BooleanField("pregunta cuánto va a durar", default=False)

    class Meta:
        verbose_name = "tipo de aviso"
        verbose_name_plural = "tipos de aviso"
        ordering = ["orden", "nombre"]

    def __str__(self):
        return self.nombre


class Gravedad(models.TextChoices):
    CUIDADO = "cuidado", "Pasar con cuidado"
    NO_PASAR = "no_pasar", "No pasar"
    PELIGRO_VIDA = "peligro_vida", "Peligro de vida"


class Profundidad(models.TextChoices):
    TOBILLO = "tobillo", "Al tobillo"
    RODILLA = "rodilla", "A la rodilla"
    CINTURA = "cintura", "A la cintura"
    PUERTA_AUTO = "puerta_auto", "A la puerta de un auto"
    SIN_DATO = "sin_dato", "Sin dato"


class Estado(models.TextChoices):
    POR_VERIFICAR = "por_verificar", "Por verificar"
    CONFIRMADO = "confirmado", "Confirmado"
    BAJANDO = "bajando", "Bajando"
    CERRADO = "cerrado", "Cerrado"


class Fuente(models.TextChoices):
    VECINO = "vecino", "Vecino"
    COORDINADOR = "coordinador", "Coordinador"
    INSTITUCION = "institucion", "Institución"
    WHATSAPP = "whatsapp", "WhatsApp"
    # Un documento público de la comunidad (el informe de campo de un barrio): ni coordinación ni institución.
    COMUNITARIO = "comunitario", "Informe comunitario"
    # Historial de la plataforma de coordinación anterior (ResponseGrid, 1 al 4 de noviembre de 2026).
    # Entra cerrado y nunca sale en el mapa: solo en la línea del tiempo (ver ReporteQuerySet.del_mapa).
    ANTERIOR = "anterior", "Coordinación anterior"


class MotivoCierre(models.TextChoices):
    VENCIO = "vencio", "Venció el plazo"
    YA_BAJO = "ya_bajo", "Dos avisos de que ya bajó"
    COORDINADOR = "coordinador", "Lo cerró coordinación"
    FUSIONADO = "fusionado", "Se fusionó con otro reporte"
    HISTORIAL = "historial", "Historial de la coordinación anterior"


class Colaborador(models.Model):
    """Quien reporta y quiere sumar puntos. Solo guarda el nombre o apodo que la persona eligió.

    Se le reconoce por la huella anónima de su teléfono (la del formulario) o por el resumen
    con clave de su número de WhatsApp. Nunca se guarda el número.
    """

    nombre = models.CharField(max_length=40, blank=True)
    huella = models.CharField(max_length=64, unique=True, editable=False)
    puntos = models.PositiveIntegerField(default=0, db_index=True)
    avisos = models.PositiveIntegerField("avisos publicados", default=0)
    # Coordinación puede ocultar de la tabla un nombre impropio o el de un menor.
    visible = models.BooleanField("aparece en la tabla de puntos", default=True)
    creado_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "colaborador"
        verbose_name_plural = "colaboradores"
        ordering = ["-puntos", "creado_en"]

    def __str__(self):
        return f"{self.nombre or 'Sin nombre'} · {self.puntos} puntos"


class SuscripcionPush(models.Model):
    """Un navegador o una app instalada que pidió recibir avisos."""

    direccion = models.TextField("dirección de entrega", unique=True)
    p256dh = models.CharField(max_length=200)
    auth = models.CharField(max_length=80)
    huella = models.CharField(max_length=64, blank=True, editable=False)
    creada_en = models.DateTimeField(auto_now_add=True)
    ultimo_envio = models.DateTimeField(null=True, blank=True)
    # De qué quiere enterarse y de qué islas. Sin islas elegidas, de todas.
    temas = models.JSONField(default=list, blank=True)
    zonas = models.JSONField(default=list, blank=True)
    # De noche (21:00 a 06:00) no se manda nada, salvo a quien lo pide aquí y solo lo urgente.
    de_noche = models.BooleanField("recibir lo urgente también de noche", default=False)

    class Meta:
        verbose_name = "suscripción a avisos"
        verbose_name_plural = "suscripciones a avisos"

    def __str__(self):
        return f"Suscripción del {self.creada_en:%d-%m %H:%M}"


class OrigenAgua(models.TextChoices):
    # Lo pide el issue 80 del repo de datos para validar los modelos.
    CANADA = "canada", "Cañada o quebrada que se desborda"
    CALLE = "calle", "Calle que se encharca"
    ALCANTARILLADO = "alcantarillado", "Agua que sale del alcantarillado"


class ReporteQuerySet(models.QuerySet):
    def vivos(self, ahora=None):
        """Los que se ven en el mapa: no cerrados y con el plazo sin vencer.

        El filtro por vence_en hace que un reporte vencido desaparezca aunque la
        tarea que lo marca como cerrado no haya corrido.
        """
        ahora = ahora or timezone.now()
        return self.del_mapa().exclude(estado=Estado.CERRADO).filter(vence_en__gt=ahora)

    def del_mapa(self):
        """Lo que puede salir en el mapa. El historial de la coordinación anterior no: solo va en la línea del tiempo."""
        return self.exclude(fuente=Fuente.ANTERIOR)

    def historial(self):
        """El historial de la coordinación anterior (ResponseGrid), para la línea del tiempo."""
        return self.filter(fuente=Fuente.ANTERIOR)


class Reporte(models.Model):
    id_publico = models.CharField(max_length=8, unique=True, default=nuevo_id_publico, editable=False)
    tipo = models.ForeignKey(TipoRiesgo, on_delete=models.PROTECT, related_name="reportes")
    gravedad = models.CharField(max_length=15, choices=Gravedad, default=Gravedad.CUIDADO)
    profundidad = models.CharField(max_length=15, choices=Profundidad, default=Profundidad.SIN_DATO)
    punto = models.PointField(srid=4326)
    tramo = models.LineStringField(srid=4326, null=True, blank=True, help_text="Tramo de vía. Solo coordinación.")
    precision_m = models.PositiveIntegerField("precisión del GPS (m)", null=True, blank=True)

    visto_en = models.DateTimeField(default=timezone.now, db_index=True)
    vence_en = models.DateTimeField(db_index=True, editable=False)
    estado = models.CharField(max_length=15, choices=Estado, default=Estado.POR_VERIFICAR, db_index=True)
    fuente = models.CharField(max_length=12, choices=Fuente, default=Fuente.VECINO)

    # Nombre propio del aviso («Centro de acopio USFQ San Cristóbal»). Si falta, se usa el del tipo.
    titulo = models.CharField("título", max_length=80, blank=True)
    foto = models.ImageField(upload_to="reportes/%Y/%m/", null=True, blank=True)
    nota = models.CharField(max_length=280, blank=True)
    # La foto y la nota de un vecino no se publican hasta que coordinación las ve:
    # así un nombre, una cédula o la cara de un menor no llegan al mapa sin revisión.
    contenido_visible = models.BooleanField("foto y nota públicas", default=True,
                                            help_text="Todo se publica al instante. Desmárcalo para ocultar la foto y la nota.")
    # Teléfono de un lugar que recibe donaciones o de una institución. Se publica con la nota,
    # al instante; coordinación lo oculta si no corresponde. Nunca el teléfono de quien reporta.
    contacto = models.CharField("teléfono de contacto del lugar", max_length=40, blank=True)
    autor = models.ForeignKey("Colaborador", null=True, blank=True, on_delete=models.SET_NULL, related_name="reportes")
    zona = models.ForeignKey("zonas.Zona", null=True, blank=True, on_delete=models.SET_NULL, related_name="reportes")

    cerrado_en = models.DateTimeField(null=True, blank=True)
    motivo_cierre = models.CharField(max_length=12, choices=MotivoCierre, blank=True)
    origen_agua = models.CharField(max_length=15, choices=OrigenAgua, blank=True)
    fusionado_en = models.ForeignKey("self", null=True, blank=True, on_delete=models.SET_NULL, related_name="fusionados")
    creado_por_llave = models.ForeignKey("api.LlaveApi", null=True, blank=True, on_delete=models.SET_NULL)
    huella = models.CharField(max_length=64, blank=True, editable=False, help_text="Huella anónima del dispositivo que lo creó")
    # Identificador en otro sistema («responsegrid:punto:<uuid>»): permite volver a importar sin duplicar.
    id_externo = models.CharField("identificador de origen", max_length=80, null=True, blank=True, editable=False)
    creado_en = models.DateTimeField(auto_now_add=True)

    objects = ReporteQuerySet.as_manager()

    class Meta:
        ordering = ["-visto_en"]
        indexes = [models.Index(fields=["estado", "vence_en"])]
        constraints = [models.UniqueConstraint(fields=["id_externo"], condition=models.Q(id_externo__isnull=False), name="reporte_id_externo_unico")]

    def __str__(self):
        return f"{self.titulo or self.tipo} · {self.id_publico}"

    @property
    def nombre(self):
        return self.titulo or self.tipo.nombre

    def save(self, *args, **kwargs):
        if self.vence_en is None:
            from .reglas import calcular_vence

            self.vence_en = calcular_vence(self.visto_en, self.tipo.plazo_horas)
        super().save(*args, **kwargs)


class FotoReporte(models.Model):
    """Fotos adicionales de un aviso. La primera sigue en Reporte.foto. Se guardan sin metadatos."""

    reporte = models.ForeignKey(Reporte, on_delete=models.CASCADE, related_name="fotos_extra")
    foto = models.ImageField(upload_to="reportes/%Y/%m/")
    pie = models.CharField(max_length=140, blank=True)
    orden = models.PositiveSmallIntegerField(default=0)

    class Meta:
        verbose_name = "foto adicional"
        verbose_name_plural = "fotos adicionales"
        ordering = ["orden", "id"]


def ruta_documento(instancia, nombre):
    # Nombre al azar: el archivo nunca se sirve por /riesgos/medios/, pero tampoco debe adivinarse.
    return f"documentos/{instancia.reporte.id_publico}/{uuid.uuid4().hex}.pdf"


def validar_pdf(archivo):
    from django.core.exceptions import ValidationError

    if archivo.size > DOCUMENTO_MAX_BYTES:
        raise ValidationError(f"El PDF pesa más de {DOCUMENTO_MAX_BYTES // (1024 * 1024)} MB.")
    inicio = archivo.read(5)
    archivo.seek(0)
    if not archivo.name.lower().endswith(".pdf") or inicio != b"%PDF-":
        raise ValidationError("Solo se aceptan documentos PDF.")


class DocumentoReporte(models.Model):
    """Un documento que respalda un aviso: un informe, un oficio. Solo lo sube coordinación desde el admin.

    Es privado salvo que coordinación lo marque público: muchos traen nombres, cédulas o teléfonos.
    Se guarda en el volumen de medios (con respaldo diario) bajo documentos/, que /riesgos/medios/ no
    sirve: solo se baja por /riesgos/documento/<id>/, que exige sesión de coordinación si es privado.
    Nunca se borra.
    """

    reporte = models.ForeignKey(Reporte, on_delete=models.PROTECT, related_name="documentos")
    archivo = models.FileField(upload_to=ruta_documento, validators=[validar_pdf], help_text="PDF, hasta 25 MB.")
    titulo = models.CharField("título", max_length=140)
    fecha = models.DateField("fecha del documento", null=True, blank=True)
    publico = models.BooleanField("se puede ver en el mapa", default=False,
                                  help_text="Márcalo solo si el PDF no trae nombres de personas afectadas, cédulas ni teléfonos.")
    subido_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "documento"
        verbose_name_plural = "documentos"
        ordering = ["fecha", "id"]

    def __str__(self):
        return self.titulo


class TipoConfirmacion(models.TextChoices):
    SIGUE_AHI = "sigue_ahi", "Sigue ahí"
    YA_BAJO = "ya_bajo", "Ya bajó"


class Confirmacion(models.Model):
    reporte = models.ForeignKey(Reporte, on_delete=models.CASCADE, related_name="confirmaciones")
    tipo = models.CharField(max_length=10, choices=TipoConfirmacion)
    fecha = models.DateTimeField(default=timezone.now)
    huella = models.CharField(max_length=64, help_text="Huella anónima del dispositivo")

    class Meta:
        verbose_name = "confirmación"
        verbose_name_plural = "confirmaciones"
        ordering = ["-fecha"]

    def __str__(self):
        return f"{self.get_tipo_display()} · {self.reporte.id_publico}"


class ClaseSuceso(models.TextChoices):
    OFICIAL = "oficial", "Informe o comunicado oficial"
    NOTICIA = "noticia", "Noticia"
    INFORME = "informe", "Informe o mapa de SOS Galápagos"
    NOTA = "nota", "Nota de coordinación"
    # Un documento de la comunidad (directiva de un barrio, comité): no es oficial ni de SOS Galápagos.
    BARRIO = "barrio", "Informe comunitario"


class ZonaGrande(models.TextChoices):
    """Las zonas con que se filtra la línea del tiempo. Vacío: todo Galápagos."""

    SANTA_CRUZ = "sc", "Santa Cruz (Puerto Ayora)"
    SANTA_CRUZ_ALTA = "sc-alta", "Santa Cruz, parte alta"
    SAN_CRISTOBAL = "sx", "San Cristóbal (Puerto Baquerizo)"
    SAN_CRISTOBAL_ALTA = "sx-alta", "San Cristóbal, parte alta"
    ISABELA = "is", "Isabela"
    ISLA_SANTA_CRUZ = "santa-cruz", "Toda Santa Cruz"
    ISLA_SAN_CRISTOBAL = "san-cristobal", "Todo San Cristóbal"


class Institucion(models.TextChoices):
    """Quién firma un documento oficial. Sirve para mostrar «el último de cada institución» en la portada."""

    INAMHI = "inamhi", "INAMHI"
    SNGR = "sngr", "Secretaría Nacional de Gestión de Riesgos"
    INOCAR = "inocar", "INOCAR"
    GAD_SANTA_CRUZ = "gad-santa-cruz", "GAD de Santa Cruz"
    GAD_SAN_CRISTOBAL = "gad-san-cristobal", "GAD de San Cristóbal"
    GAD_ISABELA = "gad-isabela", "GAD de Isabela"
    COE = "coe", "COE"
    CGREG = "cgreg", "Consejo de Gobierno de Galápagos"
    OTRA = "otra", "Otra institución"


def ruta_oficial(instancia, nombre):
    return f"oficiales/{timezone.now():%Y-%m}/{uuid.uuid4().hex}.pdf"


class Suceso(models.Model):
    """Algo que pasó en la emergencia y debe quedar en la línea del tiempo, aunque no tenga un punto en el mapa.

    Un comunicado oficial, una noticia, un informe publicado, una decisión de coordinación. Se
    escribe a mano en el admin. Los avisos que se mandan a los teléfonos y los boletines oficiales
    que se leen solos (app `clima`) entran a la línea del tiempo sin pasar por aquí.

    No lleva nombres de personas afectadas, cédulas ni teléfonos personales.
    """

    clase = models.CharField(max_length=8, choices=ClaseSuceso, default=ClaseSuceso.NOTA)
    titulo = models.CharField("título", max_length=140)
    texto = models.TextField(blank=True, help_text="Qué pasó, en pocas frases. Sin nombres de personas afectadas.")
    fuente = models.CharField(max_length=80, blank=True, help_text="Quién lo dice: INAMHI, COE cantonal, el nombre del medio…")
    enlace = models.URLField(max_length=400, blank=True, help_text="Al documento o a la noticia original.")
    # Un documento oficial lleva su institución (para la portada) y, si no está publicado en internet, el PDF.
    institucion = models.CharField("institución", max_length=20, choices=Institucion, blank=True, help_text="Solo para documentos oficiales.")
    archivo = models.FileField("PDF del documento", upload_to=ruta_oficial, validators=[validar_pdf], blank=True,
                               help_text="Si el documento no está en internet. Es público: no subas uno con nombres de personas afectadas, cédulas ni teléfonos.")
    ocurrido = models.DateTimeField("cuándo", default=timezone.now, db_index=True)
    # Lo que dura: un cierre de vía anunciado, una suspensión de clases. Vacío: un hecho puntual.
    hasta = models.DateTimeField("vigente hasta", null=True, blank=True)
    zona = models.CharField(max_length=14, choices=ZonaGrande, blank=True, help_text="Vacío: todo Galápagos.")
    visible = models.BooleanField("se ve en la línea del tiempo", default=True)
    creado_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "suceso de la línea del tiempo"
        verbose_name_plural = "sucesos de la línea del tiempo"
        ordering = ["-ocurrido"]

    def __str__(self):
        return f"{self.get_clase_display()} · {self.titulo}"

    @property
    def destino(self):
        """Adónde lleva: al original en internet o, si se subió el PDF, a su descarga."""
        if self.enlace:
            return self.enlace
        return f"/riesgos/oficial/{self.pk}/" if self.archivo else ""

# SOS Galápagos · © 2026 Universidad San Francisco de Quito (USFQ) · Autor: Julián Maya <jamaya@usfq.edu.ec>
# Todos los derechos reservados. Usar, copiar, modificar o derivar de este código requiere permiso escrito del autor (ver LICENSE).
"""Clima: todo lo que se mide, se pronostica y se avisa, en la misma base que el mapa (PostgreSQL).

Las fuentes (clima/fuentes/) escriben aquí directamente; no hay otra base ni archivos intermedios.
Las horas se guardan en UTC. El día de Galápagos es UTC−6.
"""
from django.contrib.gis.db import models


class Estacion(models.Model):
    """Una estación, un mareógrafo o una zona vista por satélite."""

    fuente = models.CharField(max_length=24)   # ierse, gsc, inamhi, ioc, ambient, goes…
    codigo = models.CharField("código", max_length=60)
    nombre = models.CharField(max_length=120, blank=True)
    isla = models.CharField(max_length=40, blank=True)
    punto = models.PointField(srid=4326, null=True, blank=True)
    altitud_m = models.FloatField(null=True, blank=True)
    operador = models.CharField(max_length=120, blank=True)
    primera = models.DateTimeField("primera medición", null=True, blank=True)
    ultima = models.DateTimeField("última medición", null=True, blank=True, db_index=True)

    class Meta:
        verbose_name = "estación"
        verbose_name_plural = "estaciones"
        ordering = ["fuente", "nombre"]
        constraints = [models.UniqueConstraint(fields=["fuente", "codigo"], name="estacion_unica")]

    def __str__(self):
        return f"{self.nombre or self.codigo} ({self.fuente})"

    @property
    def clave(self):
        return f"{self.fuente}/{self.codigo}"


class Observacion(models.Model):
    """Una medición tal como llega (cada 5 minutos, por lo general)."""

    estacion = models.ForeignKey(Estacion, on_delete=models.CASCADE, related_name="observaciones")
    variable = models.CharField(max_length=28)  # lluvia_mm, temp_c, hr_pct, presion_hpa, viento_ms, nivel_mar_m…
    ts = models.DateTimeField()
    valor = models.FloatField(null=True)

    class Meta:
        verbose_name = "observación"
        verbose_name_plural = "observaciones"
        constraints = [models.UniqueConstraint(fields=["estacion", "variable", "ts"], name="observacion_unica")]
        indexes = [models.Index(fields=["ts"], name="observacion_ts")]


class Horaria(models.Model):
    """Resumen por hora de una variable: se mantiene al día con cada sincronización.

    Es lo que se consulta casi siempre (gráficos, acumulados, niveles): así no hay que
    recorrer las mediciones de cinco minutos cada vez.
    """

    estacion = models.ForeignKey(Estacion, on_delete=models.CASCADE, related_name="horarias")
    variable = models.CharField(max_length=28)
    hora = models.DateTimeField()               # inicio de la hora, UTC
    suma = models.FloatField(null=True)         # para la lluvia
    media = models.FloatField(null=True)        # para lo demás
    maximo = models.FloatField(null=True)
    n = models.PositiveSmallIntegerField(default=0)  # mediciones que entraron

    class Meta:
        verbose_name = "resumen por hora"
        verbose_name_plural = "resúmenes por hora"
        constraints = [models.UniqueConstraint(fields=["estacion", "variable", "hora"], name="horaria_unica")]
        indexes = [models.Index(fields=["hora"], name="horaria_hora")]


class Corrida(models.Model):
    """Cada vez que se consultó una fuente: si respondió, cuánto trajo y cuánto tardó.

    No es solo un registro: la regla del nivel de lluvia distingue «la estación está
    callada» de «no pudimos preguntarle» mirando estas filas.
    """

    fuente = models.CharField(max_length=24)
    ts = models.DateTimeField()
    ok = models.BooleanField(default=False)
    registros = models.IntegerField(null=True)
    segundos = models.FloatField(null=True)
    error = models.TextField(blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["fuente", "ts"], name="corrida_unica")]
        ordering = ["-ts"]


class EstacionDanada(models.Model):
    """Un sensor con errores, marcado a mano. Sus datos se siguen guardando, pero desde «desde»
    no se usan en los cálculos ni se publican. Para reactivarlo, se pone la fecha «hasta».
    """

    estacion = models.ForeignKey(Estacion, on_delete=models.CASCADE, related_name="danos")
    variable = models.CharField(max_length=28, default="lluvia_mm")
    desde = models.DateTimeField()
    hasta = models.DateTimeField(null=True, blank=True)
    motivo = models.TextField(blank=True)

    class Meta:
        verbose_name = "sensor dañado"
        verbose_name_plural = "sensores dañados"

    def __str__(self):
        return f"{self.estacion} · {self.variable} desde {self.desde:%d-%m-%Y}"


class PronosticoCorrida(models.Model):
    """Una corrida de un modelo meteorológico, resumida por punto. Es la historia de lo que dijo cada modelo.

    `datos` es {punto: {dias: {fecha: mm}, …}}: en un determinista, un valor por día (y el detalle por
    hora del modelo de 9 km); en un conjunto, la lista con el valor de cada miembro, por día y por
    bloque de 6 horas.
    """

    modelo = models.CharField(max_length=40)
    tipo = models.CharField(max_length=12)                  # determinista o conjunto
    referencia = models.DateTimeField()                     # la hora de la corrida; si no se conoce, el bloque de 6 h en que se recibió
    corrida = models.DateTimeField(null=True, blank=True)   # inicio de la corrida, si el proveedor lo informa
    disponible = models.DateTimeField(null=True, blank=True)
    recibido = models.DateTimeField()
    datos = models.JSONField(default=dict)

    class Meta:
        verbose_name = "corrida de un modelo"
        verbose_name_plural = "corridas de los modelos"
        constraints = [models.UniqueConstraint(fields=["modelo", "tipo", "referencia"], name="pronostico_corrida_unica")]
        indexes = [models.Index(fields=["tipo", "modelo", "-recibido"], name="pronostico_corrida_ultima")]
        ordering = ["-recibido"]

    def __str__(self):
        return f"{self.modelo} · {self.referencia:%d-%m %H:%M}"


class PronosticoModelo(models.Model):
    """Lo que un modelo meteorológico dijo que llovería en un punto un día, y cuándo lo dijo.

    Solo se guarda una fila cuando el valor cambia respecto de la anterior: los modelos se
    actualizan cada 6 o 12 horas, aunque se consulten cada hora.
    """

    punto = models.CharField(max_length=40)
    modelo = models.CharField(max_length=40)
    obtenido = models.DateTimeField()           # cuándo se bajó
    fecha = models.DateField()                  # día de Galápagos pronosticado
    anticipacion = models.SmallIntegerField()   # días entre que se obtuvo y el día pronosticado
    mm = models.FloatField(null=True)           # lluvia del día (en un conjunto, la mediana de los miembros)
    miembros = models.PositiveSmallIntegerField(default=1)
    prob20 = models.FloatField(null=True)       # en un conjunto: fracción de miembros con 20 mm o más
    p90 = models.FloatField(null=True)          # en un conjunto: percentil 90 de los miembros

    class Meta:
        constraints = [models.UniqueConstraint(fields=["punto", "modelo", "obtenido", "fecha"], name="pronostico_modelo_unico")]
        indexes = [models.Index(fields=["punto", "fecha"], name="pronostico_modelo_dia")]


class PronosticoEmitido(models.Model):
    """La probabilidad de lluvia fuerte que se publicó para un punto y un día. Es lo que se verifica."""

    punto = models.CharField(max_length=40)
    emitido = models.DateTimeField()
    fecha = models.DateField()
    anticipacion = models.SmallIntegerField()
    prob10 = models.FloatField(null=True)
    prob20 = models.FloatField(null=True)
    prob50 = models.FloatField(null=True)
    consenso = models.FloatField(null=True)
    n_modelos = models.PositiveSmallIntegerField(default=0)
    mediana_mm = models.FloatField(null=True)
    nivel = models.CharField(max_length=20, blank=True)
    calibrado = models.BooleanField(default=False)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["punto", "emitido", "fecha"], name="pronostico_emitido_unico")]
        indexes = [models.Index(fields=["punto", "fecha"], name="pronostico_emitido_dia")]


class Calibracion(models.Model):
    """Una recalibración del pronóstico con lo medido en las últimas semanas, y cómo validó.

    Convierte los milímetros que dan los modelos en una probabilidad de lluvia fuerte.
    No reemplaza al pronóstico publicado: se guarda al lado para compararlos.
    """

    creada = models.DateTimeField(auto_now_add=True)
    grupo = models.CharField(max_length=10)            # alta o costa
    plazo = models.CharField(max_length=6)             # «0-1», «2-3» o «4-5» días de anticipación
    a = models.FloatField()
    b = models.FloatField()
    dias = models.PositiveIntegerField()               # pares pronóstico-observación usados
    eventos = models.PositiveIntegerField()            # de ellos, con lluvia fuerte
    brier = models.FloatField(null=True)               # validación dejando fuera un día cada vez
    brier_base = models.FloatField(null=True)          # el de decir siempre la frecuencia observada
    habilidad = models.FloatField(null=True)           # 1 − brier / brier_base
    desde = models.DateField()
    hasta = models.DateField()

    class Meta:
        verbose_name = "calibración"
        verbose_name_plural = "calibraciones"
        ordering = ["-creada", "grupo", "plazo"]


# ── Mar ──────────────────────────────────────────────────────────────────────
class MareaExtremo(models.Model):
    """Una pleamar o una bajamar predicha para un puerto, según una fuente."""

    puerto = models.CharField(max_length=20)    # santa-cruz, san-cristobal, isabela, baltra
    ts = models.DateTimeField()
    tipo = models.CharField(max_length=1)       # P (pleamar) o B (bajamar)
    altura_m = models.FloatField()
    fuente = models.CharField(max_length=12)    # inocar (tabla oficial) o stormglass
    datum = models.CharField(max_length=8)      # MLWS o MSL: las alturas de fuentes distintas no se comparan tal cual

    class Meta:
        constraints = [models.UniqueConstraint(fields=["puerto", "fuente", "ts"], name="marea_unica")]
        indexes = [models.Index(fields=["puerto", "ts"], name="marea_puerto_ts")]
        ordering = ["ts"]


class MarHora(models.Model):
    """Estado del mar pronosticado para un puerto según un modelo: oleaje, mar de fondo, viento y nivel.

    Stormglass da un valor por hora; Open-Meteo, el nivel cada 15 minutos. Son modelos, no mediciones.
    """

    puerto = models.CharField(max_length=20)
    fuente = models.CharField(max_length=12, default="stormglass")  # stormglass u openmeteo
    hora = models.DateTimeField()
    ola_m = models.FloatField(null=True)
    fondo_m = models.FloatField("mar de fondo (m)", null=True)
    periodo_s = models.FloatField(null=True)
    direccion = models.FloatField("dirección del mar de fondo (°)", null=True)
    viento_ms = models.FloatField(null=True)
    racha_ms = models.FloatField(null=True)
    nivel_m = models.FloatField("nivel del mar (m, MSL)", null=True)
    agua_c = models.FloatField("temperatura del agua (°C)", null=True)
    lluvia_mm = models.FloatField(null=True)
    obtenido = models.DateTimeField()

    class Meta:
        constraints = [models.UniqueConstraint(fields=["puerto", "fuente", "hora"], name="mar_hora_unica")]
        ordering = ["hora"]


# ── Lo que dicen las instituciones ───────────────────────────────────────────
class Boletin(models.Model):
    """Una advertencia o un boletín oficial (INAMHI, INOCAR), con lo que se extrajo de él.

    El documento original suele ser una imagen: un modelo de lenguaje lo lee y saca la
    vigencia, el nivel y lo que dice de Galápagos. El resumen nunca reemplaza al original:
    siempre va el enlace al documento oficial.
    """

    fuente = models.CharField(max_length=12)    # inamhi, inocar
    tipo = models.CharField(max_length=20)      # advertencia, oleaje, erfen
    huella = models.CharField(max_length=64, unique=True)  # del documento: uno nuevo es un boletín nuevo
    numero = models.CharField("número", max_length=30, blank=True)
    titulo = models.CharField("título", max_length=200, blank=True)
    emitido = models.DateTimeField(null=True, blank=True)
    vigente_desde = models.DateTimeField(null=True, blank=True)
    vigente_hasta = models.DateTimeField(null=True, blank=True)
    afecta_galapagos = models.BooleanField(default=False)
    nivel = models.CharField(max_length=80, blank=True)     # el que el documento da para Galápagos, si lo da
    resumen = models.TextField(blank=True)
    datos = models.JSONField(default=dict, blank=True)      # lo demás que se extrajo (olas, período, zonas…)
    enlace = models.URLField(max_length=400, blank=True)    # al documento oficial
    extraido_con = models.CharField(max_length=60, blank=True)
    revisado = models.BooleanField("revisado por una persona", default=False)
    visto_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "boletín oficial"
        verbose_name_plural = "boletines oficiales"
        ordering = ["-visto_en"]

    def __str__(self):
        return f"{self.fuente.upper()} · {self.titulo or self.tipo} {self.numero}"


class PronosticoOficial(models.Model):
    """El pronóstico del INAMHI para una isla: el del día y la lluvia de las próximas horas."""

    isla = models.CharField(max_length=20)      # santa-cruz, san-cristobal, isabela
    fecha = models.DateField()
    obtenido = models.DateTimeField()
    minima_c = models.FloatField(null=True)
    maxima_c = models.FloatField(null=True)
    periodos = models.JSONField(default=list)   # [{periodo, condicion}]
    lluvia_horas = models.JSONField(default=list)  # lo que el INAMHI espera hora a hora

    class Meta:
        constraints = [models.UniqueConstraint(fields=["isla", "fecha"], name="oficial_unico")]
        ordering = ["-fecha"]


class AvisoEnviado(models.Model):
    """Un aviso para los teléfonos. La clave impide repetir el mismo.

    De noche (21:00 a 06:00, hora de Galápagos) los avisos no se mandan: quedan retenidos y a
    las 06:00 sale un solo resumen. Todos, enviados o retenidos, se ven en la línea del tiempo.
    """

    clave = models.CharField(max_length=120, unique=True)
    tema = models.CharField(max_length=12)
    zona = models.CharField(max_length=20, blank=True)
    titulo = models.CharField("título", max_length=120)
    cuerpo = models.CharField(max_length=300)
    enlace = models.CharField(max_length=200)
    creado = models.DateTimeField(auto_now_add=True)
    entregados = models.PositiveIntegerField(default=0)
    urgente = models.BooleanField(default=False)           # llueve muy fuerte ahora o hay peligro de vida confirmado
    retenido = models.BooleanField("retenido por ser de noche", default=False)
    resumido = models.BooleanField("ya salió en el resumen de la mañana", default=False)

    class Meta:
        verbose_name = "aviso enviado"
        verbose_name_plural = "avisos enviados"
        ordering = ["-creado"]


class NivelManual(models.Model):
    """Nivel puesto a mano por la coordinación a partir de reportes de campo.

    Solo SUBE el nivel calculado, nunca lo baja, y vale entre «desde» y «hasta».
    """

    zona = models.CharField(max_length=30)      # la-cascada, santa-cruz-alta, san-cristobal, isabela
    nivel = models.CharField(max_length=12)     # medio, alto, muy alto
    desde = models.DateTimeField()
    hasta = models.DateTimeField()
    motivo = models.TextField(blank=True)

    class Meta:
        verbose_name = "nivel puesto a mano"
        verbose_name_plural = "niveles puestos a mano"
        ordering = ["-desde"]


class NivelZona(models.Model):
    """El nivel de lluvia peligrosa de una zona en cada pasada: la historia del nivel.

    `anterior` y `coincide` solo tienen datos hasta el 22-nov-2026: son la comparación con el
    recolector que se retiró ese día, guardada como constancia de que el cálculo daba lo mismo.
    """

    zona = models.CharField(max_length=30)
    calculado = models.DateTimeField()
    nivel = models.CharField(max_length=12)
    instantaneo = models.CharField("nivel instantáneo", max_length=12, blank=True)
    silencio = models.BooleanField(default=False)
    lluvia = models.JSONField(default=dict)     # R1h, R3h, R24h, R72h
    anterior = models.CharField("nivel del recolector anterior", max_length=12, blank=True)
    coincide = models.BooleanField(null=True)   # None: no había con qué comparar

    class Meta:
        constraints = [models.UniqueConstraint(fields=["zona", "calculado"], name="nivel_zona_unico")]
        indexes = [models.Index(fields=["calculado"], name="nivel_zona_ts")]
        ordering = ["-calculado"]


class Estado(models.Model):
    """Resultados ya calculados, listos para servir (el nivel por zona, por ejemplo)."""

    clave = models.CharField(max_length=30, primary_key=True)
    datos = models.JSONField(default=dict)
    generado = models.DateTimeField()


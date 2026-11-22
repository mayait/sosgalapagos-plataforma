"""Clima: mediciones de las estaciones, guardadas en la misma base que el mapa.

Etapa 1 de la migración (docs/plan-clima.md): el recolector anterior sigue corriendo y
escribe en su base SQLite; aquí se copia todo a PostgreSQL cada cinco minutos, y desde
aquí se sirven las series, los resúmenes por hora y la salud de cada fuente.

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


class Sincronizacion(models.Model):
    """Cada copia desde la base del recolector anterior. Sirve para medir el retraso y el costo."""

    inicio = models.DateTimeField(auto_now_add=True)
    segundos = models.FloatField(default=0)
    leidas = models.IntegerField(default=0)
    cambiadas = models.IntegerField(default=0)
    borradas = models.IntegerField(default=0)
    completa = models.BooleanField(default=False)
    error = models.TextField(blank=True)

    class Meta:
        verbose_name = "sincronización"
        verbose_name_plural = "sincronizaciones"
        ordering = ["-inicio"]


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


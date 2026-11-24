# SOS Galápagos · © 2026 Universidad San Francisco de Quito (USFQ) · Autor: Julián Maya <jamaya@usfq.edu.ec>
# Licencia Apache 2.0 (ver LICENSE y NOTICE): puede reutilizarse dando crédito.
"""Lo que coordinación edita en la portada (sosgalapagos.org/) desde el admin.

- El aviso destacado en rojo, con su vencimiento: se oculta solo al pasar `hasta`.
- «Situación hoy»: frases cortas por tema, con la fecha en que se revisaron y cuándo caducan.
  La portada no las muestra hoy: las del 4 de noviembre caducaron y la sección solo vuelve con una vigente.
- Las organizaciones aliadas y las que atienden animales, con sus canales oficiales.

La advertencia oficial no se edita aquí: sale sola del último boletín del INAMHI (app `clima`).
Nada de esto lleva nombres de personas afectadas ni teléfonos personales.
"""
from django.db import models
from django.utils import timezone


class AvisoQuerySet(models.QuerySet):
    def vigentes(self, ahora=None):
        return self.filter(activo=True, hasta__gt=ahora or timezone.now())


class Aviso(models.Model):
    """Aviso urgente de coordinación, en rojo arriba de la portada («No necesitamos más ropa»)."""

    titulo = models.CharField("título", max_length=160)
    texto = models.TextField(blank=True, help_text="Pocas frases. Sin nombres de personas afectadas ni teléfonos personales.")
    hasta = models.DateTimeField("se muestra hasta", help_text="Al pasar esta fecha y hora deja de verse solo. Hora de Galápagos.")
    activo = models.BooleanField(default=True, help_text="Desmárcalo para quitarlo antes de que venza.")
    creado = models.DateTimeField(default=timezone.now, editable=False)

    objects = AvisoQuerySet.as_manager()

    class Meta:
        verbose_name = "aviso destacado"
        verbose_name_plural = "avisos destacados"
        ordering = ["-hasta"]

    def __str__(self):
        return self.titulo

    @property
    def vigente(self):
        return self.activo and self.hasta > timezone.now()


class SituacionQuerySet(models.QuerySet):
    def vigentes(self, ahora=None):
        """Las visibles que no han caducado. Sin fecha de caducidad, siguen vigentes hasta que se ocultan."""
        ahora = ahora or timezone.now()
        return self.filter(visible=True).filter(models.Q(caduca__isnull=True) | models.Q(caduca__gt=ahora))


class Situacion(models.Model):
    """Una línea de «Situación hoy»: qué hay que saber de un tema (refugio, comida, salud…)."""

    tema = models.CharField(max_length=60)
    texto = models.TextField(help_text="Una o dos frases. Sin teléfonos ni nombres de personas.")
    orden = models.PositiveSmallIntegerField(default=0)
    visible = models.BooleanField(default=True)
    # Se pone sola al guardar un cambio en el admin. La portada muestra la más reciente.
    actualizado = models.DateTimeField("revisado", default=timezone.now)
    caduca = models.DateTimeField("deja de verse", null=True, blank=True,
                                  help_text="Al pasar esta fecha y hora la línea se oculta sola. Vacío: se ve hasta que la ocultes.")

    objects = SituacionQuerySet.as_manager()

    class Meta:
        verbose_name = "línea de «Situación hoy»"
        verbose_name_plural = "situación hoy"
        ordering = ["orden", "id"]

    def __str__(self):
        return self.tema


class Categoria(models.TextChoices):
    ALIADA = "aliada", "Organización aliada"
    MASCOTAS = "mascotas", "Ayuda para mascotas"


class Organizacion(models.Model):
    """Una organización con trazabilidad y sus canales oficiales. Nunca cuentas personales."""

    nombre = models.CharField(max_length=120)
    categoria = models.CharField("sección", max_length=10, choices=Categoria, default=Categoria.ALIADA)
    detalle = models.TextField(blank=True)
    instagram = models.CharField(max_length=60, blank=True, help_text="Solo el usuario, sin @.")
    facebook = models.URLField(max_length=300, blank=True)
    enlace = models.URLField("otro enlace", max_length=300, blank=True)
    enlace_texto = models.CharField("texto del otro enlace", max_length=60, blank=True)
    donar = models.URLField("enlace para donar", max_length=300, blank=True, help_text="El canal oficial de pagos de la organización.")
    donar_texto = models.CharField("texto del botón de donar", max_length=40, blank=True, default="Donar")
    pago = models.TextField("datos de transferencia", blank=True,
                           help_text="Cuentas a nombre de la organización (con su RUC). Una cuenta a nombre de una persona solo si coordinación lo autorizó.")
    orden = models.PositiveSmallIntegerField(default=0)
    visible = models.BooleanField(default=True)

    class Meta:
        verbose_name = "organización"
        verbose_name_plural = "organizaciones"
        ordering = ["categoria", "orden", "id"]

    def __str__(self):
        return self.nombre

# SOS Galápagos · © 2026 Universidad San Francisco de Quito (USFQ) · Autor: Julián Maya <jamaya@usfq.edu.ec>
# Licencia Apache 2.0 (ver LICENSE y NOTICE): puede reutilizarse dando crédito.
"""Llaves de la API. Cada institución escribe con la suya."""
import hashlib
import secrets

from django.db import models


class LlaveApi(models.Model):
    institucion = models.CharField("institución", max_length=120)
    prefijo = models.CharField(max_length=12, editable=False, help_text="Primeros caracteres, para reconocerla")
    resumen = models.CharField(max_length=64, unique=True, editable=False, help_text="La llave nunca se guarda en claro")
    puede_crear = models.BooleanField("puede crear reportes", default=True)
    puede_leer_archivo = models.BooleanField("puede leer el archivo completo", default=False)
    activa = models.BooleanField(default=True)
    creada_en = models.DateTimeField(auto_now_add=True)
    ultimo_uso = models.DateTimeField("último uso", null=True, blank=True)

    class Meta:
        verbose_name = "llave de API"
        verbose_name_plural = "llaves de API"

    def __str__(self):
        return f"{self.institucion} ({self.prefijo}…)"

    @staticmethod
    def resumir(llave):
        return hashlib.sha256(llave.encode()).hexdigest()

    @classmethod
    def crear(cls, institucion, **campos):
        """Devuelve (objeto, llave en claro). La llave solo se ve esta vez."""
        llave = "sosg_" + secrets.token_urlsafe(32)
        return cls.objects.create(institucion=institucion, prefijo=llave[:10], resumen=cls.resumir(llave), **campos), llave

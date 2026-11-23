# SOS Galápagos · © 2026 Universidad San Francisco de Quito (USFQ) · Autor: Julián Maya <jamaya@usfq.edu.ec>
# Licencia Apache 2.0 (ver LICENSE y NOTICE): puede reutilizarse dando crédito.
"""Diccionario de lugares: barrios, sectores, callejones y vías con sus nombres locales.

Sirve para dos cosas: decir en qué zona cae un reporte y ubicar un texto libre
(«en el pasaje 4 de La Cascada») que llega por WhatsApp.
"""
from django.contrib.gis.db import models


class TipoZona(models.TextChoices):
    BARRIO = "barrio", "Barrio"
    SECTOR = "sector", "Sector"
    CALLEJON = "callejon", "Callejón o pasaje"
    VIA = "via", "Vía"
    REFERENCIA = "referencia", "Punto de referencia"


class Zona(models.Model):
    nombre = models.CharField(max_length=120)
    tipo = models.CharField(max_length=12, choices=TipoZona, default=TipoZona.BARRIO)
    isla = models.CharField(max_length=40)
    geometria = models.GeometryField(srid=4326)
    fuente = models.CharField(max_length=120, blank=True)
    # Zona de /clima que le corresponde (la-cascada, santa-cruz-alta, san-cristobal, isabela).
    zona_clima = models.CharField(max_length=40, blank=True)

    class Meta:
        ordering = ["isla", "nombre"]
        constraints = [models.UniqueConstraint(fields=["nombre", "tipo", "isla"], name="zona_unica")]

    def __str__(self):
        return f"{self.nombre} ({self.isla})"


class AliasZona(models.Model):
    """Otro nombre con el que la gente llama a una zona. Se llena a mano en el admin."""

    zona = models.ForeignKey(Zona, on_delete=models.CASCADE, related_name="alias")
    nombre = models.CharField(max_length=120)

    class Meta:
        verbose_name = "alias de zona"
        verbose_name_plural = "alias de zonas"

    def __str__(self):
        return self.nombre


def zona_de(punto):
    """La zona más pequeña que contiene el punto, o None."""
    from django.contrib.gis.db.models.functions import Area

    return (
        Zona.objects.filter(geometria__contains=punto)
        .annotate(superficie=Area("geometria"))
        .order_by("superficie")
        .first()
    )

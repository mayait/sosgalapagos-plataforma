"""Mensajes que llegan por canales externos (WhatsApp) y esperan verificación.

Un mensaje nunca se publica solo: coordinación lo convierte en reporte o lo descarta.
"""
from django.db import models


class Canal(models.TextChoices):
    WHATSAPP_GRUPO = "whatsapp_grupo", "WhatsApp (grupo)"
    WHATSAPP_DIRECTO = "whatsapp_directo", "WhatsApp (directo)"


class EstadoCola(models.TextChoices):
    PENDIENTE = "pendiente", "Pendiente"
    PUBLICADO = "publicado", "Publicado como reporte"
    DESCARTADO = "descartado", "Descartado"


class MensajeEntrante(models.Model):
    canal = models.CharField(max_length=20, choices=Canal)
    grupo = models.CharField(max_length=120, blank=True)
    remitente_hash = models.CharField(max_length=64, blank=True, help_text="Resumen con clave del teléfono; nunca el número")
    texto = models.TextField(blank=True)
    medios = models.JSONField(default=list, blank=True)
    candidato = models.JSONField(default=dict, blank=True, help_text="Tipo, lugar, hora y foto que extrajo el bot")
    estado_cola = models.CharField(max_length=12, choices=EstadoCola, default=EstadoCola.PENDIENTE, db_index=True)
    recibido_en = models.DateTimeField(auto_now_add=True)
    reporte = models.ForeignKey("reportes.Reporte", null=True, blank=True, on_delete=models.SET_NULL)

    class Meta:
        verbose_name = "mensaje entrante"
        verbose_name_plural = "mensajes entrantes"
        ordering = ["-recibido_en"]

    def __str__(self):
        return f"{self.get_canal_display()} · {self.recibido_en:%d-%m %H:%M}"

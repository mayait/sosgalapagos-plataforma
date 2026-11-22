# SOS Galápagos · © 2026 Universidad San Francisco de Quito (USFQ) · Autor: Julián Maya <jamaya@usfq.edu.ec>
# Todos los derechos reservados. Usar, copiar, modificar o derivar de este código requiere permiso escrito del autor (ver LICENSE).
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
    id_externo = models.CharField(max_length=160, blank=True, db_index=True, help_text="Identificador del mensaje en WhatsApp, para no procesarlo dos veces")
    conversacion = models.ForeignKey("Conversacion", null=True, blank=True, on_delete=models.SET_NULL, related_name="mensajes")
    respuesta = models.TextField(blank=True, help_text="Lo que se respondió (o se habría respondido, en modo ensayo)")
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


class Conversacion(models.Model):
    """El hilo abierto con una persona mientras se arma su reporte.

    El identificador del chat se guarda cifrado (hace falta para responder) y su resumen
    con clave sirve para reconocer a la persona. El número nunca queda en claro, y la
    conversación se borra a los pocos días.
    """

    chat_hash = models.CharField(max_length=64, unique=True)
    chat_cifrado = models.TextField()
    es_grupo = models.BooleanField(default=False)
    # Lo que se lleva reunido: tipo, descripción, lugar, foto, contacto…
    borrador = models.JSONField(default=dict, blank=True)
    # Qué se le preguntó y cuántas veces: «ubicacion», «contacto», «nombre», «que_pasa».
    espera = models.CharField(max_length=20, blank=True)
    intentos = models.PositiveSmallIntegerField(default=0)
    ultimo_reporte = models.ForeignKey("reportes.Reporte", null=True, blank=True, on_delete=models.SET_NULL)
    creada_en = models.DateTimeField(auto_now_add=True)
    actualizada_en = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "conversación de WhatsApp"
        verbose_name_plural = "conversaciones de WhatsApp"
        ordering = ["-actualizada_en"]

    def __str__(self):
        return f"Conversación {self.chat_hash[:8]} · {self.actualizada_en:%d-%m %H:%M}"

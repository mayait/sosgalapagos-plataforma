# SOS Galápagos · © 2026 Universidad San Francisco de Quito (USFQ) · Autor: Julián Maya <jamaya@usfq.edu.ec>
# Licencia Apache 2.0 (ver LICENSE y NOTICE): puede reutilizarse dando crédito.
from django.contrib import admin

from .models import Conversacion, MensajeEntrante


@admin.register(MensajeEntrante)
class MensajeEntranteAdmin(admin.ModelAdmin):
    list_display = ("recibido_en", "canal", "estado_cola", "texto_corto", "respuesta_corta", "reporte")
    list_filter = ("estado_cola", "canal")
    readonly_fields = ("canal", "grupo", "remitente_hash", "id_externo", "conversacion", "texto", "medios", "candidato", "respuesta", "recibido_en", "reporte")

    @admin.display(description="mensaje")
    def texto_corto(self, m):
        return m.texto[:70]

    @admin.display(description="respuesta")
    def respuesta_corta(self, m):
        return m.respuesta[:70]


@admin.register(Conversacion)
class ConversacionAdmin(admin.ModelAdmin):
    list_display = ("chat_hash", "es_grupo", "espera", "intentos", "ultimo_reporte", "actualizada_en")
    exclude = ("chat_cifrado", "borrador")  # ni el chat ni la foto del borrador se muestran
    readonly_fields = ("chat_hash", "es_grupo", "espera", "intentos", "ultimo_reporte")

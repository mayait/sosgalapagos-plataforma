from django.contrib import admin

from .models import MensajeEntrante


@admin.register(MensajeEntrante)
class MensajeEntranteAdmin(admin.ModelAdmin):
    list_display = ("recibido_en", "canal", "grupo", "estado_cola")
    list_filter = ("estado_cola", "canal")

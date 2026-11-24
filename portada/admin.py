# SOS Galápagos · © 2026 Universidad San Francisco de Quito (USFQ) · Autor: Julián Maya <jamaya@usfq.edu.ec>
# Licencia Apache 2.0 (ver LICENSE y NOTICE): puede reutilizarse dando crédito.
from django.contrib import admin
from django.utils import timezone

from .models import Aviso, Organizacion, Situacion


@admin.register(Aviso)
class AvisoAdmin(admin.ModelAdmin):
    list_display = ("titulo", "hasta", "activo", "vigente")
    list_editable = ("activo",)

    @admin.display(boolean=True, description="se ve ahora")
    def vigente(self, obj):
        return obj.vigente


@admin.register(Situacion)
class SituacionAdmin(admin.ModelAdmin):
    list_display = ("tema", "texto", "orden", "visible", "actualizado", "caduca", "vigente")
    list_editable = ("orden", "visible")
    readonly_fields = ("actualizado",)

    @admin.display(boolean=True, description="se ve ahora")
    def vigente(self, obj):
        return obj.visible and (obj.caduca is None or obj.caduca > timezone.now())

    def save_model(self, request, obj, form, change):
        # La fecha «Actualizado el…» de la portada es la del último cambio real de texto.
        if not change or {"tema", "texto"} & set(form.changed_data):
            obj.actualizado = timezone.now()
        super().save_model(request, obj, form, change)


@admin.register(Organizacion)
class OrganizacionAdmin(admin.ModelAdmin):
    list_display = ("nombre", "categoria", "orden", "visible")
    list_editable = ("orden", "visible")
    list_filter = ("categoria",)

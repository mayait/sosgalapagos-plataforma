from django.contrib.gis import admin

from . import reglas
from .models import Confirmacion, Estado, FotoReporte, MotivoCierre, Reporte, TipoRiesgo


@admin.register(TipoRiesgo)
class TipoRiesgoAdmin(admin.ModelAdmin):
    list_display = ("nombre", "codigo", "clase", "plazo_horas", "orden", "activo")
    list_editable = ("plazo_horas", "orden", "activo")


class ConfirmacionEnLinea(admin.TabularInline):
    model = Confirmacion
    extra = 0
    readonly_fields = ("tipo", "fecha", "huella")
    can_delete = False


class FotoEnLinea(admin.TabularInline):
    model = FotoReporte
    extra = 0


@admin.register(Reporte)
class ReporteAdmin(admin.GISModelAdmin):
    list_display = ("id_publico", "titulo", "tipo", "gravedad", "estado", "contenido_visible", "zona", "visto_en", "vence_en", "fuente")
    list_filter = ("estado", "tipo__clase", "tipo", "gravedad", "fuente", "contenido_visible")
    search_fields = ("id_publico", "titulo", "nota")
    readonly_fields = ("id_publico", "vence_en", "huella", "creado_en", "cerrado_en", "motivo_cierre")
    inlines = [FotoEnLinea, ConfirmacionEnLinea]
    actions = ["verificar", "publicar_contenido", "cerrar"]

    # Un reporte nunca se borra: se cierra y queda en el archivo.
    def has_delete_permission(self, request, obj=None):
        return False

    @admin.action(description="Marcar como confirmado y publicar su foto y nota")
    def verificar(self, request, queryset):
        queryset.filter(estado=Estado.POR_VERIFICAR).update(estado=Estado.CONFIRMADO)
        queryset.update(contenido_visible=True)

    @admin.action(description="Publicar foto y nota (ya revisadas)")
    def publicar_contenido(self, request, queryset):
        queryset.update(contenido_visible=True)

    @admin.action(description="Cerrar (pasa al archivo)")
    def cerrar(self, request, queryset):
        for reporte in queryset.exclude(estado=Estado.CERRADO):
            reglas.cerrar(reporte, MotivoCierre.COORDINADOR)

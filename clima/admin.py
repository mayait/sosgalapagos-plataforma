from django.contrib.gis import admin

from .models import Calibracion, Corrida, Estacion, EstacionDanada, Sincronizacion


class SoloLectura(admin.ModelAdmin):
    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Estacion)
class EstacionAdmin(SoloLectura):
    list_display = ("nombre", "fuente", "codigo", "isla", "operador", "primera", "ultima")
    list_filter = ("fuente", "isla")
    search_fields = ("nombre", "codigo")


@admin.register(Corrida)
class CorridaAdmin(SoloLectura):
    list_display = ("ts", "fuente", "ok", "registros", "segundos", "error")
    list_filter = ("fuente", "ok")
    date_hierarchy = "ts"


@admin.register(Sincronizacion)
class SincronizacionAdmin(SoloLectura):
    list_display = ("inicio", "completa", "leidas", "cambiadas", "borradas", "segundos", "error")


@admin.register(EstacionDanada)
class EstacionDanadaAdmin(admin.ModelAdmin):
    list_display = ("estacion", "variable", "desde", "hasta", "motivo")
    autocomplete_fields = ("estacion",)


@admin.register(Calibracion)
class CalibracionAdmin(SoloLectura):
    list_display = ("creada", "grupo", "plazo", "dias", "eventos", "brier", "brier_base", "habilidad")
    list_filter = ("grupo", "plazo")


# SOS Galápagos · © 2026 Universidad San Francisco de Quito (USFQ) · Autor: Julián Maya <jamaya@usfq.edu.ec>
# Todos los derechos reservados. Usar, copiar, modificar o derivar de este código requiere permiso escrito del autor (ver LICENSE).
from django.contrib.gis import admin

from .models import NivelManual, NivelZona, AvisoEnviado, Boletin, Calibracion, Corrida, Estacion, EstacionDanada, MareaExtremo, PronosticoCorrida, PronosticoOficial


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


@admin.register(PronosticoCorrida)
class PronosticoCorridaAdmin(SoloLectura):
    list_display = ("recibido", "modelo", "tipo", "corrida", "disponible")
    list_filter = ("tipo", "modelo")
    exclude = ("datos",)


@admin.register(EstacionDanada)
class EstacionDanadaAdmin(admin.ModelAdmin):
    list_display = ("estacion", "variable", "desde", "hasta", "motivo")
    autocomplete_fields = ("estacion",)


@admin.register(Calibracion)
class CalibracionAdmin(SoloLectura):
    list_display = ("creada", "grupo", "plazo", "dias", "eventos", "brier", "brier_base", "habilidad")
    list_filter = ("grupo", "plazo")


@admin.register(Boletin)
class BoletinAdmin(admin.ModelAdmin):
    """Lo extrae un modelo de lenguaje: aquí una persona lo corrige y lo marca como revisado."""

    list_display = ("visto_en", "fuente", "tipo", "numero", "afecta_galapagos", "nivel", "vigente_hasta", "revisado")
    list_filter = ("fuente", "tipo", "afecta_galapagos", "revisado")
    readonly_fields = ("huella", "extraido_con", "visto_en")


@admin.register(AvisoEnviado)
class AvisoEnviadoAdmin(SoloLectura):
    list_display = ("creado", "tema", "zona", "titulo", "entregados")
    list_filter = ("tema", "zona")


@admin.register(MareaExtremo)
class MareaExtremoAdmin(SoloLectura):
    list_display = ("ts", "puerto", "tipo", "altura_m", "fuente", "datum")
    list_filter = ("puerto", "fuente")


@admin.register(PronosticoOficial)
class PronosticoOficialAdmin(SoloLectura):
    list_display = ("fecha", "isla", "minima_c", "maxima_c", "obtenido")


@admin.register(NivelManual)
class NivelManualAdmin(admin.ModelAdmin):
    """Subir a mano el nivel de una zona por un reporte de campo. Solo sube, nunca baja."""

    list_display = ("zona", "nivel", "desde", "hasta", "motivo")
    list_filter = ("zona",)


@admin.register(NivelZona)
class NivelZonaAdmin(SoloLectura):
    list_display = ("calculado", "zona", "nivel", "instantaneo", "silencio")
    list_filter = ("zona", "nivel")


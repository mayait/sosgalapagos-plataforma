# SOS Galápagos · © 2026 Universidad San Francisco de Quito (USFQ) · Autor: Julián Maya <jamaya@usfq.edu.ec>
# Licencia Apache 2.0 (ver LICENSE y NOTICE): puede reutilizarse dando crédito.
from django.contrib.gis import admin

from . import reglas
from .models import Colaborador, Confirmacion, DocumentoReporte, Estado, EstadoUbicar, FotoReporte, MotivoCierre, PorUbicar, Reporte, Suceso, SuscripcionPush, TipoRiesgo, Ubicacion


@admin.register(TipoRiesgo)
class TipoRiesgoAdmin(admin.ModelAdmin):
    list_display = ("nombre", "codigo", "clase", "plazo_horas", "pide_contacto", "pide_duracion", "orden", "activo")
    list_editable = ("plazo_horas", "pide_contacto", "pide_duracion", "orden", "activo")


class ConfirmacionEnLinea(admin.TabularInline):
    model = Confirmacion
    extra = 0
    readonly_fields = ("tipo", "fecha", "huella")
    can_delete = False


class FotoEnLinea(admin.TabularInline):
    model = FotoReporte
    extra = 0


class DocumentoEnLinea(admin.TabularInline):
    model = DocumentoReporte
    extra = 0
    can_delete = False  # un documento nunca se borra
    fields = ("archivo", "titulo", "fecha", "publico", "ver", "subido_en")
    readonly_fields = ("ver", "subido_en")

    @admin.display(description="Abrir")
    def ver(self, obj):
        from django.urls import reverse
        from django.utils.html import format_html

        if not obj.pk:
            return "—"
        return format_html('<a href="{}" target="_blank" rel="noopener">Abrir el PDF</a>', reverse("reportes:documento", args=[obj.pk]))


@admin.register(Reporte)
class ReporteAdmin(admin.GISModelAdmin):
    list_display = ("id_publico", "titulo", "tipo", "gravedad", "estado", "contenido_visible", "zona", "visto_en", "vence_en", "fuente")
    list_filter = ("estado", "tipo__clase", "tipo", "gravedad", "fuente", "contenido_visible")
    search_fields = ("id_publico", "titulo", "nota")
    readonly_fields = ("id_publico", "vence_en", "huella", "creado_en", "cerrado_en", "motivo_cierre")
    inlines = [DocumentoEnLinea, FotoEnLinea, ConfirmacionEnLinea]
    actions = ["verificar", "ocultar_contenido", "publicar_contenido", "avisar", "cerrar"]

    # Un reporte nunca se borra: se cierra y queda en el archivo.
    def has_delete_permission(self, request, obj=None):
        return False

    @admin.action(description="Marcar como confirmado y publicar su foto y nota")
    def verificar(self, request, queryset):
        from .tareas import avisar_reporte

        nuevos = list(queryset.filter(estado=Estado.POR_VERIFICAR, tipo__clase="riesgo").values_list("pk", flat=True))
        queryset.filter(estado=Estado.POR_VERIFICAR).update(estado=Estado.CONFIRMADO)
        queryset.update(contenido_visible=True)
        for pk in nuevos:  # un peligro recién confirmado se avisa a quien tiene los avisos encendidos
            avisar_reporte.enqueue(pk)

    @admin.action(description="Mandar aviso al teléfono de quienes lo pidieron")
    def avisar(self, request, queryset):
        from .tareas import avisar_reporte

        for reporte in queryset.exclude(estado=Estado.CERRADO)[:5]:
            avisar_reporte.enqueue(reporte.pk)

    @admin.action(description="Volver a publicar foto y nota")
    def publicar_contenido(self, request, queryset):
        queryset.update(contenido_visible=True)

    @admin.action(description="Ocultar foto y nota")
    def ocultar_contenido(self, request, queryset):
        queryset.update(contenido_visible=False)

    @admin.action(description="Cerrar (pasa al archivo)")
    def cerrar(self, request, queryset):
        for reporte in queryset.exclude(estado=Estado.CERRADO):
            reglas.cerrar(reporte, MotivoCierre.COORDINADOR)


@admin.register(Colaborador)
class ColaboradorAdmin(admin.ModelAdmin):
    list_display = ("nombre", "puntos", "avisos", "ubicados", "visible", "creado_en")
    list_editable = ("visible",)
    search_fields = ("nombre",)
    readonly_fields = ("huella", "puntos", "avisos", "ubicados", "creado_en")


@admin.register(SuscripcionPush)
class SuscripcionPushAdmin(admin.ModelAdmin):
    list_display = ("creada_en", "ultimo_envio")
    readonly_fields = ("direccion", "p256dh", "auth", "huella", "creada_en", "ultimo_envio")


@admin.register(Suceso)
class SucesoAdmin(admin.ModelAdmin):
    """Lo que debe quedar en la línea del tiempo y no es un punto del mapa: comunicados, noticias, informes, notas.

    Sin nombres de personas afectadas, cédulas ni teléfonos personales.
    """

    list_display = ("ocurrido", "clase", "institucion", "titulo", "fuente", "zona", "hasta", "visible")
    list_filter = ("clase", "institucion", "zona", "visible")
    list_editable = ("visible",)
    search_fields = ("titulo", "texto", "fuente")
    date_hierarchy = "ocurrido"



class UbicacionEnLinea(admin.TabularInline):
    model = Ubicacion
    extra = 0
    can_delete = False
    fields = ("punto_txt", "texto", "autor", "de_coordinacion", "acertada", "creada_en")
    readonly_fields = fields

    @admin.display(description="punto")
    def punto_txt(self, u):
        return f"{u.punto.y:.5f}, {u.punto.x:.5f}"


@admin.register(PorUbicar)
class PorUbicarAdmin(admin.ModelAdmin):
    """Fotos que llegaron de los grupos de WhatsApp sin un lugar seguro.

    Las que están «en revisión» no se ven en /riesgos/ubicar/: una cara en primer plano, un menor,
    un documento, o el clasificador no pudo mirarlas. Para ubicar una tú mismo, ábrela desde
    «Ver y ubicar» con la sesión iniciada: tu ubicación la pasa al mapa sin esperar a nadie.
    """

    list_display = ("miniatura", "visto_en", "estado", "motivo_revision", "texto", "tipo", "propuestas", "reporte")
    list_filter = ("estado", "es_video", "tipo")
    search_fields = ("id_publico", "texto")
    readonly_fields = ("id_publico", "miniatura_grande", "ver", "visto_en", "es_video", "huella_foto", "id_origen", "clasificacion", "reporte", "creado_en")
    fields = ("id_publico", "miniatura_grande", "ver", "estado", "motivo_revision", "texto", "tipo", "pista", "visto_en", "es_video", "reporte", "clasificacion", "id_origen", "creado_en")
    inlines = [UbicacionEnLinea]
    actions = ["aprobar", "descartar"]

    def has_delete_permission(self, request, obj=None):
        return False  # nunca se borra: se descarta

    @admin.display(description="foto")
    def miniatura(self, p):
        from django.utils.html import format_html

        return format_html('<img src="{}" style="height:56px;border-radius:6px">', p.foto.url) if p.foto else "—"

    @admin.display(description="foto")
    def miniatura_grande(self, p):
        from django.utils.html import format_html

        return format_html('<img src="{}" style="max-width:420px;max-height:420px">', p.foto.url) if p.foto else "—"

    @admin.display(description="propuestas")
    def propuestas(self, p):
        return p.ubicaciones.count()

    @admin.display(description="ubicar")
    def ver(self, p):
        from django.urls import reverse
        from django.utils.html import format_html

        return format_html('<a href="{}" target="_blank" rel="noopener">Ver y ubicar</a>', reverse("reportes:ubicar", args=[p.id_publico]))

    @admin.action(description="Aprobar la foto: puede verse (pasa a la lista o a su reporte)")
    def aprobar(self, request, queryset):
        for item in queryset.filter(estado=EstadoUbicar.REVISION):
            reglas.aprobar_por_ubicar(item)

    @admin.action(description="Descartar (no se pide ubicar)")
    def descartar(self, request, queryset):
        queryset.exclude(estado=EstadoUbicar.UBICADO).update(estado=EstadoUbicar.DESCARTADO)

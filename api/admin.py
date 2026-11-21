from django.contrib import admin, messages

from .models import LlaveApi


@admin.register(LlaveApi)
class LlaveApiAdmin(admin.ModelAdmin):
    list_display = ("institucion", "prefijo", "puede_crear", "activa", "ultimo_uso")
    readonly_fields = ("prefijo", "resumen", "creada_en", "ultimo_uso")

    def save_model(self, request, obj, form, change):
        if change:
            return super().save_model(request, obj, form, change)
        nueva, llave = LlaveApi.crear(obj.institucion, puede_crear=obj.puede_crear, puede_leer_archivo=obj.puede_leer_archivo)
        obj.pk = nueva.pk
        messages.warning(request, f"Llave de {nueva.institucion}: {llave} — cópiala ahora, no se vuelve a mostrar.")

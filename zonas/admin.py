# SOS Galápagos · © 2026 Universidad San Francisco de Quito (USFQ) · Autor: Julián Maya <jamaya@usfq.edu.ec>
# Todos los derechos reservados. Usar, copiar, modificar o derivar de este código requiere permiso escrito del autor (ver LICENSE).
from django.contrib.gis import admin

from .models import AliasZona, Zona


class AliasEnLinea(admin.TabularInline):
    model = AliasZona
    extra = 1


@admin.register(Zona)
class ZonaAdmin(admin.GISModelAdmin):
    list_display = ("nombre", "tipo", "isla", "zona_clima", "fuente")
    list_filter = ("isla", "tipo")
    search_fields = ("nombre", "alias__nombre")
    inlines = [AliasEnLinea]

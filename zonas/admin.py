# SOS Galápagos · © 2026 Universidad San Francisco de Quito (USFQ) · Autor: Julián Maya <jamaya@usfq.edu.ec>
# Licencia Apache 2.0 (ver LICENSE y NOTICE): puede reutilizarse dando crédito.
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

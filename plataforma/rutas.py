"""Rutas de la plataforma.

Hasta la fase 4 todo lo nuevo vive bajo /mapa/ y /api/, para no chocar con
ResponseGrid, que sigue sirviendo la portada.
"""
from django.conf import settings
from django.contrib import admin
from django.urls import include, path, re_path
from django.views.generic import RedirectView
from django.views.static import serve

from api.rutas import api

urlpatterns = [
    path("", RedirectView.as_view(url="/mapa/")),
    path("mapa/", include("reportes.rutas")),
    path("api/", api.urls),
    path("admin/", admin.site.urls),
]

if settings.DEBUG:
    # Solo en la Mac: las fotos y las capas del repo de datos. En el servidor las sirve Caddy.
    urlpatterns += [
        re_path(r"^medios/(?P<path>.*)$", serve, {"document_root": settings.MEDIA_ROOT}),
        re_path(r"^capas/(?P<path>.*)$", serve, {"document_root": settings.CAPAS_DIR}),
    ]

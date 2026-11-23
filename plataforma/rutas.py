# SOS Galápagos · © 2026 Universidad San Francisco de Quito (USFQ) · Autor: Julián Maya <jamaya@usfq.edu.ec>
# Licencia Apache 2.0 (ver LICENSE y NOTICE): puede reutilizarse dando crédito.
"""Rutas de la plataforma.

Todo vive bajo /riesgos/ (páginas, API, administración, estáticos y fotos). Así en el
servidor basta una sola ruta nueva en Caddy y nada choca con el sitio actual, que ya
usa /api y /admin.
"""
from django.conf import settings
from django.contrib import admin
from django.urls import include, path, re_path
from django.views.generic import RedirectView
from django.views.static import serve

from api.rutas import api
from reportes.vistas import copia_de_mapas, relieve

urlpatterns = [
    path("riesgos/api/", api.urls),
    path("riesgos/admin/", admin.site.urls),
    # Fotos de los reportes. Son pocas y pequeñas: las sirve Django, sin tocar los volúmenes de Caddy.
    # documentos/ no se sirve aquí: los PDF de los reportes pasan por reportes.vistas.documento.
    re_path(r"^riesgos/medios/(?!documentos/)(?P<path>.*)$", serve, {"document_root": settings.MEDIA_ROOT}),
    re_path(r"^riesgos/relieve3d/(?P<ruta>[\w./-]+)$", relieve),
    path("riesgos/", include("reportes.rutas")),
]

if settings.DEBUG:
    # Solo en la Mac: la portada lleva al mapa, y /mapas es una copia de lo publicado.
    urlpatterns += [
        path("", RedirectView.as_view(url="/riesgos/")),
        re_path(r"^mapas/(?P<ruta>.*)$", copia_de_mapas),
    ]

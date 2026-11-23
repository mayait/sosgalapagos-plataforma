# SOS Galápagos · © 2026 Universidad San Francisco de Quito (USFQ) · Autor: Julián Maya <jamaya@usfq.edu.ec>
# Licencia Apache 2.0 (ver LICENSE y NOTICE): puede reutilizarse dando crédito.
"""Rutas de la plataforma.

El mapa de riesgos y el clima viven bajo /riesgos/ (páginas, API, administración, estáticos y
fotos). Desde el 23-nov-2026 la plataforma sirve también la raíz del sitio: la portada (/), la
privacidad (/privacidad), robots, sitemap y las redirecciones de la plataforma anterior
(portada/rutas.py). /mapas, /clima, /descargas y /backend los sigue sirviendo Caddy.
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
    # documentos/ y oficiales/ no se sirven aquí: esos PDF pasan por reportes.vistas (documento y oficial).
    re_path(r"^riesgos/medios/(?!documentos/|oficiales/)(?P<path>.*)$", serve, {"document_root": settings.MEDIA_ROOT}),
    re_path(r"^riesgos/relieve3d/(?P<ruta>[\w./-]+)$", relieve),
    # La privacidad es una sola para todo el sitio.
    path("riesgos/privacidad/", RedirectView.as_view(url="/privacidad", permanent=True)),
    path("riesgos/", include("reportes.rutas")),
    path("", include("portada.rutas")),
]

if settings.DEBUG:
    # Solo en la Mac: /mapas es una copia de lo publicado.
    urlpatterns += [re_path(r"^mapas/(?P<ruta>.*)$", copia_de_mapas)]

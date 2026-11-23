# SOS Galápagos · © 2026 Universidad San Francisco de Quito (USFQ) · Autor: Julián Maya <jamaya@usfq.edu.ec>
# Licencia Apache 2.0 (ver LICENSE y NOTICE): puede reutilizarse dando crédito.
"""Rutas de la raíz del sitio: la portada, la privacidad, robots, sitemap e icono.

Y las rutas de la plataforma de coordinación anterior (ResponseGrid, retirada el 23-nov-2026),
que llevan con una redirección permanente (301) a lo que hoy hace lo mismo. Van con prefijos
explícitos, sin comodín: lo que no está aquí da 404.
"""
from django.urls import path, re_path
from django.views.generic import RedirectView

from . import vistas


def a(destino):
    return RedirectView.as_view(url=destino, permanent=True, query_string=False)


# (expresión, destino). /e/<emergencia>/… era la página de la emergencia y su mapa.
VIEJAS = [
    (r"^e/[\w-]+/reportar/?$", "/riesgos/reportar/"),
    (r"^e/[\w-]+/(donar|donacion|pre-registro|recepcion|registrar)(/.*)?$", "/#organizaciones"),
    (r"^e/[\w-]+/(peticion|ofrecer-transporte)/?$", "/#ayuda"),
    (r"^e/[\w-]+/(voluntario|mi-voluntariado|mis-expediciones)/?$", "/#grupos-whatsapp"),
    (r"^e(/.*)?$", "/riesgos/"),
    (r"^(peticion|voluntario)/?$", "/#ayuda"),
    (r"^(login|signup|verificar|offline)/?$", "/"),
    (r"^(auth|panel|dashboard|admin|emergencies|organizations)(/.*)?$", "/"),
    (r"^(transparencia|sobre|funcionalidades|como-funciona)/?$", "/"),
    (r"^docs/?$", "/riesgos/api/docs"),
    (r"^eliminar-datos/?$", "/privacidad#derechos"),
    (r"^privacidad/$", "/privacidad"),
]

urlpatterns = [
    path("", vistas.portada, name="portada"),
    path("privacidad", vistas.privacidad, name="privacidad"),
    path("robots.txt", vistas.robots, name="robots"),
    path("sitemap.xml", vistas.sitemap, name="sitemap"),
    path("icon.svg", vistas.icono, name="icono"),
    re_path(r"^icons/icon-(?P<tamano>192|512)\.png$", vistas.icono_png),
    path("sw.js", vistas.sw_retirado),
] + [re_path(expresion, a(destino)) for expresion, destino in VIEJAS]

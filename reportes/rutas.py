# SOS Galápagos · © 2026 Universidad San Francisco de Quito (USFQ) · Autor: Julián Maya <jamaya@usfq.edu.ec>
# Todos los derechos reservados. Usar, copiar, modificar o derivar de este código requiere permiso escrito del autor (ver LICENSE).
from django.urls import path

from . import vistas

app_name = "reportes"
urlpatterns = [
    path("", vistas.mapa, name="mapa"),
    path("reportar/", vistas.reportar, name="reportar"),
    path("cerca/", vistas.cerca, name="cerca"),
    path("lluvia/", vistas.lluvia, name="lluvia"),
    path("informe/", vistas.informe, name="informe"),
    path("descargas/", vistas.descargas, name="descargas"),
    path("puntos/", vistas.puntos, name="puntos"),
    path("mapa-del-tiempo/", vistas.tiempo, name="tiempo"),
    path("avisos/suscribir/", vistas.push_suscribir, name="push_suscribir"),
    path("r/<str:id_publico>/", vistas.ficha, name="ficha"),
    path("r/<str:id_publico>/confirmar/", vistas.confirmar, name="confirmar"),
    path("documento/<int:pk>/", vistas.documento, name="documento"),
    path("app.webmanifest", vistas.manifiesto_app, name="manifiesto_app"),
    path("sw.js", vistas.service_worker, name="service_worker"),
    path("app.js", vistas.app_cargador, name="app_cargador"),
    path("app/", vistas.app_js, name="app_js"),
]

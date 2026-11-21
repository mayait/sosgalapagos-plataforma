from django.urls import path

from . import vistas

app_name = "reportes"
urlpatterns = [
    path("", vistas.mapa, name="mapa"),
    path("reportar/", vistas.reportar, name="reportar"),
    path("cerca/", vistas.cerca, name="cerca"),
    path("lluvia/", vistas.lluvia, name="lluvia"),
    path("informes/", vistas.informes, name="informes"),
    path("informe/", vistas.informe, name="informe"),
    path("descargas/", vistas.descargas, name="descargas"),
    path("r/<str:id_publico>/", vistas.ficha, name="ficha"),
    path("r/<str:id_publico>/confirmar/", vistas.confirmar, name="confirmar"),
    path("app.webmanifest", vistas.manifiesto_app, name="manifiesto_app"),
    path("sw.js", vistas.service_worker, name="service_worker"),
]

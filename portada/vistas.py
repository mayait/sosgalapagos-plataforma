# SOS Galápagos · © 2026 Universidad San Francisco de Quito (USFQ) · Autor: Julián Maya <jamaya@usfq.edu.ec>
# Licencia Apache 2.0 (ver LICENSE y NOTICE): puede reutilizarse dando crédito.
"""La portada del sitio (sosgalapagos.org/), la privacidad y lo que el sitio sirve en la raíz.

Reemplaza a la portada de ResponseGrid, que se retiró. Las rutas viejas de esa plataforma
llevan con una redirección permanente a lo que hoy hace lo mismo (ver rutas.py).
"""
from datetime import timedelta, timezone as dt_timezone

from django.conf import settings
from django.contrib.staticfiles import finders
from django.http import FileResponse, Http404, HttpResponse
from django.shortcuts import render
from django.templatetags.static import static
from django.utils import timezone
from django.views.decorators.cache import cache_control
from django.views.decorators.http import require_GET

from . import contenido, informes
from .models import Aviso, Categoria, Organizacion, Situacion

GALAPAGOS = dt_timezone(timedelta(hours=-6))
DIAS = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]


def hora_galapagos(fecha, con_dia=True):
    """«sábado 21 de noviembre, 16:00» en hora de Galápagos."""
    f = fecha.astimezone(GALAPAGOS)
    dia = f"{DIAS[f.weekday()]} {f.day} de {informes.MESES[f.month - 1]}" if con_dia else f"{f.day} de {informes.MESES[f.month - 1]}"
    return f"{dia}, {f:%H:%M}"


def advertencia_vigente(ahora=None):
    """La última advertencia del INAMHI que nombra a Galápagos y sigue vigente, o None.

    «Vigente» es lo mismo que en /clima/ y en la API (clima.oficiales.vigentes).
    """
    from clima import oficiales

    for b in oficiales.vigentes(ahora):  # del más reciente al más antiguo
        if b["fuente"] == "INAMHI" and b["tipo"] == "advertencia" and b["afecta_galapagos"]:
            return {
                **b,
                "desde_txt": hora_galapagos(b["vigente_desde"]) if b["vigente_desde"] else "",
                "hasta_txt": hora_galapagos(b["vigente_hasta"]) if b["vigente_hasta"] else "",
                "emitido_txt": hora_galapagos(b["emitido"]) if b["emitido"] else "",
            }
    return None


@require_GET
def portada(request):
    ahora = timezone.now()
    situacion = list(Situacion.objects.filter(visible=True))
    lista = informes.leer()
    for i in lista:
        i["fecha_txt"] = informes.fecha_larga(i["fecha"])
    organizaciones = Organizacion.objects.filter(visible=True)
    return render(request, "portada/portada.html", {
        "aviso": Aviso.objects.vigentes(ahora).first(),
        "advertencia": advertencia_vigente(ahora),
        "situacion": situacion,
        "situacion_fecha": hora_galapagos(max(s.actualizado for s in situacion)) if situacion else "",
        "aliadas": [o for o in organizaciones if o.categoria == Categoria.ALIADA],
        "mascotas": [o for o in organizaciones if o.categoria == Categoria.MASCOTAS],
        "informes": lista,
        "informes_url": settings.INFORMES_URL,
        "cont": contenido,
        "compartir": {
            "titulo": "SOS Galápagos · Inundaciones en Santa Cruz",
            "descripcion": "Situación, refugio, cómo ayudar, mapa de riesgos, clima y línea del tiempo. Emergencias: 911.",
            "imagen": request.build_absolute_uri(static("app/icono-512.png")),
            "url": request.build_absolute_uri("/"),
            "con_foto": False,
        },
    })


@require_GET
def privacidad(request):
    """Una sola política para todo el sitio: portada, mapa de riesgos, WhatsApp, avisos, clima y la app."""
    return render(request, "portada/privacidad.html", {"correo": settings.PRIVACIDAD_CORREO, "actualizada": settings.PRIVACIDAD_ACTUALIZADA})


@require_GET
@cache_control(max_age=86400)
def robots(request):
    sitio = request.build_absolute_uri("/").rstrip("/")
    texto = "\n".join([
        "User-agent: *",
        "Allow: /",
        "Disallow: /riesgos/admin/",
        "Disallow: /riesgos/api/",
        "Disallow: /riesgos/documento/",
        "Disallow: /riesgos/avisos/",
        f"Sitemap: {sitio}/sitemap.xml",
        "",
    ])
    return HttpResponse(texto, content_type="text/plain; charset=utf-8")


@require_GET
@cache_control(max_age=3600)
def sitemap(request):
    sitio = request.build_absolute_uri("/").rstrip("/")
    rutas = ["/", "/riesgos/", "/riesgos/informe/", "/clima/", "/riesgos/mapa-del-tiempo/", "/riesgos/descargas/", "/privacidad"]
    urls = "".join(f"<url><loc>{sitio}{r}</loc></url>" for r in rutas)
    return HttpResponse(f'<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{urls}</urlset>',
                        content_type="application/xml")


def _estatico(ruta, tipo):
    archivo = finders.find(ruta)
    if not archivo:
        raise Http404
    respuesta = FileResponse(open(archivo, "rb"), content_type=tipo)
    respuesta["Cache-Control"] = "public, max-age=86400"
    return respuesta


@require_GET
def icono(request):
    """/icon.svg: el isotipo de la marca. Lo usa de favicon el panel de /clima/."""
    return _estatico("marca/usfq-isotipo-color.svg", "image/svg+xml")


@require_GET
def icono_png(request, tamano):
    """/icons/icon-192.png y -512.png: los iconos de la app vieja, ahora los de la plataforma."""
    return _estatico(f"app/icono-{tamano}.png", "image/png")


@require_GET
def sw_retirado(request):
    """/sw.js: el service worker de la portada vieja (ResponseGrid) se quita solo.

    Los teléfonos que lo instalaron vuelven a pedir este archivo. Este borra las copias que
    guardó («reliefhub-…»), se da de baja y recarga las pestañas abiertas. El de la app
    actual vive en /riesgos/sw.js y no se toca.
    """
    codigo = """// SOS Galápagos: retira el service worker de la portada anterior.
self.addEventListener('install', () => self.skipWaiting());
self.addEventListener('activate', (e) => e.waitUntil((async () => {
  for (const k of await caches.keys()) if (k.startsWith('reliefhub-')) await caches.delete(k);
  await self.registration.unregister();
  for (const c of await self.clients.matchAll({ type: 'window' })) c.navigate(c.url);
})()));
"""
    respuesta = HttpResponse(codigo, content_type="text/javascript")
    respuesta["Cache-Control"] = "no-cache"
    return respuesta

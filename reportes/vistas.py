"""Pantallas públicas: mapa, formulario de reporte y ficha."""
import json
import secrets
from datetime import datetime, timedelta

from django.conf import settings
from django.contrib.gis.db.models.functions import Distance
from django.contrib.gis.geos import Point
from django.contrib.gis.measure import D
from django.http import FileResponse, Http404, HttpResponse, HttpResponseRedirect, JsonResponse
from django.shortcuts import get_object_or_404, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.cache import cache_control
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from zonas.models import zona_de

from . import clima, fotos, reglas
from .models import Gravedad, Profundidad, Reporte, TipoConfirmacion, TipoRiesgo

GALLETA = "dispositivo"


def _huella(request):
    """(huella, identificador nuevo o None). El identificador vive en una cookie del teléfono."""
    identificador = request.COOKIES.get(GALLETA)
    nuevo = None
    if not identificador:
        identificador = nuevo = secrets.token_urlsafe(24)
    return reglas.huella_de(identificador), nuevo


def _con_galleta(respuesta, nuevo):
    if nuevo:
        respuesta.set_cookie(
            GALLETA, nuevo, max_age=365 * 86400, httponly=True, samesite="Lax", secure=not settings.DEBUG
        )
    return respuesta


def _configuracion():
    return {
        "centro": settings.MAPA_CENTRO,
        "zoom": settings.MAPA_ZOOM,
        "baseInicial": settings.MAPA_BASE_INICIAL,
        "capasUrl": settings.CAPAS_URL,
        "capasVariante": settings.CAPAS_VARIANTE,
        "capasSiempreGrupos": settings.CAPAS_SIEMPRE_GRUPOS,
        "capasApagadasAlAbrir": settings.CAPAS_APAGADAS_AL_ABRIR,
        "estaticos": settings.STATIC_URL,
        "vivos": "/api/reportes/vivos.geojson",
        "cerca": reverse("reportes:cerca"),
        "lluvia": reverse("reportes:lluvia"),
        "ficha": "/mapa/r/",
        "reportar": reverse("reportes:reportar"),
    }


@ensure_csrf_cookie
@require_GET
def mapa(request):
    return render(
        request,
        "reportes/mapa.html",
        {"tipos": TipoRiesgo.objects.filter(activo=True), "configuracion": _configuracion()},
    )


def _numero(valor):
    try:
        return float(valor)
    except (TypeError, ValueError):
        return None


@ensure_csrf_cookie
@require_http_methods(["GET", "POST"])
def reportar(request):
    if request.method == "GET":
        return render(
            request,
            "reportes/reportar.html",
            {
                "tipos": TipoRiesgo.objects.filter(activo=True),
                "profundidades": Profundidad.choices,
                "gravedades": Gravedad.choices,
                "configuracion": _configuracion(),
            },
        )

    huella, nuevo = _huella(request)
    hace_una_hora = timezone.now() - timedelta(hours=1)
    if Reporte.objects.filter(huella=huella, creado_en__gt=hace_una_hora).count() >= settings.LIMITE_REPORTES_HORA:
        return JsonResponse({"error": "Ya enviaste muchos reportes en la última hora. Si es una emergencia, llama al 911."}, status=429)

    tipo = TipoRiesgo.objects.filter(codigo=request.POST.get("tipo"), activo=True).first()
    if not tipo:
        return JsonResponse({"error": "Elige qué está pasando."}, status=400)

    foto = ubicacion_foto = None
    if request.FILES.get("foto"):
        try:
            foto, ubicacion_foto = fotos.procesar(request.FILES["foto"])
        except Exception:
            return JsonResponse({"error": "No pude leer la foto. Prueba con otra."}, status=400)

    lat, lon = _numero(request.POST.get("lat")), _numero(request.POST.get("lon"))
    if lat is None or lon is None:
        if not ubicacion_foto:
            return JsonResponse({"error": "Falta la ubicación. Mueve el pin al lugar."}, status=400)
        lat, lon = ubicacion_foto
    if not (-2 <= lat <= 2 and -92.5 <= lon <= -88.5):
        return JsonResponse({"error": "Ese punto está fuera de Galápagos."}, status=400)

    profundidad = request.POST.get("profundidad")
    if profundidad not in Profundidad.values:
        profundidad = Profundidad.SIN_DATO
    gravedad = request.POST.get("gravedad")
    if gravedad not in Gravedad.values:
        gravedad = reglas.gravedad_sugerida(profundidad)

    # Un reporte hecho sin señal llega después con la hora en que se vio.
    ahora = timezone.now()
    visto_en = ahora
    try:
        declarado = datetime.fromisoformat(request.POST.get("visto_en", "").replace("Z", "+00:00"))
        if ahora - timedelta(hours=24) <= declarado <= ahora:
            visto_en = declarado
    except ValueError:
        pass

    punto = Point(lon, lat, srid=4326)
    precision = _numero(request.POST.get("precision"))
    resultado = reglas.crear_reporte(
        tipo=tipo,
        punto=punto,
        huella=huella,
        visto_en=visto_en,
        gravedad=gravedad,
        profundidad=profundidad,
        foto=foto,
        nota=(request.POST.get("nota") or "").strip()[:280],
        precision_m=round(precision) if precision and precision < 100000 else None,
        zona=zona_de(punto),
    )
    r = resultado.reporte
    return _con_galleta(
        JsonResponse(
            {
                "id": r.id_publico,
                "duplicado": resultado.duplicado,
                "lon": r.punto.x,
                "lat": r.punto.y,
                "url": reverse("reportes:ficha", args=[r.id_publico]),
            },
            status=200 if resultado.duplicado else 201,
        ),
        nuevo,
    )


def _contexto_ficha(reporte, huella=None, mensaje=""):
    return {
        "r": reporte,
        "sigue": reporte.confirmaciones.filter(tipo=TipoConfirmacion.SIGUE_AHI).count(),
        "bajo": reporte.confirmaciones.filter(tipo=TipoConfirmacion.YA_BAJO).count(),
        "mensaje": mensaje,
        "ahora": timezone.now(),
    }


@require_GET
def ficha(request, id_publico):
    reporte = get_object_or_404(Reporte.objects.select_related("tipo", "zona"), id_publico=id_publico)
    plantilla = "parciales/ficha.html" if request.headers.get("HX-Request") else "reportes/ficha.html"
    return render(request, plantilla, _contexto_ficha(reporte))


@require_POST
def confirmar(request, id_publico):
    reporte = get_object_or_404(Reporte, id_publico=id_publico)
    tipo = request.POST.get("tipo")
    if tipo not in TipoConfirmacion.values:
        raise Http404
    huella, nuevo = _huella(request)
    hace_poco = timezone.now() - timedelta(minutes=10)
    if reporte.confirmaciones.filter(huella=huella, tipo=tipo, fecha__gt=hace_poco).exists():
        mensaje = "Ya lo anotamos. Gracias."
    else:
        reporte = reglas.confirmar(reporte, tipo, huella)
        mensaje = "Gracias. Renovamos el aviso." if tipo == TipoConfirmacion.SIGUE_AHI else "Gracias por avisar."
    reporte = Reporte.objects.select_related("tipo", "zona").get(pk=reporte.pk)
    respuesta = render(request, "parciales/ficha.html", _contexto_ficha(reporte, huella, mensaje))
    respuesta["HX-Trigger"] = "reportes-cambiaron"
    return _con_galleta(respuesta, nuevo)


@require_GET
def cerca(request):
    """Lista de lo que hay cerca de un punto, para la hoja inferior."""
    lat, lon = _numero(request.GET.get("lat")), _numero(request.GET.get("lon"))
    if lat is None or lon is None:
        lon, lat = settings.MAPA_CENTRO
    punto = Point(lon, lat, srid=4326)
    reportes = (
        Reporte.objects.vivos()
        .select_related("tipo", "zona")
        .filter(punto__distance_lte=(punto, D(m=settings.CERCA_METROS)))
        .annotate(distancia=Distance("punto", punto))
        .order_by("distancia")[:30]
    )
    return render(request, "parciales/cerca.html", {"reportes": reportes, "ahora": timezone.now()})


@require_GET
def lluvia(request):
    lat, lon = _numero(request.GET.get("lat")), _numero(request.GET.get("lon"))
    if lat is None or lon is None:
        lon, lat = settings.MAPA_CENTRO
    return render(request, "parciales/lluvia.html", {"lluvia": clima.nivel(clima.zona_por_punto(lon, lat))})


@cache_control(max_age=3600)
def manifiesto_app(request):
    e = settings.STATIC_URL
    return JsonResponse(
        {
            "name": "SOS Galápagos · Mapa de riesgos",
            "short_name": "SOS Galápagos",
            "description": "Reportes ciudadanos de lugares de riesgo. Información preliminar, no oficial.",
            "lang": "es",
            "start_url": "/mapa/",
            "scope": "/mapa/",
            "display": "standalone",
            "background_color": "#ffffff",
            "theme_color": "#ffffff",
            "icons": [
                {"src": f"{e}app/icono-192.png", "sizes": "192x192", "type": "image/png"},
                {"src": f"{e}app/icono-512.png", "sizes": "512x512", "type": "image/png", "purpose": "any maskable"},
            ],
        },
        content_type="application/manifest+json",
    )


def service_worker(request):
    """Se sirve desde /mapa/ para que su alcance cubra todo el mapa."""
    respuesta = render(request, "reportes/sw.js", {"estaticos": settings.STATIC_URL}, content_type="text/javascript")
    respuesta["Cache-Control"] = "no-cache"
    return respuesta


def copia_de_mapas(request, ruta):
    """Solo en la Mac: sirve lo que publica /mapas, bajándolo una vez del sitio.

    En el servidor esta vista no existe: /mapas lo sirve Caddy desde el repo de datos.
    Los archivos de descarga (zip) no se copian: se manda al sitio publicado.
    """
    import mimetypes
    import re
    from urllib.request import Request, urlopen

    if not settings.DEBUG or not re.fullmatch(r"[\w@./-]+", ruta) or ".." in ruta:
        raise Http404
    if ruta.startswith("descargas/"):
        return HttpResponseRedirect(settings.CAPAS_ORIGEN + ruta)
    # Cada publicación de /mapas tiene su versión (?v=…). La copia se guarda por versión,
    # para que un modelo actualizado por otro equipo no quede tapado por una copia vieja.
    version = request.GET.get("v", "")
    if version and not re.fullmatch(r"[\w-]{1,80}", version):
        raise Http404
    sin_version = settings.CAPAS_COPIA / ruta
    local = settings.CAPAS_COPIA / "v" / version / ruta if version else sin_version
    es_indice = ruta in ("capas.json", "descargas.json", "version.txt")
    if not local.exists() or es_indice:
        try:
            pedido = Request(settings.CAPAS_ORIGEN + ruta, headers={"User-Agent": "sosgalapagos-plataforma (desarrollo local)"})
            with urlopen(pedido, timeout=30) as respuesta:
                datos = respuesta.read()
            local.parent.mkdir(parents=True, exist_ok=True)
            local.write_bytes(datos)
        except Exception:
            if not local.exists():
                if not sin_version.exists():  # sin red y sin copia
                    raise Http404
                local = sin_version  # lo generado en la Mac y aún no publicado (p. ej. teselas/relieve3d)
    tipo = "application/geo+json" if ruta.endswith(".geojson") else mimetypes.guess_type(ruta)[0] or "application/octet-stream"
    return FileResponse(local.open("rb"), content_type=tipo)

# SOS Galápagos · © 2026 Universidad San Francisco de Quito (USFQ) · Autor: Julián Maya <jamaya@usfq.edu.ec>
# Todos los derechos reservados. Usar, copiar, modificar o derivar de este código requiere permiso escrito del autor (ver LICENSE).
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
from django.views.decorators.csrf import csrf_exempt, ensure_csrf_cookie
from django.views.static import serve
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from zonas.models import zona_de

from . import avisos, clima, fotos, reglas
from .models import Gravedad, Profundidad, Reporte, SuscripcionPush, TipoConfirmacion, TipoRiesgo

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
        "relieveUrl": settings.RELIEVE_URL,
        "capasUrl": settings.CAPAS_URL,
        "capasVariante": settings.CAPAS_VARIANTE,
        "capasSiempreGrupos": settings.CAPAS_SIEMPRE_GRUPOS,
        "capasApagadasAlAbrir": settings.CAPAS_APAGADAS_AL_ABRIR,
        "estaticos": settings.STATIC_URL,
        "vivos": "/riesgos/api/reportes/vivos.geojson",
        "cerca": reverse("reportes:cerca"),
        "lluvia": reverse("reportes:lluvia"),
        "ficha": "/riesgos/r/",
        "reportar": reverse("reportes:reportar"),
        "mapa": reverse("reportes:mapa"),
        "pushPublica": settings.PUSH_PUBLICA if avisos.activos() else "",
        "pushSuscribir": reverse("reportes:push_suscribir"),
        "todos": "/riesgos/api/reportes/vivos.geojson?periodo=evento",
        "lluviaHoraria": "/riesgos/api/lluvia.json",
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

    # Un lugar que recibe donaciones lleva un teléfono al que llamar antes de ir.
    import re

    contacto = re.sub(r"[^\d+ ]", "", request.POST.get("contacto") or "").strip()[:40]
    if tipo.pide_contacto and len(re.sub(r"\D", "", contacto)) < 7:
        return JsonResponse({"error": "Pon un teléfono de contacto del lugar, para que la gente llame antes de ir."}, status=400)
    if not tipo.pide_contacto:
        contacto = ""

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
        contacto=contacto,
        nombre_autor=request.POST.get("nombre") or "",
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
                "puntos": resultado.puntos,
                "total": resultado.colaborador.puntos if resultado.colaborador else resultado.puntos,
                "nombre": resultado.colaborador.nombre if resultado.colaborador else "",
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


@require_GET
def informe(request):
    """Línea del tiempo: todos los reportes y cuánto ha llovido, con filtros."""
    return render(request, "reportes/informe.html", {"configuracion": _configuracion()})


@require_GET
def descargas(request):
    """Todas las capas del mapa para descargar, en Shapefile y GeoJSON."""
    return render(request, "reportes/descargas.html", {"configuracion": _configuracion()})


@cache_control(max_age=3600)
def manifiesto_app(request):
    """El manifiesto de la app. Cubre todo el sitio: portada, riesgos y clima son una sola app."""
    e = settings.STATIC_URL
    return JsonResponse(
        {
            "id": "/riesgos/",  # se mantiene el de la primera versión: quien ya la instaló conserva su app
            "name": "SOS Galápagos",
            "short_name": "SOS Galápagos",
            "description": "Mapa de riesgos, clima en vivo y avisos de la emergencia en Galápagos. Información preliminar, no oficial.",
            "lang": "es",
            "start_url": "/riesgos/",
            "scope": "/",
            "display": "standalone",
            "background_color": "#ffffff",
            "theme_color": "#ffffff",
            "icons": [
                {"src": f"{e}app/icono-192.png", "sizes": "192x192", "type": "image/png"},
                {"src": f"{e}app/icono-512.png", "sizes": "512x512", "type": "image/png", "purpose": "any maskable"},
            ],
            "shortcuts": [
                {"name": "Reportar", "url": "/riesgos/reportar/"},
                {"name": "Clima en vivo", "url": "/clima/"},
                {"name": "Ver como lista", "url": "/riesgos/informe/"},
            ],
        },
        content_type="application/manifest+json",
    )


def app_cargador(request):
    """/riesgos/app.js: lo que enlazan las páginas. Es un cargador mínimo que casi nunca cambia.

    Cloudflare le pone cuatro horas de caché en el navegador a todo lo que termina en .js,
    diga lo que diga el servidor. Por eso el componente de verdad se sirve en /riesgos/app/,
    sin extensión, y este archivo solo lo llama: así un cambio llega al instante.
    """
    codigo = "(function(){if(window.__sosCargador)return;window.__sosCargador=true;var s=document.createElement('script');s.src='%s';s.defer=true;document.head.appendChild(s);})();" % reverse("reportes:app_js")
    return HttpResponse(codigo, content_type="text/javascript")


def app_js(request):
    """Componente «Instalar la app» y «Recibir avisos», para cualquier página del sitio."""
    from clima import alertas

    respuesta = render(
        request,
        "reportes/app.js",
        {
            "push_publica": settings.PUSH_PUBLICA if avisos.activos() else "",
            "suscribir": reverse("reportes:push_suscribir"),
            "manifiesto": reverse("reportes:manifiesto_app"),
            "temas": json.dumps([{"id": k, "nombre": v, "por_defecto": k in alertas.POR_DEFECTO} for k, v in alertas.TEMAS.items()], ensure_ascii=False),
            "zonas": json.dumps([{"id": k, "nombre": v} for k, v in alertas.ZONAS.items()], ensure_ascii=False),
        },
        content_type="text/javascript",
    )
    respuesta["Cache-Control"] = "no-cache"
    return respuesta


def service_worker(request):
    """Se sirve desde /riesgos/ para que su alcance cubra todo el mapa."""
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


@require_GET
def relieve(request, ruta):
    """Teselas de cota para la vista 3D. Las teselas de solo mar no existen: responden 404."""
    respuesta = serve(request, ruta, document_root=settings.RELIEVE_DIR)
    # No cambian hasta que se regeneran: el navegador y Cloudflare pueden guardarlas un día.
    respuesta["Cache-Control"] = "public, max-age=86400"
    return respuesta


@require_GET
def tiempo(request):
    """Prototipo: el mapa animado de Windy con lluvia, viento y olas."""
    return render(request, "reportes/tiempo.html", {"llave": settings.WINDY_MAPA_LLAVE})


@require_GET
def puntos(request):
    """Tabla de puntos: quién ha publicado más. Solo el nombre o apodo que cada persona eligió."""
    huella, _ = _huella(request)
    return render(
        request,
        "reportes/puntos.html",
        {"tabla": reglas.tabla_de_puntos(), "yo": reglas.colaborador_de(huella), "valores": settings.PUNTOS},
    )


@csrf_exempt  # se llama también desde la portada y desde /clima/, que no tienen la cookie de este formulario
@require_POST
def push_suscribir(request):
    """Guarda (o retira) la suscripción de este navegador a los avisos.

    Solo se acepta desde páginas del propio sitio. Lo único que guarda es la dirección de
    entrega que da el navegador; al suscribirse se manda un aviso de prueba.
    """
    from urllib.parse import urlparse

    origen = request.headers.get("Origin") or request.headers.get("Referer") or ""
    if not settings.DEBUG and urlparse(origen).netloc != request.get_host():
        return JsonResponse({"error": "origen no permitido"}, status=403)
    try:
        datos = json.loads(request.body or b"{}")
    except ValueError:
        return JsonResponse({"error": "datos ilegibles"}, status=400)
    direccion = str(datos.get("endpoint") or "")
    if not direccion.startswith("https://") or len(direccion) > 2000:
        return JsonResponse({"error": "suscripción inválida"}, status=400)
    from clima import alertas

    if datos.get("baja"):
        SuscripcionPush.objects.filter(direccion=direccion).delete()
        return JsonResponse({"suscrito": False})
    actual = SuscripcionPush.objects.filter(direccion=direccion).first()
    if datos.get("consulta"):  # qué tiene elegido este teléfono
        return JsonResponse({"suscrito": bool(actual), "temas": (actual.temas if actual else None) or alertas.POR_DEFECTO, "zonas": actual.zonas if actual else []})
    # Cada quien elige de qué enterarse y de qué islas; lo que no se reconoce se ignora.
    preferencias = {}
    if isinstance(datos.get("temas"), list):
        preferencias["temas"] = [t for t in datos["temas"] if t in alertas.TEMAS]
    if isinstance(datos.get("zonas"), list):
        preferencias["zonas"] = [z for z in datos["zonas"] if z in alertas.ZONAS]
    if actual and preferencias and not datos.get("keys"):
        SuscripcionPush.objects.filter(pk=actual.pk).update(**preferencias)
        return JsonResponse({"suscrito": True, **preferencias})
    llaves = datos.get("keys") or {}
    if not llaves.get("p256dh") or not llaves.get("auth"):
        return JsonResponse({"error": "suscripción inválida"}, status=400)
    huella, nuevo = _huella(request)
    suscripcion, _ = SuscripcionPush.objects.update_or_create(
        direccion=direccion, defaults={"p256dh": str(llaves["p256dh"])[:200], "auth": str(llaves["auth"])[:80], "huella": huella, **preferencias}
    )
    if not suscripcion.temas:
        suscripcion.temas = list(alertas.POR_DEFECTO)
        suscripcion.save(update_fields=["temas"])
    from .tareas import avisar_bienvenida

    avisar_bienvenida.enqueue(suscripcion.pk)  # confirma a la persona que los avisos le llegan
    return _con_galleta(JsonResponse({"suscrito": True, "temas": suscripcion.temas, "zonas": suscripcion.zonas}), nuevo)

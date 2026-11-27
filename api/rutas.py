# SOS Galápagos · © 2026 Universidad San Francisco de Quito (USFQ) · Autor: Julián Maya <jamaya@usfq.edu.ec>
# Licencia Apache 2.0 (ver LICENSE y NOTICE): puede reutilizarse dando crédito.
"""API pública. En la fase 1 solo trae la salida GeoJSON que usa el mapa.

La forma Open311 (tipos, crear y consultar reportes) y las llaves llegan en la fase 2.
"""
import hashlib
import json
from datetime import datetime, timedelta
from datetime import timezone as dt_timezone

from django.http import HttpResponse
from django.utils import timezone
from ninja import NinjaAPI

from reportes.models import Estado, Reporte

api = NinjaAPI(
    title="SOS Galápagos · Reportes de riesgo",
    version="0.1",
    description=("Información ciudadana preliminar, no oficial. Emergencias: 911. "
                 "© 2026 Universidad San Francisco de Quito (USFQ) · SOS Galápagos · autor: Julián Maya (jamaya@usfq.edu.ec). "
                 "Datos y modelos propios bajo CC BY 4.0, con atribución; los datos de terceros conservan la licencia de su fuente. "
                 "Código bajo Apache 2.0. Si integras esta API en otro producto, da crédito a SOS Galápagos · USFQ · Julián Maya."),
    docs_url="/docs",
)

INICIO_EVENTO = datetime(2026, 10, 30, 6, 0, tzinfo=dt_timezone.utc)


def _propiedades(r):
    return {
        "id": r.id_publico,
        "tipo": r.tipo.codigo,
        "tipo_nombre": r.tipo.nombre,
        "titulo": r.titulo,
        "clase": r.tipo.clase,  # riesgo, bueno o ayuda
        "icono": r.tipo.icono,
        "gravedad": r.gravedad,
        "profundidad": r.profundidad,
        "estado": r.estado,
        "fuente": r.fuente,
        "zona": r.zona.nombre if r.zona else "",
        "isla": r.zona.isla if r.zona else "",
        # Segundos desde 1970: el mapa calcula la edad sin volver a pedir datos.
        "visto": int(r.visto_en.timestamp()),
        "vence": int(r.vence_en.timestamp()),
    }


@api.get("/lluvia.json", summary="Lluvia por hora de una estación", tags=["informe"])
def lluvia(request, desde: datetime, hasta: datetime, estacion: str = ""):
    """Lluvia medida por hora, tal como la publica /clima. Datos preliminares, no oficiales.

    Devuelve también la lista de estaciones con serie de lluvia. Como máximo, 62 días.
    """
    from reportes import clima

    desde = desde if desde.tzinfo else desde.replace(tzinfo=dt_timezone.utc)
    hasta = hasta if hasta.tzinfo else hasta.replace(tzinfo=dt_timezone.utc)
    hasta = min(hasta, desde + timedelta(days=62))
    estaciones = clima.estaciones_con_lluvia()
    inicio, mm = clima.lluvia_por_hora(estacion, desde, hasta) if estacion else (None, [])
    return {
        "estaciones": estaciones,
        "estacion": estacion,
        "inicio": inicio.isoformat().replace("+00:00", "Z") if inicio else None,
        "mm": mm,
        "nota": "Lluvia medida, preliminar y no oficial. Las horas sin transmisión van sin dato: los totales son mínimos.",
    }


@api.get("/oficiales.json", summary="El último documento oficial de cada institución", tags=["informe"])
def oficiales(request):
    """INAMHI, SNGR (SITREP), INOCAR y lo que coordinación suba de los GAD y del COE. Cada uno con su resumen y el
    enlace al documento original, que es el que vale. `todos` lleva a la línea del tiempo filtrada."""
    from reportes import cronica

    return cronica.ultimos_oficiales()


@api.get("/sucesos.json", summary="Sucesos de la línea del tiempo", tags=["informe"])
def sucesos(request, desde: datetime = None, hasta: datetime = None):
    """Lo que pasó y no es un punto del mapa: avisos enviados a los teléfonos (o retenidos de noche),
    boletines oficiales, noticias e informes. `zonas` vacío significa todo Galápagos."""
    from reportes import cronica

    return {"sucesos": cronica.sucesos(desde, hasta)}


@api.get("/reportes/vivos.geojson", summary="Reportes en el mapa", tags=["mapa"])
def vivos(request, periodo: str = "ahora"):
    """Reportes como GeoJSON.

    - `ahora`: solo los vivos.
    - `24h`: además, los cerrados en las últimas 24 horas.
    - `evento`: además, todos los cerrados del evento.
    """
    ahora = timezone.now()
    # El historial de la coordinación anterior nunca sale en el mapa, en ningún período.
    consulta = Reporte.objects.del_mapa().select_related("tipo", "zona")
    if periodo == "24h":
        consulta = consulta.filter(visto_en__gt=ahora - timedelta(hours=24))
    elif periodo == "evento":
        consulta = consulta.filter(visto_en__gt=INICIO_EVENTO)
    else:
        consulta = consulta.vivos(ahora)

    elementos = []
    for r in consulta.filter(fusionado_en__isnull=True)[:5000]:
        p = _propiedades(r)
        if r.estado != Estado.CERRADO and r.vence_en <= ahora:
            p["estado"] = Estado.CERRADO  # venció y la tarea aún no lo marcó
        elementos.append(
            {"type": "Feature", "geometry": {"type": "Point", "coordinates": [round(r.punto.x, 6), round(r.punto.y, 6)]}, "properties": p}
        )
    cuerpo = json.dumps({"type": "FeatureCollection", "features": elementos}, separators=(",", ":"))
    etiqueta = '"' + hashlib.md5(cuerpo.encode()).hexdigest() + '"'
    if request.headers.get("If-None-Match") == etiqueta:
        return HttpResponse(status=304, headers={"ETag": etiqueta})
    return HttpResponse(cuerpo, content_type="application/geo+json", headers={"ETag": etiqueta, "Cache-Control": "no-cache"})


@api.get("/reportes/historial.json", summary="Historial de la coordinación anterior", tags=["informe"])
def historial(request):
    """Lo que publicó la plataforma de coordinación anterior (ResponseGrid) del 1 al 4 de noviembre de 2026:
    refugios, centros de acopio, entregas y pedidos de ayuda. Está cerrado y no sale en el mapa: solo en la
    línea del tiempo. Sin datos personales; los pedidos sensibles van con la ubicación aproximada (unos 500 m)."""
    elementos = []
    for r in Reporte.objects.historial().select_related("tipo", "zona")[:2000]:
        p = _propiedades(r)
        p["nota"] = r.nota if r.contenido_visible else ""
        elementos.append({"type": "Feature", "geometry": {"type": "Point", "coordinates": [round(r.punto.x, 6), round(r.punto.y, 6)]}, "properties": p})
    return HttpResponse(json.dumps({"type": "FeatureCollection", "features": elementos}, separators=(",", ":")),
                        content_type="application/geo+json", headers={"Cache-Control": "public, max-age=300"})


# ── WhatsApp: lo que manda el servidor OpenWA cuando llega un mensaje ────────
def openwa_forma(o, nivel=0):
    """La estructura de un dato sin su contenido: de un texto solo queda su largo."""
    if isinstance(o, dict):
        return {k: openwa_forma(v, nivel + 1) for k, v in list(o.items())[:40]} if nivel < 5 else "{…}"
    if isinstance(o, list):
        return [openwa_forma(o[0], nivel + 1)] if o else []
    if isinstance(o, str):
        # Los valores cortos de estos campos no son personales y dicen cómo leer el mensaje.
        return f"texto({len(o)})"
    return type(o).__name__


@api.post("/whatsapp/entrada", summary="Mensaje entrante de WhatsApp", tags=["interno"], include_in_schema=False)
def whatsapp_entrada(request, secreto: str = ""):
    """Recibe el aviso del servidor de WhatsApp, descarta lo que no toca y encola el resto.

    Responde enseguida: el trabajo con el modelo de lenguaje va en segundo plano.
    """
    import hmac

    from django.conf import settings

    from entradas import flujo
    from entradas.tareas import procesar_mensaje

    esperado = settings.WHATSAPP_SECRETO
    dado = request.headers.get("X-Secreto") or secreto
    if not esperado or not hmac.compare_digest(dado.encode(), esperado.encode()):
        return api.create_response(request, {"error": "no autorizado"}, status=403)
    try:
        carga = json.loads(request.body or b"{}")
    except ValueError:
        return api.create_response(request, {"error": "se esperaba JSON"}, status=400)
    if settings.WHATSAPP_MODO == "ensayo":
        # En ensayo se anota la forma de lo que llega (nombres de campo y tipos, nunca el contenido):
        # sirve para ajustar el lector al formato real del servidor de WhatsApp.
        import logging

        logging.getLogger("entradas").warning("forma del webhook: %s", json.dumps(openwa_forma(carga), ensure_ascii=False)[:1500])
    mensaje = flujo.recibir(carga)
    if mensaje:
        procesar_mensaje.enqueue(mensaje.pk)
    return {"atendido": bool(mensaje)}


@api.post("/ingesta/whatsapp", summary="Elemento de la entrada horaria de WhatsApp", tags=["interno"], include_in_schema=False)
def ingesta_whatsapp(request):
    """Recibe un elemento ya limpio de la Mac de coordinación (despliegue/ingesta/). Pide la llave en X-Llave.

    Solo crea: un punto en el mapa si trae ubicación segura, o una foto en «Ayúdanos a ubicar».
    """
    import hmac

    from django.conf import settings

    from entradas import ingesta

    llave = settings.INGESTA_LLAVE
    if not llave or not hmac.compare_digest(request.headers.get("X-Llave", "").encode(), llave.encode()):
        return api.create_response(request, {"error": "no autorizado"}, status=403)
    try:
        return ingesta.recibir(request.POST, request.FILES.get("foto"))
    except ingesta.Rechazo as e:
        return api.create_response(request, {"error": str(e)}, status=e.estado)


# ── Clima: mediciones guardadas en esta base ─────────────────────────────────
@api.get("/clima/estaciones", summary="Estaciones meteorológicas y su lluvia reciente", tags=["clima"])
def clima_estaciones(request):
    """Mediciones preliminares de terceros, no oficiales. Cada estación cita su operador."""
    from clima import consultas

    return {"estaciones": consultas.estaciones()}


@api.get("/clima/serie", summary="Serie por hora o por día de una estación", tags=["clima"])
def clima_serie(request, estacion: str, variable: str = "lluvia_mm", desde: datetime = None, hasta: datetime = None, paso: str = "hora"):
    """`estacion` es «fuente/código». `paso` es «hora» o «dia» (día de Galápagos). Como máximo, un año."""
    from clima import consultas

    hasta = hasta or timezone.now()
    desde = desde or hasta - timedelta(days=3)
    desde = desde if desde.tzinfo else desde.replace(tzinfo=dt_timezone.utc)
    hasta = hasta if hasta.tzinfo else hasta.replace(tzinfo=dt_timezone.utc)
    if variable not in ("lluvia_mm", "temp_c", "hr_pct", "presion_hpa", "viento_ms", "nivel_mar_m", "rad_wm2") or paso not in ("hora", "dia"):
        return api.create_response(request, {"error": "variable o paso desconocido"}, status=400)
    datos = consultas.serie(estacion, variable, max(desde, hasta - timedelta(days=366)), hasta, paso)
    if datos is None:
        return api.create_response(request, {"error": "estación desconocida"}, status=404)
    return datos


@api.get("/clima/salud", summary="Salud de las fuentes de clima", tags=["clima"])
def clima_salud(request):
    """Qué fuentes responden, cuánto tardan y hace cuánto llegó la última medición."""
    from clima import consultas

    return consultas.salud()


@api.get("/clima/pronostico/verificacion", summary="Acierto del pronóstico de lluvia fuerte", tags=["clima"])
def clima_verificacion(request, dias: int = 45):
    """Lo pronosticado frente a lo que llovió. Verificación automática y preliminar, no oficial."""
    from clima import pronostico

    return pronostico.verificar(max(7, min(dias, 365)))


@api.get("/clima/pronostico", summary="Lluvia fuerte en los próximos días, por punto", tags=["clima"])
def clima_pronostico(request):
    """Lo publicado, lo recalibrado con las últimas semanas y lo que dicen los modelos. Experimental, no oficial."""
    from clima import pronostico

    return pronostico.proximos_dias()


@api.get("/clima/mar", summary="Mareas y estado del mar por puerto", tags=["clima"])
def clima_mar(request):
    """Pleamares y bajamares (tabla oficial del INOCAR cuando la hay) y oleaje pronosticado. No reemplaza los avisos de la Armada."""
    from clima import mar

    return mar.resumen()


@api.get("/clima/oficial", summary="Pronóstico y boletines oficiales", tags=["clima"])
def clima_oficial(request):
    """Lo que publican el INAMHI y el INOCAR. Los resúmenes los escribe un modelo de lenguaje: el documento oficial manda."""
    from clima import oficiales
    from clima.models import PronosticoOficial

    hoy = timezone.now().astimezone(dt_timezone(timedelta(hours=-6))).date()
    return {
        "aviso": "Resúmenes automáticos de documentos oficiales. Pueden tener errores: abre siempre el documento de la institución.",
        "boletines": oficiales.vigentes(),
        "pronostico_inamhi": [
            {"isla": p.isla, "fecha": p.fecha, "minima_c": p.minima_c, "maxima_c": p.maxima_c, "periodos": p.periodos, "lluvia_horas": p.lluvia_horas, "obtenido": p.obtenido}
            for p in PronosticoOficial.objects.filter(fecha__gte=hoy).order_by("isla", "fecha")
        ],
    }


@api.get("/clima/alertas", summary="Temas de alerta a los que alguien se puede suscribir", tags=["clima"])
def clima_alertas(request):
    from clima import alertas
    from clima.models import AvisoEnviado

    return {
        "temas": [{"id": k, "nombre": v, "por_defecto": k in alertas.POR_DEFECTO} for k, v in alertas.TEMAS.items()],
        "zonas": [{"id": k, "nombre": v} for k, v in alertas.ZONAS.items()],
        "ultimos": [{"tema": a.tema, "zona": a.zona, "titulo": a.titulo, "cuerpo": a.cuerpo, "enlace": a.enlace, "creado": a.creado} for a in AvisoEnviado.objects.all()[:10]],
    }


@api.get("/clima/lluvia-mapa.json", summary="Rejilla de lluvia y viento de los modelos, para el mapa animado", tags=["clima"])
def clima_lluvia_mapa(request, horas: int = 0):
    """Lo que dibuja el mapa de lluvia y viento (lo genera clima/lluvia_mapa.py cada vez que hay corrida nueva).
    Son modelos, no mediciones ni un pronóstico oficial.

    Con `horas` (de 6 a 72) devuelve solo lo necesario para animar ese tramo desde ahora con el modelo ECMWF:
    es lo que pide la portada, y pesa unas diez veces menos."""
    from pathlib import Path

    from django.conf import settings
    from django.http import FileResponse

    from clima import lluvia_mapa

    ruta = Path(settings.CLIMA_SALIDA or ".") / "lluvia-mapa.json"
    if not settings.CLIMA_SALIDA or not ruta.exists():
        return api.create_response(request, {"error": "todavía no hay mapa"}, status=404)
    if not horas:
        return FileResponse(open(ruta, "rb"), content_type="application/json", headers={"Cache-Control": "public, max-age=300"})
    try:
        datos = lluvia_mapa.recorte(json.loads(ruta.read_text(encoding="utf-8")), timezone.now(), horas=max(6, min(72, horas)))
    except (ValueError, KeyError, TypeError):
        datos = None
    if datos is None:
        return api.create_response(request, {"error": "el mapa no cubre las próximas horas"}, status=404)
    return HttpResponse(json.dumps(datos, ensure_ascii=False, separators=(",", ":")), content_type="application/json",
                        headers={"Cache-Control": "public, max-age=300"})


def _archivo_clima(request, nombre, falta):
    """Sirve un JSON que la plataforma dejó en CLIMA_SALIDA (el servidor web no deja pasar archivos nuevos bajo /clima/)."""
    from pathlib import Path

    from django.conf import settings
    from django.http import FileResponse

    ruta = Path(settings.CLIMA_SALIDA or ".") / nombre
    if not settings.CLIMA_SALIDA or not ruta.exists():
        return api.create_response(request, {"error": falta}, status=404)
    return FileResponse(open(ruta, "rb"), content_type="application/json", headers={"Cache-Control": "public, max-age=900"})


@api.get("/clima/nino.json", summary="El Niño: índices de la NOAA, mar alrededor de Galápagos, boyas, MJO y el último boletín ERFEN", tags=["clima"])
def clima_nino(request):
    """Lo genera clima/nino.py cada seis horas. Los índices y el satélite son contexto; la voz oficial es el ERFEN."""
    return _archivo_clima(request, "nino.json", "todavía no hay datos de El Niño")


@api.get("/clima/nino_mapa.json", summary="Rejillas de anomalía de temperatura y nivel del mar para el mapa de El Niño", tags=["clima"])
def clima_nino_mapa(request):
    """Lo genera clima/nino.py. Datos de satélite de la NOAA: contexto, no dato oficial."""
    return _archivo_clima(request, "nino_mapa.json", "todavía no hay mapa de El Niño")


@api.get("/clima/zcit.json", summary="ZCIT y ondas tropicales cerca de Galápagos (discusión del NHC)", tags=["clima"])
def clima_zcit(request):
    """Lo genera clima/zcit.py con la discusión del Centro Nacional de Huracanes de la NOAA. Contexto, no aviso oficial."""
    return _archivo_clima(request, "zcit.json", "todavía no hay análisis de la ZCIT")


@api.get("/clima/pdirnow.json", summary="Lluvia estimada por satélite (PDIR-Now) sobre Galápagos, últimas horas", tags=["clima"])
def clima_pdirnow(request):
    """Lo genera clima/satelite/pdir.py (servicio «satelite»). Estimación por infrarrojo, no medida ni oficial:
    no ve la garúa ni la lluvia de nubes bajas. No entra en la señal satelital ni en el nivel de lluvia."""
    from pathlib import Path

    from django.conf import settings
    from django.http import FileResponse

    ruta = Path(settings.CLIMA_SALIDA or ".") / "pdirnow.json"
    if not settings.CLIMA_SALIDA or not ruta.exists():
        return api.create_response(request, {"error": "todavía no hay lluvia estimada"}, status=404)
    return FileResponse(open(ruta, "rb"), content_type="application/json", headers={"Cache-Control": "public, max-age=300"})


@api.get("/clima/satelite-capas", summary="Fondo del mapa del satélite: horas disponibles de la imagen GeoColor", tags=["clima"])
def clima_satelite_capas(request):
    """Plantilla de teselas y horas (UTC, cada 10 min, últimas 3 h disponibles) de la imagen GeoColor de GOES-East
    que sirve NASA GIBS. Es una imagen del satélite, no un dato de lluvia. Sin GIBS, `tiempos` viene vacío."""
    from clima.satelite import gibs

    r = api.create_response(request, gibs.capas(), status=200)
    r["Cache-Control"] = "public, max-age=300"
    return r


@api.get("/clima/nivel", summary="Nivel de lluvia peligrosa por zona", tags=["clima"])
def clima_nivel(request):
    """El nivel vigente de cada zona. Es una estimación propia y preliminar, no una alerta oficial."""
    from clima.models import Estado

    e = Estado.objects.filter(clave="inundacion").first()
    return {"aviso": "Estimación propia y preliminar a partir de la lluvia medida. No es una alerta oficial: sigue las indicaciones del COE, la SNGR y el ECU 911.",
            **(e.datos if e else {"zonas": []})}


@api.get("/clima/relevo/ierse", summary="Relevo de IERSE: qué pedir", tags=["clima"], include_in_schema=False)
def clima_relevo_pedidos(request):
    """Para la máquina de relevo en Ecuador: la lista de pedidos que debe hacerle a IERSE ahora."""
    from clima import relevo

    if not relevo.autorizado(request):
        return api.create_response(request, {"error": "no autorizado"}, status=403)
    return relevo.pedidos()


@api.post("/clima/relevo/ierse", summary="Relevo de IERSE: entregar respuestas", tags=["clima"], include_in_schema=False)
def clima_relevo_entrega(request):
    from clima import relevo

    if not relevo.autorizado(request):
        return api.create_response(request, {"error": "no autorizado"}, status=403)
    return relevo.recibir(request.body)

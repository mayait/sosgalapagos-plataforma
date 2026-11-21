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
    description="Información ciudadana preliminar, no oficial. Emergencias: 911.",
    docs_url="/docs",
)

INICIO_EVENTO = datetime(2026, 10, 30, 6, 0, tzinfo=dt_timezone.utc)


def _propiedades(r):
    return {
        "id": r.id_publico,
        "tipo": r.tipo.codigo,
        "tipo_nombre": r.tipo.nombre,
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


@api.get("/reportes/vivos.geojson", summary="Reportes en el mapa", tags=["mapa"])
def vivos(request, periodo: str = "ahora"):
    """Reportes como GeoJSON.

    - `ahora`: solo los vivos.
    - `24h`: además, los cerrados en las últimas 24 horas.
    - `evento`: además, todos los cerrados del evento.
    """
    ahora = timezone.now()
    consulta = Reporte.objects.select_related("tipo", "zona")
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

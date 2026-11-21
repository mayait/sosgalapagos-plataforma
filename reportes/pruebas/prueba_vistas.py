"""Pruebas del formulario, la ficha y la salida GeoJSON."""
import json
from io import BytesIO

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from PIL import Image

from reportes import fotos
from reportes.models import Estado, Reporte

pytestmark = pytest.mark.django_db

DATOS = {"tipo": "agua_via", "lat": "-0.7435", "lon": "-90.3145", "profundidad": "rodilla"}


def foto_con_gps():
    imagen = Image.new("RGB", (40, 30), "navy")
    exif = imagen.getexif()
    gps = exif.get_ifd(fotos.ETIQUETA_GPS)
    gps[1], gps[2], gps[3], gps[4] = "S", (0, 44, 36.6), "W", (90, 18, 52.2)
    exif[fotos.ETIQUETA_GPS] = gps
    salida = BytesIO()
    imagen.save(salida, "JPEG", exif=exif)
    return SimpleUploadedFile("foto.jpg", salida.getvalue(), content_type="image/jpeg")


def prueba_crear_un_reporte_desde_el_formulario(client):
    respuesta = client.post("/riesgos/reportar/", DATOS)
    assert respuesta.status_code == 201
    r = Reporte.objects.get(id_publico=respuesta.json()["id"])
    assert r.tipo.codigo == "agua_via"
    assert r.gravedad == "no_pasar"  # sugerida por la profundidad «rodilla»
    assert r.estado == Estado.POR_VERIFICAR


def prueba_el_reporte_aparece_enseguida_en_el_geojson(client):
    nuevo = client.post("/riesgos/reportar/", DATOS).json()["id"]
    datos = json.loads(client.get("/riesgos/api/reportes/vivos.geojson").content)
    assert [f["properties"]["id"] for f in datos["features"]] == [nuevo]


def prueba_el_geojson_responde_sin_cambios_si_nada_cambio(client):
    client.post("/riesgos/reportar/", DATOS)
    primera = client.get("/riesgos/api/reportes/vivos.geojson")
    segunda = client.get("/riesgos/api/reportes/vivos.geojson", headers={"If-None-Match": primera["ETag"]})
    assert segunda.status_code == 304


def prueba_el_geojson_no_trae_nota_ni_foto(client):
    client.post("/riesgos/reportar/", {**DATOS, "nota": "Casa de Fulano"})
    assert b"Fulano" not in client.get("/riesgos/api/reportes/vivos.geojson").content


def prueba_sin_tipo_o_fuera_de_galapagos_se_rechaza(client):
    assert client.post("/riesgos/reportar/", {**DATOS, "tipo": ""}).status_code == 400
    assert client.post("/riesgos/reportar/", {**DATOS, "lat": "-2.19", "lon": "-79.88"}).status_code == 400
    assert Reporte.objects.count() == 0


def prueba_la_foto_se_guarda_sin_metadatos_y_da_la_ubicacion(client, settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    respuesta = client.post("/riesgos/reportar/", {"tipo": "agua_via", "foto": foto_con_gps()})
    assert respuesta.status_code == 201
    r = Reporte.objects.get()
    assert abs(r.punto.y - (-0.7435)) < 0.001 and abs(r.punto.x - (-90.3145)) < 0.001
    guardada = Image.open(r.foto.path)
    assert not guardada.getexif()  # ni ubicación ni modelo de teléfono


def prueba_la_ficha_oculta_la_nota_hasta_que_coordinacion_la_ve(client):
    ident = client.post("/riesgos/reportar/", {**DATOS, "nota": "Vive la familia Pérez"}).json()["id"]
    assert "Pérez" not in client.get(f"/riesgos/r/{ident}/").content.decode()
    Reporte.objects.update(contenido_visible=True)
    assert "Pérez" in client.get(f"/riesgos/r/{ident}/").content.decode()


def prueba_dos_ya_bajo_desde_dos_telefonos_cierran_el_reporte(client):
    from django.test import Client

    ident = client.post("/riesgos/reportar/", DATOS).json()["id"]
    Client().post(f"/riesgos/r/{ident}/confirmar/", {"tipo": "ya_bajo"})
    assert Reporte.objects.get().estado == Estado.BAJANDO
    Client().post(f"/riesgos/r/{ident}/confirmar/", {"tipo": "ya_bajo"})
    assert Reporte.objects.get().estado == Estado.CERRADO


def prueba_el_mismo_telefono_no_cierra_solo(client):
    ident = client.post("/riesgos/reportar/", DATOS).json()["id"]
    client.post(f"/riesgos/r/{ident}/confirmar/", {"tipo": "ya_bajo"})
    client.post(f"/riesgos/r/{ident}/confirmar/", {"tipo": "ya_bajo"})
    assert Reporte.objects.get().estado == Estado.BAJANDO


def prueba_limite_de_reportes_por_dispositivo(client, settings):
    settings.LIMITE_REPORTES_HORA = 2
    for i in range(2):
        assert client.post("/riesgos/reportar/", {**DATOS, "lat": str(-0.74 - i * 0.01)}).status_code == 201
    assert client.post("/riesgos/reportar/", {**DATOS, "lat": "-0.70"}).status_code == 429


def prueba_el_mapa_nunca_dice_zona_segura(client):
    pagina = client.get("/riesgos/").content.decode().lower()
    assert "zona segura" not in pagina
    assert "sin reportes activos" in pagina


def prueba_el_mapa_lee_las_capas_de_lo_que_publica_mapas(client):
    # Principio de /mapas: toda capa se enciende, se apaga y se descarga.
    # Para eso el panel usa el mismo manifiesto y el mismo índice de descargas.
    configuracion = client.get("/riesgos/").context["configuracion"]
    assert configuracion["capasUrl"] == "/mapas/"
    assert configuracion["capasVariante"] == "completo"
    # El riesgo modelado y las quebradas arrancan encendidos también en el teléfono.
    assert {"lluvia", "hidrografia"} <= set(configuracion["capasSiempreGrupos"])


def prueba_el_mapa_abre_en_satelite(client):
    assert client.get("/riesgos/").context["configuracion"]["baseInicial"] == "satelite"


def prueba_los_informes_publicados_se_enlazan_y_lo_mal_formado_se_descarta(client, settings, tmp_path):
    (tmp_path / "indice.json").write_text(json.dumps({"informes": [
        {"archivo": "mapa-riesgo.pdf", "portada": "mapa-riesgo.jpg", "titulo": "Mapa de riesgo de Puerto Ayora", "fecha": "2026-11-21", "paginas": 4, "tamano": "2 MB"},
        {"archivo": "../secreto.pdf", "titulo": "Ruta que se sale de la carpeta", "fecha": "2026-11-21"},
        {"archivo": "sin-fecha.pdf", "titulo": "Sin fecha"},
    ]}))
    settings.INFORMES_DIR = tmp_path
    pagina = client.get("/riesgos/informes/").content.decode()
    assert "Mapa de riesgo de Puerto Ayora" in pagina and "/descargas/mapa-riesgo.pdf" in pagina
    assert "secreto" not in pagina and "Sin fecha" not in pagina


def prueba_sin_indice_de_informes_no_se_muestra_la_seccion(client, settings, tmp_path):
    settings.INFORMES_DIR = tmp_path / "no-existe"
    assert client.get("/riesgos/informes/").content.strip() == b""

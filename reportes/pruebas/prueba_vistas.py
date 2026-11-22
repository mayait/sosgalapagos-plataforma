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


def prueba_el_mapa_abre_en_calles(client):
    assert client.get("/riesgos/").context["configuracion"]["baseInicial"] == "calles"


def prueba_el_mapa_no_lista_los_informes_en_pdf(client):
    # Los informes y mapas en PDF van solo en la portada del sitio.
    assert "informes" not in client.get("/riesgos/").content.decode().replace("/riesgos/informe/", "")
    assert client.get("/riesgos/informes/").status_code == 404


def prueba_el_relieve_del_3d_se_sirve_y_el_mar_da_404(client, settings, tmp_path):
    (tmp_path / "cota" / "8" / "63").mkdir(parents=True)
    (tmp_path / "teselas.json").write_text('{"cota": {"codificacion": "terrarium"}}')
    (tmp_path / "cota" / "8" / "63" / "128.png").write_bytes(b"png")
    settings.RELIEVE_DIR = tmp_path
    assert client.get("/riesgos/relieve3d/teselas.json").status_code == 200
    tesela = client.get("/riesgos/relieve3d/cota/8/63/128.png")
    assert tesela.status_code == 200 and "max-age" in tesela["Cache-Control"]
    assert client.get("/riesgos/relieve3d/cota/8/1/1.png").status_code == 404
    assert client.get("/riesgos/relieve3d/../ajustes.py").status_code in (400, 404)  # nada fuera de la carpeta


def prueba_se_puede_avisar_algo_bueno_y_donde_donar(client):
    bueno = client.post("/riesgos/reportar/", {"tipo": "algo_bueno", "lat": "-0.7408", "lon": "-90.3152", "nota": "Volvió la luz"})
    ayuda = client.post("/riesgos/reportar/", {"tipo": "donar_colaborar", "lat": "-0.7428", "lon": "-90.3108", "contacto": "05 252 0000"})
    assert bueno.status_code == 201 and ayuda.status_code == 201
    datos = json.loads(client.get("/riesgos/api/reportes/vivos.geojson").content)
    assert sorted(f["properties"]["clase"] for f in datos["features"]) == ["ayuda", "bueno"]
    ficha = client.get(f"/riesgos/r/{bueno.json()['id']}/").content.decode()
    assert "Ya no está" in ficha and "No pasar" not in ficha and "Pasar con cuidado" not in ficha


def prueba_los_peligros_siguen_llevando_su_clase(client):
    client.post("/riesgos/reportar/", DATOS)
    datos = json.loads(client.get("/riesgos/api/reportes/vivos.geojson").content)
    assert datos["features"][0]["properties"]["clase"] == "riesgo"


def prueba_el_formulario_ofrece_camara_y_galeria(client):
    pagina = client.get("/riesgos/reportar/").content.decode()
    assert 'capture="environment"' in pagina          # cámara
    assert pagina.count('type="file"') == 2            # y otra entrada sin «capture»: galería
    assert "Elegir de la galería" in pagina


def prueba_las_paginas_de_informe_y_descargas_abren(client):
    informe = client.get("/riesgos/informe/").content.decode()
    assert "Línea del tiempo" in informe and "Estación de lluvia" not in informe and "no es información oficial" in informe
    descargas = client.get("/riesgos/descargas/").content.decode()
    assert "Shapefile y GeoJSON" in descargas and "no datos oficiales" in descargas
    mapa = client.get("/riesgos/").content.decode()
    assert "/riesgos/informe/" in mapa and "/riesgos/descargas/" in mapa


def prueba_la_lluvia_por_hora_se_recorta_al_periodo(client, monkeypatch):
    from reportes import clima

    monkeypatch.setattr(clima, "horario", lambda: {"inicio": "2026-11-21T00:00:00Z", "series": {"a/uno": {"lluvia_mm": [0, 1.5, None, 4, 9]}}})
    monkeypatch.setattr(clima, "estado", lambda: {"estaciones": [{"fuente": "a", "estacion": "uno", "nombre": "Uno", "isla": "Santa Cruz"}]})
    d = client.get("/riesgos/api/lluvia.json", {"desde": "2026-11-21T01:00:00Z", "hasta": "2026-11-21T03:00:00Z", "estacion": "a/uno"}).json()
    assert d["mm"] == [1.5, None, 4] and d["inicio"] == "2026-11-21T01:00:00Z"
    assert d["estaciones"] == [{"id": "a/uno", "nombre": "Uno", "isla": "Santa Cruz"}]
    sin = client.get("/riesgos/api/lluvia.json", {"desde": "2026-11-21T01:00:00Z", "hasta": "2026-11-21T03:00:00Z", "estacion": "no/existe"}).json()
    assert sin["mm"] == [] and sin["inicio"] is None


def prueba_el_geojson_dice_la_isla(client):
    from zonas.models import Zona
    from django.contrib.gis.geos import Polygon

    Zona.objects.create(nombre="Las Acacias", isla="Santa Cruz", geometria=Polygon.from_bbox((-90.32, -0.75, -90.31, -0.74)))
    client.post("/riesgos/reportar/", DATOS)
    p = json.loads(client.get("/riesgos/api/reportes/vivos.geojson?periodo=evento").content)["features"][0]["properties"]
    assert p["isla"] == "Santa Cruz" and p["zona"] == "Las Acacias"


def prueba_crear_aviso_de_coordinacion_con_titulo_fotos_y_plazo_largo(client, settings, tmp_path):
    from datetime import timedelta

    from django.core.management import call_command
    from django.utils import timezone

    settings.MEDIA_ROOT = tmp_path / "medios"
    fotos_dir = tmp_path / "entrada"
    fotos_dir.mkdir()
    for n in (1, 2):
        (fotos_dir / f"{n}.jpg").write_bytes(foto_con_gps().read())
    call_command(
        "crear_aviso", tipo="donar_colaborar", lat=-0.89553, lon=-89.60884, titulo="Centro de acopio USFQ San Cristóbal",
        nota="Se reciben víveres empacados y kits de higiene.", dias=14, foto=[str(fotos_dir / "1.jpg"), str(fotos_dir / "2.jpg")],
    )
    r = Reporte.objects.get()
    assert r.estado == Estado.CONFIRMADO and r.contenido_visible and r.tipo.icono == "corazon"
    assert r.vence_en > timezone.now() + timedelta(days=13)
    assert r.fotos_extra.count() == 1 and not Image.open(r.fotos_extra.get().foto.path).getexif()
    ficha = client.get(f"/riesgos/r/{r.id_publico}/").content.decode()
    assert "Centro de acopio USFQ San Cristóbal" in ficha and ficha.count("data-foto=") == 2
    p = json.loads(client.get("/riesgos/api/reportes/vivos.geojson").content)["features"][0]["properties"]
    assert p["titulo"] == "Centro de acopio USFQ San Cristóbal" and p["icono"] == "corazon" and p["clase"] == "ayuda"


@pytest.mark.django_db
def prueba_el_mapa_trae_buscador_y_enlaces_del_pie(client):
    """/riesgos/ es el mapa único: lleva el buscador, «Mis puntos» y, bajo la firma, los enlaces."""
    html = client.get("/riesgos/").content.decode()
    assert 'id="buscar-abrir"' in html and 'id="mis-puntos"' in html
    assert "mapa/buscar.js" in html
    pie = html[html.index('class="firma"'):]
    assert 'href="/clima/"' in pie
    assert 'href="/riesgos/descargas/"' in pie
    assert "github.com/mayait/sosgalapagos-plataforma" in pie
    # El visor de /mapas ya no se enlaza: de /mapas/ solo se leen los datos.
    assert 'href="/mapas/"' not in html


@pytest.mark.django_db
def prueba_el_informe_se_llama_linea_del_tiempo(client):
    html = client.get("/riesgos/informe/").content.decode()
    assert "<h1 class=\"form-titulo\">Línea del tiempo</h1>" in html
    assert 'id="g-nav"' in html and 'id="saltos"' in html  # navegador para moverse rápido en el tiempo
    assert "no es información oficial" in html


@pytest.mark.django_db
def prueba_el_mapa_ofrece_ver_como_lista(client):
    html = client.get("/riesgos/").content.decode()
    assert ">Ver como lista</a>" in html


# ── Fase 2: puntos, contacto, daño en infraestructura, avisos ────────────────
def prueba_publicar_suma_puntos_y_guarda_el_nombre(client):
    r = client.post("/riesgos/reportar/", {**DATOS, "nombre": "  Lucía  "})
    assert r.status_code == 201
    d = r.json()
    assert d["puntos"] == 10 and d["total"] == 10 and d["nombre"] == "Lucía"
    # Avisar de lo mismo, ahí mismo, confirma y suma menos.
    d2 = client.post("/riesgos/reportar/", DATOS).json()
    assert d2["duplicado"] and d2["puntos"] == 2 and d2["total"] == 12
    tabla = client.get("/riesgos/puntos/").content.decode()
    assert "Lucía" in tabla and "<b>12</b>" in tabla


def prueba_la_tabla_no_muestra_a_quien_no_dio_nombre_ni_telefonos(client):
    client.post("/riesgos/reportar/", DATOS)
    otro = client.__class__()
    otro.post("/riesgos/reportar/", {**DATOS, "lat": "-0.7300", "nombre": "0991234567"})  # un teléfono no es un nombre
    from reportes.models import Colaborador

    assert Colaborador.objects.count() == 2 and not Colaborador.objects.exclude(nombre="").exists()
    assert "Todavía no hay nadie" in client.get("/riesgos/puntos/").content.decode()


def prueba_un_lugar_de_donacion_pide_telefono_de_contacto(client):
    sin = client.post("/riesgos/reportar/", {"tipo": "donar_colaborar", "lat": "-0.7428", "lon": "-90.3108"})
    assert sin.status_code == 400 and "teléfono de contacto" in sin.json()["error"]
    con = client.post("/riesgos/reportar/", {"tipo": "donar_colaborar", "lat": "-0.7428", "lon": "-90.3108", "contacto": "099-123-4567"})
    r = Reporte.objects.get(id_publico=con.json()["id"])
    assert r.contacto == "0991234567"
    # El teléfono, como la nota, no se ve hasta que coordinación lo revisa.
    assert "0991234567" not in client.get(f"/riesgos/r/{r.id_publico}/").content.decode()
    Reporte.objects.filter(pk=r.pk).update(contenido_visible=True)
    assert 'href="tel:0991234567"' in client.get(f"/riesgos/r/{r.id_publico}/").content.decode()


def prueba_un_peligro_no_guarda_contacto(client):
    r = client.post("/riesgos/reportar/", {**DATOS, "contacto": "0991234567"})
    assert Reporte.objects.get(id_publico=r.json()["id"]).contacto == ""


def prueba_el_dano_en_infraestructura_dura_dias(client):
    r = client.post("/riesgos/reportar/", {"tipo": "dano_infraestructura", "lat": "-0.7435", "lon": "-90.3145", "nota": "Puente con la baranda caída"})
    assert r.status_code == 201
    reporte = Reporte.objects.get(id_publico=r.json()["id"])
    assert (reporte.vence_en - reporte.visto_en).days == 14
    assert "Daño en infraestructura pública" in client.get("/riesgos/reportar/").content.decode()


def prueba_el_formulario_explica_la_ubicacion(client):
    pagina = client.get("/riesgos/reportar/").content.decode()
    assert "pedirGps(true)" in pagina and "gps-aviso" in pagina
    assert "Tu nombre o apodo" in pagina and "Teléfono de contacto del lugar" in pagina


def prueba_suscribirse_y_darse_de_baja_de_los_avisos(client, monkeypatch):
    from reportes import tareas
    from reportes.models import SuscripcionPush

    monkeypatch.setattr(tareas, "avisar_bienvenida", type("Tarea", (), {"enqueue": staticmethod(lambda pk: None)}))
    client.defaults["HTTP_ORIGIN"] = "http://testserver"  # el navegador siempre dice desde qué sitio llama

    datos = {"endpoint": "https://push.ejemplo.test/abc", "keys": {"p256dh": "BPk", "auth": "xyz"}}
    assert client.post("/riesgos/avisos/suscribir/", json.dumps(datos), content_type="application/json").json()["suscrito"] is True
    client.post("/riesgos/avisos/suscribir/", json.dumps(datos), content_type="application/json")  # dos veces no duplica
    assert SuscripcionPush.objects.count() == 1
    mala = client.post("/riesgos/avisos/suscribir/", json.dumps({"endpoint": "http://sin-cifrar"}), content_type="application/json")
    assert mala.status_code == 400
    client.post("/riesgos/avisos/suscribir/", json.dumps({**datos, "baja": True}), content_type="application/json")
    assert SuscripcionPush.objects.count() == 0


def prueba_sin_llaves_no_se_ofrecen_avisos_y_no_se_envia_nada(client, settings):
    from reportes import avisos

    settings.PUSH_PUBLICA = settings.PUSH_PRIVADA = ""
    assert avisos.enviar("t", "c", "/riesgos/") == 0
    assert '"pushPublica": ""' in client.get("/riesgos/").content.decode()


def prueba_el_mapa_ofrece_la_app_y_los_puntos(client):
    html = client.get("/riesgos/").content.decode()
    assert "data-sos-app" in html and 'src="/riesgos/app.js"' in html and ">Puntos</a>" in html and 'href="/clima/"' in html
    sw = client.get("/riesgos/sw.js").content.decode()
    assert "addEventListener('push'" in sw and "notificationclick" in sw


def prueba_el_componente_de_la_app_sirve_en_todo_el_sitio(client, settings):
    settings.PUSH_PUBLICA, settings.PUSH_PRIVADA = "BPublica", "privada"
    js = client.get("/riesgos/app.js")
    assert js["Content-Type"].startswith("text/javascript") and js["Cache-Control"] == "no-cache"
    codigo = js.content.decode()
    assert "publica: 'BPublica'" in codigo and "/riesgos/avisos/suscribir/" in codigo
    # En iPhone el permiso hay que pedirlo antes de esperar a nada más.
    assert codigo.index("Notification.requestPermission()") < codigo.index("await registro()")
    manifiesto = client.get("/riesgos/app.webmanifest").json()
    assert manifiesto["scope"] == "/" and manifiesto["start_url"] == "/riesgos/"
    assert {a["url"] for a in manifiesto["shortcuts"]} >= {"/clima/", "/riesgos/reportar/"}
    for pagina in ("/riesgos/informe/", "/riesgos/puntos/", "/riesgos/descargas/"):
        assert "data-sos-app" in client.get(pagina).content.decode()


def prueba_suscribirse_desde_la_portada_manda_un_aviso_de_prueba(client, monkeypatch, settings):
    from django.test import Client

    from reportes import tareas
    from reportes.models import SuscripcionPush

    enviados = []
    monkeypatch.setattr(tareas, "avisar_bienvenida", type("Tarea", (), {"enqueue": staticmethod(enviados.append)}))
    settings.DEBUG = False
    sin_csrf = Client(enforce_csrf_checks=True)  # la portada no tiene la cookie del formulario
    datos = json.dumps({"endpoint": "https://push.ejemplo.test/portada", "keys": {"p256dh": "BPk", "auth": "xyz"}})
    ajeno = sin_csrf.post("/riesgos/avisos/suscribir/", datos, content_type="application/json", headers={"Origin": "https://otro-sitio.test"})
    assert ajeno.status_code == 403
    propio = sin_csrf.post("/riesgos/avisos/suscribir/", datos, content_type="application/json", headers={"Origin": "http://testserver"})
    assert propio.json()["suscrito"] is True
    assert enviados == [SuscripcionPush.objects.get().pk]

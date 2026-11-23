# SOS Galápagos · © 2026 Universidad San Francisco de Quito (USFQ) · Autor: Julián Maya <jamaya@usfq.edu.ec>
# Licencia Apache 2.0 (ver LICENSE y NOTICE): puede reutilizarse dando crédito.
"""Pruebas de la portada, la privacidad, las rutas de la raíz y las redirecciones de ResponseGrid."""
import json
from datetime import timedelta

import pytest
from django.utils import timezone

from clima.models import Boletin
from portada.models import Aviso, Organizacion, Situacion

pytestmark = pytest.mark.django_db


def prueba_la_portada_responde_en_la_raiz(client):
    r = client.get("/")
    pagina = r.content.decode()
    assert r.status_code == 200
    for texto in ("Gestión de emergencias", "Sociedad Civil Galápagos", 'href="tel:911"', "Mapa de riesgos", "Reportar", "Clima", "Lluvia y viento",
                  "Línea del tiempo", "Si necesitas ayuda", "Si quieres ayudar", "No envíes donaciones físicas desde el continente",
                  'id="informes"', 'id="organizaciones"', 'id="mascotas"', "Magma Galápagos", "/privacidad"):
        assert texto in pagina, texto
    assert "albergue" not in pagina.lower()
    assert "zona segura" not in pagina.lower()


def prueba_la_migracion_carga_el_contenido_actual_sin_cedulas(client):
    assert Situacion.objects.filter(tema="Refugio").exists()
    assert Organizacion.objects.filter(nombre="Fundación Pan Animalia Galápagos", categoria="mascotas").exists()
    pagina = client.get("/").content.decode()
    assert "Revisado el miércoles 4 de noviembre, 07:00" in pagina
    assert "1757800683" not in pagina and "Walthert" not in pagina  # cuenta personal de Patitas: no se publica


def prueba_el_aviso_vencido_no_sale_y_el_vigente_si(client):
    # El de la migración (21 de noviembre) ya venció.
    assert "Hoy, sábado 21 de noviembre" not in client.get("/").content.decode()
    Aviso.objects.create(titulo="Aviso vencido de prueba", hasta=timezone.now() - timedelta(minutes=1))
    Aviso.objects.create(titulo="Aviso apagado de prueba", hasta=timezone.now() + timedelta(hours=3), activo=False)
    Aviso.objects.create(titulo="No necesitamos más ropa", hasta=timezone.now() + timedelta(hours=3))
    pagina = client.get("/").content.decode()
    assert "No necesitamos más ropa" in pagina
    assert "Aviso vencido de prueba" not in pagina and "Aviso apagado de prueba" not in pagina


def _boletin(**campos):
    ahora = timezone.now()
    datos = {"fuente": "inamhi", "tipo": "advertencia", "huella": str(campos), "numero": "89", "titulo": "Advertencia meteorológica n.º 89",
             "vigente_desde": ahora - timedelta(hours=5), "vigente_hasta": ahora + timedelta(days=1), "afecta_galapagos": True, "nivel": "rojo",
             "resumen": "Lluvia fuerte en Galápagos.", "enlace": "https://example.org/advertencia.pdf"}
    datos.update(campos)
    return Boletin.objects.create(**datos)


def prueba_la_advertencia_vigente_sale_y_la_vencida_no(client):
    _boletin(titulo="Advertencia vencida", huella="a", vigente_hasta=timezone.now() - timedelta(hours=1))
    _boletin(titulo="Advertencia del continente", huella="b", afecta_galapagos=False)
    assert 'id="advertencia"' not in client.get("/").content.decode()
    _boletin(huella="c")
    pagina = client.get("/").content.decode()
    assert 'id="advertencia"' in pagina and "Advertencia meteorológica n.º 89" in pagina
    assert "rojo" in pagina and "https://example.org/advertencia.pdf" in pagina and "hora de Galápagos" in pagina
    assert "Advertencia vencida" not in pagina and "Advertencia del continente" not in pagina


def prueba_los_informes_salen_del_indice_y_sin_rutas_raras(client, settings, tmp_path):
    assert "Todavía no hay informes" in client.get("/").content.decode()
    (tmp_path / "indice.json").write_text(json.dumps({"informes": [
        {"archivo": "atlas.pdf", "titulo": "Atlas de Santa Cruz", "fecha": "2026-11-21", "paginas": 14},
        {"archivo": "../secreto.pdf", "titulo": "No debe salir", "fecha": "2026-11-22"},
    ]}), encoding="utf-8")
    settings.INFORMES_DIR = str(tmp_path)
    pagina = client.get("/").content.decode()
    assert 'href="/descargas/atlas.pdf"' in pagina and "21 de noviembre de 2026" in pagina
    assert "No debe salir" not in pagina


def prueba_una_sola_privacidad(client):
    pagina = client.get("/privacidad").content.decode()
    for texto in ("Julián Maya", "jamaya@usfq.edu.ec", "Qué datos recogemos", "Con quién los compartimos", "Cuánto tiempo",
                  "Tus derechos", "Superintendencia de Protección de Datos Personales", "fines comerciales", "No te vamos a contactar",
                  "Cloudflare", "OpenStreetMap", "Esri", "NASA GIBS", "modelo de lenguaje", "ResponseGrid", "fuera de línea", 'id="derechos"'):
        assert texto in pagina, texto
    assert "Human Centric" not in pagina
    assert client.get("/riesgos/privacidad/")["Location"] == "/privacidad"
    assert client.get("/eliminar-datos")["Location"] == "/privacidad#derechos"


def prueba_el_formulario_dice_para_que_sirve_el_reporte(client):
    pagina = client.get("/riesgos/reportar/").content.decode()
    assert "Para qué sirve tu reporte" in pagina and "No te vamos a contactar" in pagina and 'href="/privacidad"' in pagina


@pytest.mark.parametrize("vieja,nueva", [
    ("/e/galapagos-2026", "/riesgos/"), ("/e/galapagos-2026/", "/riesgos/"), ("/e/galapagos-2026/reportar", "/riesgos/reportar/"),
    ("/e/galapagos-2026/donar", "/#organizaciones"), ("/e/galapagos-2026/peticion", "/#ayuda"), ("/e/galapagos-2026/voluntario", "/#grupos-whatsapp"),
    ("/e/galapagos-2026/recursos/abc", "/riesgos/"), ("/login", "/"), ("/signup", "/"), ("/panel/grupos", "/"), ("/auth/complete", "/"),
    ("/dashboard", "/"), ("/admin/users", "/"), ("/transparencia", "/"), ("/sobre", "/"), ("/funcionalidades", "/"), ("/como-funciona", "/"),
    ("/verificar", "/"), ("/docs", "/riesgos/api/docs"), ("/peticion", "/#ayuda"), ("/voluntario", "/#ayuda"), ("/offline", "/"),
])
def prueba_las_rutas_de_responsegrid_redirigen(client, vieja, nueva):
    r = client.get(vieja)
    assert r.status_code == 301 and r["Location"] == nueva


def prueba_las_rutas_de_la_raiz(client):
    assert "Sitemap:" in client.get("/robots.txt").content.decode()
    mapa = client.get("/sitemap.xml").content.decode()
    for ruta in ("/</loc>", "/riesgos/</loc>", "/clima/</loc>", "/riesgos/informe/</loc>", "/privacidad</loc>"):
        assert ruta in mapa, ruta
    assert client.get("/icon.svg")["Content-Type"] == "image/svg+xml"
    assert "unregister" in client.get("/sw.js").content.decode()
    assert client.get("/no-existe").status_code == 404
    assert client.get("/riesgos/").status_code == 200  # el mapa sigue en su sitio


def prueba_el_menu_enlaza_la_privacidad(client):
    from reportes import menu

    assert ("Privacidad", "/privacidad", False) in menu.DESTINOS

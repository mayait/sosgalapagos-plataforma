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
    for texto in ("<h1 class=\"pt-titulo\">SOS Galápagos</h1>", "Sociedad Civil Galápagos · USFQ. Lluvias de El Niño en Santa Cruz, San Cristóbal e Isabela.",
                  'href="tel:911"', "Reportar un punto", "Ver el mapa de riesgos", "Ver el clima en vivo", "¿Necesitas ayuda?", "Apoyo ante violencia", "¿Quieres ayudar?",
                  "No mandes cosas desde el continente", "Boletines oficiales", "Todos los documentos oficiales", "Clima completo", "Línea del tiempo",
                  "Lluvia y viento", "Descargar capas", 'id="informes"', 'id="organizaciones"', 'id="mascotas"', 'id="ayuda"', 'id="grupos-whatsapp"',
                  "Magma Galápagos", "/privacidad", "Refugios y puntos de ayuda en el mapa"):
        assert texto in pagina, texto
    assert "albergue" not in pagina.lower()
    # Un solo botón lleno: el rojo de «Reportar un punto».
    assert pagina.count("pt-boton-rojo\"") == 1 and " lleno" not in pagina
    # Fuera: los accesos grandes, «Mapas y clima», las referencias y la probabilidad de lluvia fuerte.
    for fuera in ("pt-acceso", "Mapas y clima", "Publicaciones científicas", "doi.org", "probabilidad", "Gestión de emergencias"):
        assert fuera not in pagina, fuera


def prueba_nunca_zona_segura_ni_sin_riesgo(client):
    pagina = client.get("/").content.decode().lower()
    assert "zona segura" not in pagina and "sin riesgo" not in pagina


def prueba_no_oficial_una_sola_vez(client):
    _boletin(huella="no-oficial")
    pagina = client.get("/").content.decode().lower()
    assert pagina.count("no oficial") == 1


def prueba_sin_los_enlaces_rotos_del_gad_ni_del_coe(client):
    from portada import contenido

    pagina = client.get("/").content.decode()
    assert "gadsantacruz.gob.ec" not in pagina and "docs.google.com/forms" not in pagina
    assert "Registro de damnificados" not in pagina and "Formulario del COE" not in pagina
    assert not hasattr(contenido, "REGISTRO_GAD") and not hasattr(contenido, "FORMULARIO_COE")


def prueba_situacion_hoy_no_sale_con_lineas_vencidas(client):
    # Las de la migración (4 de noviembre) quedaron caducadas.
    assert Situacion.objects.filter(tema="Refugio").exists()
    assert not Situacion.objects.vigentes().exists()
    pagina = client.get("/").content.decode()
    assert "Situación hoy" not in pagina and "Miguel Ángel Cazares" not in pagina
    Situacion.objects.create(tema="Vencida", texto="Ya no vale.", caduca=timezone.now() - timedelta(minutes=1))
    assert "Situación hoy" not in client.get("/").content.decode()
    Situacion.objects.create(tema="Agua", texto="Hay agua en el coliseo.", caduca=timezone.now() + timedelta(hours=6))
    pagina = client.get("/").content.decode()
    assert "Situación hoy" in pagina and "Hay agua en el coliseo." in pagina and "Ya no vale." not in pagina


def prueba_organizaciones_con_donar_primero_y_patitas_con_su_cuenta(client):
    pagina = client.get("/").content.decode()
    usfq = pagina.index("USFQ Galápagos · Galápagos Science Center")
    mas = pagina.index("Más organizaciones (")
    assert usfq < mas and "Donar ↗" in pagina
    assert pagina.index("Fundación Charles Darwin") > mas  # sin canal de donación: plegada
    assert "Ayuda para mascotas (4)" in pagina
    # Julián autorizó publicar la cuenta de Patitas Galapagueñas (23-nov-2026).
    assert "2203496066" in pagina and "Banco Pichincha" in pagina
    assert "No dones a cuentas personales" not in pagina


def prueba_qr_solo_en_computadora(client):
    from django.contrib.staticfiles import finders

    css = open(finders.find("portada/portada.css"), encoding="utf-8").read()
    assert "@media (hover: hover) and (pointer: fine) and (min-width: 900px)" in css
    # Fuera de ese bloque, los QR no se muestran.
    assert ".pt-qr { display: none; }" in css


def prueba_cache_corta_y_sin_cookies(client):
    r = client.get("/")
    assert r["Cache-Control"] == "public, max-age=60, s-maxage=60"
    assert not r.cookies
    assert "Cookie" not in r.get("Vary", "")


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
    pagina = client.get("/").content.decode()
    assert 'id="advertencia"' not in pagina
    assert "El INAMHI no tiene una advertencia vigente para Galápagos." in pagina
    _boletin(huella="c", nivel="naranja intenso", resumen="Resumen escrito por el modelo.")
    pagina = client.get("/").content.decode()
    assert 'id="advertencia"' in pagina and "Advertencia meteorológica n.º 89" in pagina and "INAMHI · advertencia vigente" in pagina
    assert "https://example.org/advertencia.pdf" in pagina and "(hora de Galápagos)" in pagina
    # Sin la palabra del nivel ni el resumen: los lee un modelo y pueden fallar.
    assert "naranja intenso" not in pagina and "Resumen escrito por el modelo." not in pagina
    assert "Advertencia vencida" not in pagina and "Advertencia del continente" not in pagina
    assert "no tiene una advertencia vigente" not in pagina


def prueba_boletines_salen_de_ultimos_oficiales_sin_duplicar(client):
    from reportes.models import Suceso

    ahora = timezone.now()
    _boletin(huella="adv")
    Boletin.objects.create(fuente="inocar", tipo="oleaje", huella="ole", numero="191126", afecta_galapagos=True,
                           resumen="Oleaje moderado en el archipiélago. Segunda frase que no debe salir.", enlace="https://inocar.test/o.png")
    Suceso.objects.create(clase="oficial", institucion="gad-santa-cruz", titulo="Informe del GAD n.º 4", texto="Se reabre la vía a Baltra.",
                          ocurrido=ahora - timedelta(hours=2), enlace="https://gad.test/4.pdf")
    pagina = client.get("/").content.decode()
    assert "INOCAR · Boletín de oleaje" in pagina and "Oleaje moderado en el archipiélago." in pagina
    assert "Segunda frase que no debe salir" not in pagina
    assert "GAD de Santa Cruz · Informe o comunicado" in pagina and "Informe del GAD n.º 4" in pagina and "https://gad.test/4.pdf" in pagina
    assert 'href="/riesgos/informe/?ver=oficial"' in pagina
    # La advertencia del INAMHI va destacada una sola vez, no repetida en las tarjetas.
    assert pagina.count("https://example.org/advertencia.pdf") == 1
    # Un solo bloque de oficiales, ya marcado para que app.js no pinte otro.
    assert pagina.count("data-sos-oficiales") == 1 and 'class="pt-boletines sos-oficiales"' in pagina
    assert 'aria-labelledby="situacion-heading"' not in pagina


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
    assert "Ver todos" not in pagina  # con uno solo no hace falta


def prueba_los_informes_muestran_dos_y_ver_todos(client, settings, tmp_path):
    (tmp_path / "indice.json").write_text(json.dumps({"informes": [
        {"archivo": f"i{n}.pdf", "titulo": f"Informe {n}", "fecha": f"2026-11-1{n}"} for n in range(1, 5)
    ]}), encoding="utf-8")
    settings.INFORMES_DIR = str(tmp_path)
    pagina = client.get("/").content.decode()
    assert pagina.index("Informe 4") < pagina.index("Informe 3") < pagina.index("Ver todos (4)") < pagina.index("Informe 2")


def prueba_una_sola_privacidad(client):
    pagina = client.get("/privacidad").content.decode()
    for texto in ("Julián Maya", "jamaya@usfq.edu.ec", "Qué datos recogemos", "Con quién los compartimos", "Cuánto tiempo",
                  "Tus derechos", "Superintendencia de Protección de Datos Personales", "fines comerciales", "No te vamos a contactar",
                  "Cloudflare", "OpenStreetMap", "Esri", "NASA GIBS", "modelo de lenguaje", "ResponseGrid", "fuera de línea", 'id="derechos"', "En grupos de WhatsApp"):
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


# ── La lluvia de las próximas 24 horas, el orden y los títulos (25-nov-2026) ──────────────

def prueba_la_portada_abre_con_la_lluvia_de_las_proximas_24_horas(client):
    pagina = client.get("/").content.decode()
    assert '<h2 class="pt-h2" id="reel-titulo">Lluvia de las próximas 24 horas</h2>' in pagina
    # La caja trae de dónde sale todo: los datos recortados a 24 horas, las islas y el motor del mapa de lluvia.
    assert 'data-reel data-estado="espera" data-datos="/riesgos/api/clima/lluvia-mapa.json?horas=24"' in pagina
    for trozo in ("portada/islas.json?v=", "mapa/lluvia-mapa.js?v=", "mapa/lluvia-mapa.css?v=", "terceros/leaflet/leaflet.js", "terceros/leaflet/leaflet.css"):
        assert trozo in pagina, trozo
    # Carga diferida: en la página solo va el guion que monta la animación; Leaflet y el motor no se enlazan.
    assert "portada/portada.js?v=" in pagina
    assert '<script src="/riesgos/estaticos/terceros/leaflet' not in pagina and '<script src="/riesgos/estaticos/mapa/lluvia-mapa' not in pagina
    assert '<link rel="stylesheet" href="/riesgos/estaticos/terceros/leaflet' not in pagina
    # Si el pronóstico no carga, la caja dice dónde ver la lluvia medida; no queda un hueco.
    assert "No pudimos cargar el mapa de lluvia de las próximas 24 horas." in pagina and "<noscript>" in pagina
    # Es lluvia de modelo y se dice para qué sirve, sin milímetros ni porcentajes.
    assert "sirve para ver cuándo llueve" in pagina and "Open-Meteo" in pagina and "IGM" in pagina
    assert "%" not in pagina.split('id="lluvia-24h"')[1].split('class="pt-hacer"')[0]


def prueba_el_orden_de_la_portada(client):
    _boletin(huella="orden")
    pagina = client.get("/").content.decode()
    orden = ['id="lluvia-24h"', 'id="ahora"', 'class="pt-acciones"', "</svg>Reportar un punto</a>", "</svg>Ver el mapa de riesgos</a>", "</svg>Ver el clima en vivo</a>",
             'class="pt-tarjeta pt-peligros"', 'id="boletines"', 'id="ayuda"', 'id="quieres-ayudar"', 'id="grupos-whatsapp"', 'id="informes"', 'id="mas"']
    lugares = [pagina.index(t) for t in orden]
    assert lugares == sorted(lugares), list(zip(orden, lugares))


def prueba_los_tres_botones_van_en_mayusculas_y_con_icono(client):
    from django.contrib.staticfiles import finders

    pagina = client.get("/").content.decode()
    botones = pagina.split('<nav class="pt-acciones"')[1].split("</nav>")[0]
    assert botones.count("<a ") == 3 and botones.count("<svg ") == 3
    for clase, destino, texto in (("pt-boton-rojo", "/riesgos/reportar/", "Reportar un punto"), ("pt-boton pt-boton-grande", "/riesgos/", "Ver el mapa de riesgos"),
                                  ("pt-boton pt-boton-grande", "/clima/", "Ver el clima en vivo")):
        assert f'<a class="{clase}" href="{destino}"><svg ' in botones and f"</svg>{texto}</a>" in botones, texto
    css = open(finders.find("portada/portada.css"), encoding="utf-8").read()
    for clase in (".pt-boton-rojo {", ".pt-boton-grande {"):
        assert "text-transform: uppercase" in css.split(clase)[1].split("}")[0], clase


def prueba_los_titulos_de_seccion_miden_lo_mismo(client):
    pagina = client.get("/").content.decode()
    for titulo in ('<h2 class="pt-h2" id="necesitas-titulo">¿Necesitas ayuda?</h2>', '<h2 class="pt-h2" id="boletines-titulo">Boletines oficiales</h2>',
                   '<h3 class="pt-h2 pt-h2-dentro" id="grupos-whatsapp">Únete a una brigada</h3>', '<h2 class="pt-h2" id="informes-titulo">Informes</h2>',
                   '<h2 class="pt-h2" id="mas-titulo">Más</h2>', '<h2 class="pt-h2" id="quieres-titulo">¿Quieres ayudar?</h2>'):
        assert titulo in pagina, titulo


def prueba_el_recorte_de_24_horas_del_mapa_de_lluvia(client, settings, tmp_path):
    from datetime import datetime, timezone as tz

    from clima import lluvia_mapa

    ahora = datetime(2026, 11, 25, 7, 22, tzinfo=tz.utc)   # 01:22 en Galápagos
    horas = [f"2026-11-{24 + h // 24:02d}T{h % 24:02d}:00Z" for h in range(3, 150, 3)]   # del 24 a las 03:00 al 30 a las 03:00, cada 3 h
    modelo = lambda nombre: {"id": nombre, "nombre": nombre, "corrida": "2026-11-24T18:00Z", "lluvia": [f"l{i}" for i in range(len(horas))],
                             "u": [f"u{i}" for i in range(len(horas))], "v": [f"v{i}" for i in range(len(horas))]}
    datos = {"version": 1, "generado": "2026-11-25T02:06Z", "rejilla": {"nlat": 1, "nlon": 1}, "horas": horas, "paso_h": 3, "inicio": 8,
             "modelos": [modelo("gfs_seamless"), modelo("ecmwf_ifs")]}
    r = lluvia_mapa.recorte(datos, ahora)
    # De las 06:00Z (el cuadro anterior a las 07:00Z, para interpolar) a las 12:00Z del día siguiente (uno después de las 24 h).
    assert r["horas"][0] == "2026-11-25T06:00Z" and r["horas"][-1] == "2026-11-26T12:00Z" and len(r["horas"]) == 11
    assert r["ahora"] == "2026-11-25T07:22Z" and r["inicio"] == 1 and r["rejilla"] == datos["rejilla"]
    assert [m["id"] for m in r["modelos"]] == ["ecmwf_ifs"]
    i = horas.index("2026-11-25T06:00Z")
    assert r["modelos"][0]["lluvia"] == [f"l{k}" for k in range(i, i + 11)] and r["modelos"][0]["v"][0] == f"v{i}"
    assert len(datos["horas"]) == 49 and len(datos["modelos"]) == 2   # el original no se toca
    # Si el archivo ya no cubre las próximas horas, no hay recorte.
    assert lluvia_mapa.recorte(datos, datetime(2026, 11, 30, 1, 0, tzinfo=tz.utc)) is None
    assert lluvia_mapa.recorte({"horas": [], "modelos": []}, ahora) is None

    settings.CLIMA_SALIDA = str(tmp_path)
    assert client.get("/riesgos/api/clima/lluvia-mapa.json?horas=24").status_code == 404   # todavía no se generó
    viejo = {**datos, "horas": [h.replace("2026", "2020") for h in horas]}
    (tmp_path / "lluvia-mapa.json").write_text(json.dumps(viejo), encoding="utf-8")
    assert client.get("/riesgos/api/clima/lluvia-mapa.json?horas=24").status_code == 404   # un archivo viejo ya no cubre las próximas horas
    ahora_real = timezone.now().replace(minute=0, second=0, microsecond=0)
    datos["horas"] = [(ahora_real + timedelta(hours=3 * k)).strftime("%Y-%m-%dT%H:%MZ") for k in range(-8, 41)]
    (tmp_path / "lluvia-mapa.json").write_text(json.dumps(datos), encoding="utf-8")
    r = client.get("/riesgos/api/clima/lluvia-mapa.json?horas=24")
    assert r.status_code == 200 and "max-age=300" in r["Cache-Control"]
    j = json.loads(r.content)
    assert len(j["horas"]) <= 11 and [m["id"] for m in j["modelos"]] == ["ecmwf_ifs"] and "ahora" in j
    completo = client.get("/riesgos/api/clima/lluvia-mapa.json")   # sin «horas», el archivo entero, como siempre
    assert len(json.loads(b"".join(completo.streaming_content))["horas"]) == 49

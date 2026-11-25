# SOS Galápagos · © 2026 Universidad San Francisco de Quito (USFQ) · Autor: Julián Maya <jamaya@usfq.edu.ec>
# Licencia Apache 2.0 (ver LICENSE y NOTICE): puede reutilizarse dando crédito.
"""Pruebas de los documentos oficiales: el SITREP de la SNGR, lo último de cada institución y lo que sube coordinación."""
from datetime import datetime, timedelta, timezone

import pytest
from django.core.management import call_command

from clima import alertas, oficiales
from clima.models import AvisoEnviado, Boletin, Corrida
from reportes.models import Suceso

pytestmark = pytest.mark.django_db

PAGINA = """<html><body><ul>
<li><a href="https://sngr.test/uploads/SitRep-No-104-15h.pdf"><strong>SITREP Nacional No. 104 – 29/08/2026 al 23/11/2026- 16h00</strong></a></li>
<li><a href="https://sngr.test/uploads/Infografia-No-104.pdf">Infografía Nacional No. 104</a></li>
<li><a href="https://sngr.test/uploads/SitRep-No-103-10h.pdf">SITREP Nacional No. 103 – 29/08/2026 al 23/11/2026- 12h00</a></li>
<li><a href="https://sngr.test/uploads/SitRep-No-99-PM.docx.pdf">SITREP Nacional No. 99– 29/08/2026 al 20/11/2026- 20h00</a></li>
<li><a href="https://sngr.test/uploads/SITREP-Nro.-02-Orellana.pdf">Informe de Situación No. 02 ORELLANA – Desde el 29/08/2026 al 13/11/2026</a></li>
</ul></body></html>"""
PDF = b"%PDF-1.7 informe de prueba"


def prueba_encuentra_el_sitrep_nacional_mas_reciente():
    u = oficiales.ultimo_sitrep(PAGINA)
    assert u["numero"] == "104" and u["enlace"].endswith("SitRep-No-104-15h.pdf") and u["infografia"].endswith("Infografia-No-104.pdf")
    assert u["emitido"] == datetime(2026, 11, 23, 21, 0, tzinfo=timezone.utc)      # las 16:00 del continente
    assert oficiales.ultimo_sitrep("<html>nada</html>") is None                    # los provinciales no cuentan
    assert oficiales.ultimo_sitrep(PAGINA.replace("104", "9"))["numero"] == "103"  # manda el número, no el orden de la página


@pytest.fixture
def sngr(monkeypatch, settings):
    settings.CLIMA_SNGR_SITREP_URL, settings.IA_MODELO = "https://sngr.test/sitrep/", "prueba"
    bajadas, leidos = [], []
    monkeypatch.setattr(oficiales, "_bajar", lambda url, **k: bajadas.append(url) or (PAGINA.encode() if url.endswith("/sitrep/") else PDF))
    monkeypatch.setattr(oficiales, "leer_documento", lambda contenido, mime, que_es, esquema=None, instrucciones=None: leidos.append(que_es) or oficiales.InformeSituacion(
        nombra_galapagos=True, resumen="En Santa Cruz hay 120 personas afectadas y 35 viviendas con daños. En el país suman 14 000 personas afectadas.",
        personas_afectadas_galapagos=120, viviendas_afectadas_galapagos=35))
    return bajadas, leidos


def prueba_un_sitrep_nuevo_se_baja_se_resume_y_no_se_repite(sngr):
    bajadas, leidos = sngr
    b = oficiales.revisar_sitrep()
    assert (b.fuente, b.tipo, b.numero, b.afecta_galapagos) == ("sngr", "sitrep", "104", True) and "120 personas" in b.resumen
    assert b.enlace.endswith("SitRep-No-104-15h.pdf") and b.datos == {"infografia": "https://sngr.test/uploads/Infografia-No-104.pdf", "personas_afectadas_galapagos": 120, "viviendas_afectadas_galapagos": 35}
    assert b.emitido == datetime(2026, 11, 23, 21, 0, tzinfo=timezone.utc) and "SITREP nacional n.º 104" in leidos[0]
    # La siguiente revisión mira la página y nada más: no vuelve a bajar el PDF ni a llamar al modelo.
    assert oficiales.revisar_sitrep() is None and len(bajadas) == 3 and len(leidos) == 1 and Boletin.objects.count() == 1
    assert Corrida.objects.filter(fuente="boletin_sitrep", ok=True).exists()


def prueba_sin_modelo_el_sitrep_se_guarda_con_su_enlace_y_sin_inventar(sngr, monkeypatch):
    monkeypatch.setattr(oficiales, "leer_documento", lambda *a, **k: None)
    b = oficiales.revisar_sitrep()
    assert b.numero == "104" and b.resumen == "" and not b.afecta_galapagos and not b.extraido_con and b.enlace


def prueba_si_la_pagina_cambia_queda_anotado_como_fallo(sngr, monkeypatch):
    monkeypatch.setattr(oficiales, "_bajar", lambda url, **k: b"<html>en mantenimiento</html>")
    assert oficiales.revisar_sitrep() is None and not Boletin.objects.exists()
    assert not Corrida.objects.get(fuente="boletin_sitrep").ok


def prueba_el_sitrep_no_suena_en_el_telefono_pero_si_va_a_la_linea_del_tiempo(sngr, client, monkeypatch):
    from reportes import clima as panel

    monkeypatch.setattr(panel, "estado", lambda: {})
    monkeypatch.setattr(alertas, "es_de_noche", lambda ahora: False)
    oficiales.revisar_sitrep()
    Boletin.objects.create(fuente="sngr", tipo="sitrep", huella="s" * 64, numero="103", titulo="SITREP nacional n.º 103 · lluvias", afecta_galapagos=False, enlace="https://sngr.test/103.pdf")
    assert alertas.revisar() == [] and not AvisoEnviado.objects.exists()          # sale dos veces al día: no es un aviso
    sucesos = client.get("/riesgos/api/sucesos.json").json()["sucesos"]
    titulos = {s["titulo"]: s for s in sucesos}
    assert set(titulos) == {"SITREP nacional de la SNGR n.º 104", "SITREP nacional de la SNGR n.º 103"}   # aunque uno no nombre a Galápagos
    s = titulos["SITREP nacional de la SNGR n.º 104"]
    assert s["clase"] == "oficial" and s["fuente"] == "SNGR" and s["institucion"] == "sngr" and "120 personas" in s["texto"] and s["enlace"].endswith(".pdf")
    assert s["detalle"] == "resumen automático: el documento oficial es el que vale" and titulos["SITREP nacional de la SNGR n.º 103"]["detalle"] == ""


def prueba_lo_ultimo_de_cada_institucion_para_la_portada(sngr, client):
    ahora = datetime.now(timezone.utc)
    oficiales.revisar_sitrep()
    Boletin.objects.create(fuente="inamhi", tipo="advertencia", huella="a" * 64, numero="88", afecta_galapagos=True, resumen="Vieja.", enlace="https://inamhi.test/88.pdf")
    Boletin.objects.create(fuente="inamhi", tipo="advertencia", huella="b" * 64, numero="89", afecta_galapagos=True, nivel="muy alto", resumen="Lluvias de nivel muy alto.",
                           enlace="https://inamhi.test/89.pdf", vigente_hasta=ahora + timedelta(days=1))
    Boletin.objects.create(fuente="inocar", tipo="oleaje", huella="c" * 64, numero="191126", afecta_galapagos=True, resumen="Oleaje moderado.", enlace="https://inocar.test/o.png")
    Suceso.objects.create(clase="oficial", institucion="gad-santa-cruz", titulo="Informe del GAD n.º 3", texto="Vías cerradas.", ocurrido=ahora - timedelta(days=1), enlace="https://gad.test/3.pdf")
    Suceso.objects.create(clase="oficial", institucion="gad-santa-cruz", titulo="Informe del GAD n.º 4", texto="Se reabre la vía a Baltra.", ocurrido=ahora - timedelta(hours=2), enlace="https://gad.test/4.pdf")
    Suceso.objects.create(clase="oficial", institucion="gad-san-cristobal", titulo="Oculto", visible=False)
    Suceso.objects.create(clase="noticia", institucion="coe", titulo="Una noticia no es un documento oficial")
    d = client.get("/riesgos/api/oficiales.json").json()
    assert d["todos"] == "/riesgos/informe/?ver=oficial"
    assert [(x["institucion"], x["titulo"]) for x in d["documentos"]] == [
        ("inamhi", "Advertencia del INAMHI n.º 89"), ("sngr", "SITREP nacional de la SNGR n.º 104"), ("inocar", "Boletín de oleaje del INOCAR n.º 191126"), ("gad-santa-cruz", "Informe del GAD n.º 4")]
    inamhi, sitrep = d["documentos"][0], d["documentos"][1]
    assert inamhi["vigente"] and inamhi["nivel"] == "muy alto" and inamhi["nombre"] == "INAMHI"
    assert sitrep["infografia"].endswith("Infografia-No-104.pdf") and sitrep["resumen_automatico"] and sitrep["que_es"] == "Informe de situación (SITREP)"


def prueba_coordinacion_sube_el_informe_de_un_gad_con_su_pdf(client, tmp_path, settings, monkeypatch):
    settings.MEDIA_ROOT, settings.IA_MODELO = str(tmp_path / "medios"), "prueba"
    from reportes.management.commands import oficial_agregar

    monkeypatch.setattr(oficiales, "leer_documento", lambda contenido, mime, que_es, esquema=None, instrucciones=None: oficial_agregar.DocumentoLeido(
        titulo="Informe de situación n.º 5 del COE cantonal", fecha="2026-11-23T10:00:00-06:00", resumen="Se habilitan dos refugios y se cierra la vía a El Cascajo."))
    archivo = tmp_path / "informe.pdf"
    archivo.write_bytes(PDF)
    call_command("oficial_agregar", "gad-santa-cruz", archivo=str(archivo), zona="santa-cruz")
    s = Suceso.objects.get()
    assert (s.clase, s.institucion, s.titulo, s.zona) == ("oficial", "gad-santa-cruz", "Informe de situación n.º 5 del COE cantonal", "santa-cruz")
    assert s.ocurrido == datetime(2026, 11, 23, 16, 0, tzinfo=timezone.utc) and "dos refugios" in s.texto and s.destino == f"/riesgos/oficial/{s.pk}/"
    # El destino es el visor (una página con botón de volver); el PDF se baja por su propia ruta.
    assert "data-volver" in client.get(s.destino).content.decode()
    r = client.get(f"{s.destino}archivo/")
    assert r.status_code == 200 and r["Content-Type"] == "application/pdf" and b"".join(r.streaming_content) == PDF
    assert client.get(f"/riesgos/medios/{s.archivo.name}").status_code == 404        # el PDF solo sale por su ruta
    s.visible = False
    s.save()
    assert client.get(s.destino).status_code == 404 and client.get(f"{s.destino}archivo/").status_code == 404
    with pytest.raises(Exception):
        call_command("oficial_agregar", "coe")                                         # sin archivo ni enlace
    (tmp_path / "foto.pdf").write_bytes(b"no es un pdf")
    with pytest.raises(Exception):
        call_command("oficial_agregar", "coe", archivo=str(tmp_path / "foto.pdf"))


def prueba_la_linea_del_tiempo_se_puede_abrir_ya_filtrada(client):
    pagina = client.get("/riesgos/informe/?ver=oficial").content.decode()
    assert "?ver=oficial" in pagina and "Solo los documentos oficiales" in pagina
    componente = client.get("/riesgos/app/").content.decode()
    assert "data-sos-oficiales" in componente and "/riesgos/api/oficiales.json" in componente and "Documentos oficiales" in componente

# SOS Galápagos · © 2026 Universidad San Francisco de Quito (USFQ) · Autor: Julián Maya <jamaya@usfq.edu.ec>
# Licencia Apache 2.0 (ver LICENSE y NOTICE): puede reutilizarse dando crédito.
"""Pruebas del importador del historial de ResponseGrid. Los datos son inventados."""
import json

import pytest
from django.core.management import call_command

from reportes import reglas
from reportes.models import Estado, Fuente, Reporte, TipoConfirmacion

pytestmark = pytest.mark.django_db

EXPORTACION = {
    "exportado": "2026-11-23T14:00:00+00:00",
    "necesidades": [
        {"id": "n-publica", "titulo": "Agua para el barrio", "descripcion": "Falta agua. Llamar a Ana Pérez al 099 123 4567 o a ana@ejemplo.org.",
         "prioridad": "high", "estado": "validated", "creado": "2026-11-01T19:53:39+00:00", "vence": "2026-11-03T19:53:39+00:00",
         "lat": -0.7335, "lon": -90.3137, "sensibilidad": "public", "zona": None, "referencia": None,
         "items": [{"nombre": "Agua embotellada", "cantidad": 10, "unidad": "galón"}]},
        {"id": "n-sensible", "titulo": "Pañales para una familia", "descripcion": "Mi hija Carla necesita pañales. Escríbanme al 0987654321.",
         "prioridad": "high", "estado": "validated", "creado": "2026-11-02T01:24:00+00:00", "vence": None,
         "lat": -0.69613, "lon": -90.32788, "sensibilidad": "approximate", "zona": "Bellavista", "referencia": "Casa azul de la señora Rosa", "items": []},
        {"id": "n-rechazada", "titulo": "Insulina", "descripcion": "Datos de una persona.", "prioridad": "urgent", "estado": "rejected",
         "creado": "2026-11-02T02:04:00+00:00", "vence": None, "lat": -0.73, "lon": -90.31, "sensibilidad": "approximate", "zona": None, "referencia": None, "items": []},
    ],
    "puntos": [
        {"id": "p-refugio", "tipo": "venue", "nombre": "Refugio — Colegio de prueba", "descripcion": "Refugio autorizado.", "direccion": "Av. Siempre Viva 742",
         "lat": -0.73861, "lon": -90.31807, "estado": "closed", "verificacion": "verified", "creado": "2026-11-01T19:53:31+00:00",
         "horario": None, "acepta": [], "capacidad": None, "organizacion_fuente": None},
        {"id": "p-transporte", "tipo": "transport", "nombre": "Juan Inventado (Pachito) — camioneta gratis",
         "descripcion": "Publicado en WhatsApp: dom 1 nov, 17:45. Vence: mar 3 nov, 20:00 (se cierra solo si nadie lo confirma). "
                        "Ayuda con el traslado de pertenencias. Contacto: Juan Inventado, 099 193 0000.",
         "direccion": "Servicio móvil", "lat": -0.7425, "lon": -90.3143, "estado": "closed", "verificacion": "verified",
         "creado": "2026-11-02T01:17:00+00:00", "horario": None, "acepta": [], "capacidad": None, "organizacion_fuente": None},
        {"id": "p-oculto", "tipo": "venue", "nombre": "Casa de alguien", "descripcion": "", "direccion": "", "lat": -0.74, "lon": -90.31,
         "estado": "hidden", "verificacion": "unverified", "creado": "2026-11-02T21:00:00+00:00", "horario": None, "acepta": [], "capacidad": None,
         "organizacion_fuente": None},
    ],
}


@pytest.fixture
def archivo(tmp_path):
    ruta = tmp_path / "exportacion.json"
    ruta.write_text(json.dumps(EXPORTACION), encoding="utf-8")
    return str(ruta)


def todo_el_texto():
    return " ".join(f"{r.titulo} {r.nota} {r.contacto}" for r in Reporte.objects.historial())


def prueba_el_importador_es_idempotente(archivo):
    call_command("importar_responsegrid", archivo)
    call_command("importar_responsegrid", archivo)
    assert Reporte.objects.historial().count() == 4  # sin la rechazada ni el oculto
    assert Reporte.objects.filter(id_externo="responsegrid:punto:p-refugio").count() == 1


def prueba_lo_importado_entra_cerrado_con_su_fecha_original(archivo):
    call_command("importar_responsegrid", archivo)
    r = Reporte.objects.get(id_externo="responsegrid:necesidad:n-publica")
    assert r.estado == Estado.CERRADO and r.fuente == Fuente.ANTERIOR and r.contenido_visible
    assert r.visto_en.isoformat().startswith("2026-11-01T19:53:39")
    assert r.tipo.codigo == "pedido_ayuda" and not r.tipo.activo  # no se ofrece en el formulario


def prueba_el_importador_no_lleva_telefonos_correos_ni_nombres(archivo):
    call_command("importar_responsegrid", archivo)
    texto = todo_el_texto()
    for prohibido in ("099", "0987654321", "ana@", "Ana Pérez", "Juan Inventado", "Pachito", "Carla", "Rosa", "Siempre Viva", "Publicado en WhatsApp", "Vence:"):
        assert prohibido not in texto, prohibido
    transporte = Reporte.objects.get(id_externo="responsegrid:punto:p-transporte")
    assert transporte.titulo == "" and transporte.nombre == "Transporte solidario"
    assert "traslado de pertenencias" in transporte.nota


def prueba_los_pedidos_sensibles_van_aproximados_y_sin_texto(archivo):
    call_command("importar_responsegrid", archivo)
    r = Reporte.objects.get(id_externo="responsegrid:necesidad:n-sensible")
    assert (round(r.punto.x, 6), round(r.punto.y, 6)) == (-90.33, -0.695)
    assert "aproximada" in r.nota and "pañales" not in r.nota.lower()
    # Los puntos públicos van en su lugar exacto.
    assert Reporte.objects.get(id_externo="responsegrid:punto:p-refugio").punto.y == pytest.approx(-0.73861)


def prueba_lo_importado_no_sale_en_el_mapa_pero_si_en_la_linea_del_tiempo(archivo, client):
    call_command("importar_responsegrid", archivo)
    for periodo in ("ahora", "24h", "evento"):
        datos = client.get(f"/riesgos/api/reportes/vivos.geojson?periodo={periodo}").json()
        assert not [f for f in datos["features"] if f["properties"]["fuente"] == "anterior"], periodo
    historial = client.get("/riesgos/api/reportes/historial.json").json()
    assert len(historial["features"]) == 4
    assert {f["properties"]["estado"] for f in historial["features"]} == {"cerrado"}
    assert "/riesgos/api/reportes/historial.json" in client.get("/riesgos/informe/").content.decode()


def prueba_lo_importado_no_vuelve_al_mapa_con_una_confirmacion(archivo, client):
    call_command("importar_responsegrid", archivo)
    r = Reporte.objects.get(id_externo="responsegrid:punto:p-refugio")
    client.post(f"/riesgos/r/{r.id_publico}/confirmar/", {"tipo": "sigue_ahi"})
    reglas.confirmar(r, TipoConfirmacion.SIGUE_AHI, "huella")
    r.refresh_from_db()
    assert r.estado == Estado.CERRADO and not r.confirmaciones.exists()
    assert not Reporte.objects.vivos().filter(pk=r.pk).exists()
    ficha = client.get(f"/riesgos/r/{r.id_publico}/").content.decode()
    assert "coordinación anterior" in ficha and "Ver en el mapa" not in ficha
    assert f'data-url="/riesgos/r/{r.id_publico}/"' in ficha  # compartir lleva a la ficha, no al mapa
    assert client.get(f"/riesgos/?r={r.id_publico}")["Location"] == f"/riesgos/r/{r.id_publico}/"

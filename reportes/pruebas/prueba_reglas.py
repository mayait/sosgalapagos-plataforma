# SOS Galápagos · © 2026 Universidad San Francisco de Quito (USFQ) · Autor: Julián Maya <jamaya@usfq.edu.ec>
# Licencia Apache 2.0 (ver LICENSE y NOTICE): puede reutilizarse dando crédito.
"""Pruebas de las reglas de vida: vencimiento, duplicados y confirmaciones."""
from datetime import timedelta

import pytest
from django.contrib.gis.geos import Point
from django.utils import timezone

from reportes import reglas
from reportes.models import Estado, Fuente, MotivoCierre, Reporte, TipoConfirmacion, TipoRiesgo

pytestmark = pytest.mark.django_db

AYORA = Point(-90.3145, -0.7435, srid=4326)
# Un grado de latitud son unos 111 km: 0,0003° ≈ 33 m y 0,0009° ≈ 100 m.
A_33_M = Point(-90.3145, -0.7438, srid=4326)
A_100_M = Point(-90.3145, -0.7444, srid=4326)


@pytest.fixture
def agua():
    return TipoRiesgo.objects.get(codigo="agua_via")  # plazo de 6 h


@pytest.fixture
def cable():
    return TipoRiesgo.objects.get(codigo="cable")  # plazo de 24 h


def crear(tipo, punto=AYORA, huella="a", **campos):
    return reglas.crear_reporte(tipo=tipo, punto=punto, huella=huella, **campos)


# ── Vencimiento ───────────────────────────────────────────────────────────────


def prueba_vence_segun_el_plazo_del_tipo(agua, cable):
    ahora = timezone.now()
    assert crear(agua, ahora=ahora).reporte.vence_en == ahora + timedelta(hours=6)
    assert crear(cable, ahora=ahora).reporte.vence_en == ahora + timedelta(hours=24)


def prueba_un_reporte_vencido_deja_de_estar_vivo_sin_ninguna_tarea(agua):
    ahora = timezone.now()
    r = crear(agua, ahora=ahora).reporte
    assert r in Reporte.objects.vivos(ahora + timedelta(hours=5, minutes=59))
    assert r not in Reporte.objects.vivos(ahora + timedelta(hours=6, minutes=1))
    r.refresh_from_db()
    assert r.estado != Estado.CERRADO  # nadie lo tocó: desapareció solo por la fecha


def prueba_cerrar_vencidos_lo_pasa_al_archivo_sin_borrarlo(agua):
    ahora = timezone.now()
    r = crear(agua, ahora=ahora).reporte
    assert reglas.cerrar_vencidos(ahora + timedelta(hours=7)) == 1
    r.refresh_from_db()
    assert r.estado == Estado.CERRADO
    assert r.motivo_cierre == MotivoCierre.VENCIO
    assert r.cerrado_en == r.vence_en  # la hora de cierre es la del vencimiento
    assert Reporte.objects.filter(pk=r.pk).exists()


def prueba_cerrar_vencidos_no_toca_los_vigentes(agua):
    ahora = timezone.now()
    crear(agua, ahora=ahora)
    assert reglas.cerrar_vencidos(ahora + timedelta(hours=1)) == 0


def prueba_un_vecino_entra_por_verificar_y_con_el_contenido_publicado(agua):
    r = crear(agua, nota="frente a la tienda").reporte
    assert r.estado == Estado.POR_VERIFICAR
    assert r.contenido_visible is True


def prueba_la_nota_de_un_vecino_no_publica_telefonos_ni_cedulas(agua):
    r = crear(agua, nota="llamar al 099 123 4567 o al +593987654321, cédula 2000045357; casa 12").reporte
    assert "4567" not in r.nota and "987654321" not in r.nota and "2000045357" not in r.nota
    assert r.nota.count("[número oculto]") == 3 and "casa 12" in r.nota


def prueba_un_coordinador_entra_confirmado_y_visible(agua):
    r = crear(agua, fuente=Fuente.COORDINADOR).reporte
    assert r.estado == Estado.CONFIRMADO
    assert r.contenido_visible is True


# ── Duplicados ────────────────────────────────────────────────────────────────


def prueba_mismo_tipo_a_menos_de_50_m_es_confirmacion_del_existente(agua):
    original = crear(agua, huella="a").reporte
    resultado = crear(agua, punto=A_33_M, huella="b")
    assert resultado.duplicado is True
    assert resultado.reporte == original
    assert Reporte.objects.count() == 1
    assert original.confirmaciones.filter(tipo=TipoConfirmacion.SIGUE_AHI).count() == 1


def prueba_mismo_tipo_a_mas_de_50_m_es_un_reporte_nuevo(agua):
    crear(agua)
    assert crear(agua, punto=A_100_M).duplicado is False
    assert Reporte.objects.count() == 2


def prueba_otro_tipo_en_el_mismo_lugar_es_un_reporte_nuevo(agua, cable):
    crear(agua)
    assert crear(cable).duplicado is False
    assert Reporte.objects.count() == 2


def prueba_un_reporte_vencido_no_absorbe_duplicados(agua):
    ahora = timezone.now()
    crear(agua, ahora=ahora)
    despues = ahora + timedelta(hours=7)
    assert crear(agua, punto=A_33_M, ahora=despues).duplicado is False


def prueba_el_duplicado_renueva_el_plazo_del_original(agua):
    ahora = timezone.now()
    original = crear(agua, ahora=ahora).reporte
    crear(agua, punto=A_33_M, huella="b", ahora=ahora + timedelta(hours=4))
    original.refresh_from_db()
    assert original.vence_en == ahora + timedelta(hours=10)


# ── Confirmaciones ────────────────────────────────────────────────────────────


def prueba_sigue_ahi_renueva_el_plazo(agua):
    ahora = timezone.now()
    r = crear(agua, ahora=ahora).reporte
    r = reglas.confirmar(r, TipoConfirmacion.SIGUE_AHI, "b", ahora=ahora + timedelta(hours=5))
    assert r.vence_en == ahora + timedelta(hours=11)


def prueba_un_ya_bajo_lo_deja_bajando_y_sigue_en_el_mapa(agua):
    r = crear(agua).reporte
    r = reglas.confirmar(r, TipoConfirmacion.YA_BAJO, "b")
    assert r.estado == Estado.BAJANDO
    assert r in Reporte.objects.vivos()


def prueba_dos_ya_bajo_de_dispositivos_distintos_lo_cierran(agua):
    r = crear(agua).reporte
    reglas.confirmar(r, TipoConfirmacion.YA_BAJO, "b")
    r = reglas.confirmar(r, TipoConfirmacion.YA_BAJO, "c")
    assert r.estado == Estado.CERRADO
    assert r.motivo_cierre == MotivoCierre.YA_BAJO
    assert r not in Reporte.objects.vivos()


def prueba_dos_ya_bajo_del_mismo_dispositivo_no_lo_cierran(agua):
    r = crear(agua).reporte
    reglas.confirmar(r, TipoConfirmacion.YA_BAJO, "b")
    r = reglas.confirmar(r, TipoConfirmacion.YA_BAJO, "b")
    assert r.estado == Estado.BAJANDO


def prueba_sigue_ahi_anula_los_ya_bajo_anteriores(agua):
    ahora = timezone.now()
    r = crear(agua, ahora=ahora).reporte
    reglas.confirmar(r, TipoConfirmacion.YA_BAJO, "b", ahora=ahora + timedelta(minutes=10))
    r = reglas.confirmar(r, TipoConfirmacion.SIGUE_AHI, "c", ahora=ahora + timedelta(minutes=20))
    assert r.estado == Estado.POR_VERIFICAR or r.estado == Estado.CONFIRMADO
    r = reglas.confirmar(r, TipoConfirmacion.YA_BAJO, "d", ahora=ahora + timedelta(minutes=30))
    assert r.estado == Estado.BAJANDO  # el «ya bajó» de antes ya no cuenta


def prueba_confirmar_un_reporte_cerrado_no_lo_revive(agua):
    r = crear(agua).reporte
    reglas.cerrar(r, MotivoCierre.COORDINADOR)
    r = reglas.confirmar(r, TipoConfirmacion.SIGUE_AHI, "b")
    assert r.estado == Estado.CERRADO


def prueba_la_huella_no_revela_el_identificador():
    huella = reglas.huella_de("identificador-del-telefono")
    assert "identificador" not in huella and len(huella) == 64
    assert huella == reglas.huella_de("identificador-del-telefono")

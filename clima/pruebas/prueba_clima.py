"""Pruebas del clima: la copia desde la base del recolector, los resúmenes por hora y la API."""
import sqlite3
from datetime import datetime, timedelta, timezone

import pytest

from clima import consultas
from clima.models import Corrida, Estacion, Horaria, Observacion, Sincronizacion
from clima.sincronizar import sincronizar

pytestmark = pytest.mark.django_db(transaction=True)  # la copia usa COPY y tablas temporales
AHORA = datetime.now(timezone.utc).replace(minute=20, second=0, microsecond=0)
iso = lambda t: t.strftime("%Y-%m-%dT%H:%M:%SZ")  # noqa: E731


@pytest.fixture
def origen(tmp_path):
    ruta = tmp_path / "clima.db"
    con = sqlite3.connect(ruta)
    con.executescript("""
      CREATE TABLE obs (fuente TEXT NOT NULL, estacion TEXT NOT NULL, variable TEXT NOT NULL, ts TEXT NOT NULL, valor REAL,
        PRIMARY KEY (fuente, estacion, variable, ts)) WITHOUT ROWID;
      CREATE TABLE estaciones (fuente TEXT NOT NULL, estacion TEXT NOT NULL, nombre TEXT, isla TEXT, lat REAL, lon REAL,
        altitud_m REAL, operador TEXT, url TEXT, meta TEXT, PRIMARY KEY (fuente, estacion));
      CREATE TABLE corridas (ts TEXT NOT NULL, fuente TEXT NOT NULL, ok INTEGER, registros INTEGER, segundos REAL, error TEXT);
    """)
    con.execute("INSERT INTO estaciones VALUES ('ierse','n1','Los Guayabillos','Santa Cruz',-0.6991,-90.342,178,'IERSE',NULL,NULL)")
    hora = AHORA.replace(minute=0)
    filas = [("ierse", "n1", "lluvia_mm", iso(hora - timedelta(hours=1) + timedelta(minutes=5 * i)), 0.5) for i in range(12)]
    filas += [("ierse", "n1", "temp_c", iso(hora - timedelta(hours=1) + timedelta(minutes=30 * i)), 20 + 2 * i) for i in range(2)]
    filas += [("goes", "la-cascada", "frio_pct", iso(hora - timedelta(hours=1)), 12.0)]
    con.executemany("INSERT INTO obs VALUES (?,?,?,?,?)", filas)
    con.executemany("INSERT INTO corridas VALUES (?,?,?,?,?,?)", [
        (iso(AHORA - timedelta(minutes=10)), "ierse", 1, 12, 1.5, None), (iso(AHORA - timedelta(minutes=5)), "ierse", 0, 0, 30.0, "sin respuesta"),
        (iso(AHORA - timedelta(minutes=5)), "gsc", 1, 40, 6.0, None)])
    con.commit()
    con.close()
    return ruta


def prueba_copia_estaciones_mediciones_y_corridas(origen):
    s = sincronizar(completa=True, ruta=origen)
    assert not s.error and s.leidas == 15 and s.cambiadas == 15
    e = Estacion.objects.get(fuente="ierse", codigo="n1")
    assert e.nombre == "Los Guayabillos" and abs(e.punto.x + 90.342) < 1e-6 and e.ultima is not None
    assert Estacion.objects.filter(fuente="goes", codigo="la-cascada").exists()  # las zonas del satélite se crean solas
    assert Observacion.objects.count() == 15 and Corrida.objects.count() == 3
    # Repetir no duplica nada.
    s2 = sincronizar(ruta=origen)
    assert s2.cambiadas == 0 and s2.borradas == 0 and Observacion.objects.count() == 15 and Corrida.objects.count() == 3


def prueba_resume_por_hora(origen):
    sincronizar(completa=True, ruta=origen)
    hora = AHORA.replace(minute=0) - timedelta(hours=1)
    lluvia = Horaria.objects.get(estacion__codigo="n1", variable="lluvia_mm", hora=hora)
    assert lluvia.suma == pytest.approx(6.0) and lluvia.n == 12
    temperatura = Horaria.objects.get(estacion__codigo="n1", variable="temp_c", hora=hora)
    assert temperatura.media == pytest.approx(21.0) and temperatura.maximo == 22


def prueba_las_correcciones_y_los_borrados_del_recolector_llegan(origen):
    sincronizar(completa=True, ruta=origen)
    con = sqlite3.connect(origen)
    hora = AHORA.replace(minute=0) - timedelta(hours=1)
    con.execute("UPDATE obs SET valor = 2.5 WHERE variable = 'lluvia_mm' AND ts = ?", [iso(hora)])
    con.execute("DELETE FROM obs WHERE variable = 'lluvia_mm' AND ts = ?", [iso(hora + timedelta(minutes=5))])
    con.commit()
    con.close()
    s = sincronizar(ruta=origen)
    assert s.cambiadas == 1 and s.borradas == 1 and Observacion.objects.count() == 14
    assert Horaria.objects.get(estacion__codigo="n1", variable="lluvia_mm", hora=hora).suma == pytest.approx(7.5)


def prueba_una_lectura_corta_no_borra_nada(origen):
    sincronizar(completa=True, ruta=origen)
    con = sqlite3.connect(origen)
    con.execute("DELETE FROM obs WHERE variable = 'lluvia_mm'")  # como si el origen se leyera a medias
    con.commit()
    con.close()
    s = sincronizar(ruta=origen)
    assert s.borradas == 0 and Observacion.objects.count() == 15


def prueba_si_falta_la_base_de_origen_queda_anotado(tmp_path):
    s = sincronizar(ruta=tmp_path / "no-existe.db")
    assert s.error and Sincronizacion.objects.count() == 1 and Observacion.objects.count() == 0


def prueba_la_api_da_series_estaciones_y_salud(origen, client):
    sincronizar(completa=True, ruta=origen)
    hora = AHORA.replace(minute=0) - timedelta(hours=1)
    estaciones = client.get("/riesgos/api/clima/estaciones").json()["estaciones"]
    assert [e["id"] for e in estaciones] == ["ierse/n1"]  # las zonas del satélite no son estaciones
    assert estaciones[0]["lluvia_mm"]["24h"] == 6.0
    serie = client.get("/riesgos/api/clima/serie", {"estacion": "ierse/n1", "desde": iso(hora - timedelta(hours=1)), "hasta": iso(hora + timedelta(hours=1))}).json()
    assert serie["valores"] == [None, 6.0]
    dia = client.get("/riesgos/api/clima/serie", {"estacion": "ierse/n1", "paso": "dia", "desde": iso(hora - timedelta(days=1)), "hasta": iso(hora + timedelta(hours=1))}).json()
    assert sum(v or 0 for v in dia["valores"]) == 6.0
    assert client.get("/riesgos/api/clima/serie", {"estacion": "no/existe"}).status_code == 404
    assert client.get("/riesgos/api/clima/serie", {"estacion": "ierse/n1", "variable": "otra"}).status_code == 400
    salud = client.get("/riesgos/api/clima/salud").json()
    ierse = next(f for f in salud["fuentes"] if f["fuente"] == "ierse")
    assert ierse["corridas"] == 2 and ierse["bien"] == 1 and ierse["acierto_pct"] == 50
    assert salud["observaciones"] == 15 and salud["copia"]["con_error"] == 0

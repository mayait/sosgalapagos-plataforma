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


# ── Pronóstico: guardar y verificar ──────────────────────────────────────────
def _respuesta(base_utc, mm_por_hora):
    """Una respuesta como la de los modelos: 7 puntos, 72 horas, dos modelos."""
    horas = [(base_utc + timedelta(hours=i)).strftime("%Y-%m-%dT%H:%M") for i in range(72)]
    return [{"hourly": {"time": horas, "precipitation_gfs_seamless": [mm_por_hora] * 72, "precipitation_icon_seamless": [0.0] * 72}} for _ in range(7)]


def prueba_el_dia_del_modelo_es_el_de_galapagos():
    from clima import pronostico

    # 24 horas que terminan entre las 07:00 y las 06:00 UTC del día siguiente = el día de Galápagos.
    base = datetime(2026, 11, 10, 7, 0, tzinfo=timezone.utc)
    horas = [(base + timedelta(hours=i)).strftime("%Y-%m-%dT%H:%M") for i in range(30)]
    totales = pronostico.totales_por_dia(horas, [1.0] * 30)
    assert totales == {datetime(2026, 11, 10).date(): 24.0}  # el día incompleto no se cuenta


def prueba_guarda_solo_lo_que_cambia_y_verifica(tmp_path, origen, settings):
    import gzip
    import json

    from clima import pronostico
    from clima.models import EstacionDanada, PronosticoEmitido, PronosticoModelo

    carpeta = tmp_path / "pronostico" / "archivo" / "2026-11"
    carpeta.mkdir(parents=True)
    dia = (AHORA.astimezone(consultas.GALAPAGOS) - timedelta(days=1)).date()  # ayer en Galápagos
    base = datetime.combine(dia - timedelta(days=1), datetime.min.time(), timezone.utc) + timedelta(hours=7)
    obtenido = datetime.combine(dia - timedelta(days=1), datetime.min.time(), timezone.utc) + timedelta(hours=12)
    for hora in (0, 1):  # dos archivos con lo mismo: el segundo no añade filas
        with gzip.open(carpeta / f"{obtenido + timedelta(hours=hora):%Y%m%dT%H}_deterministas.json.gz", "wt") as f:
            json.dump(_respuesta(base, 1.0), f)
    leidos, nuevas = pronostico.guardar_archivo(tmp_path / "pronostico")
    assert leidos == 2 and nuevas == PronosticoModelo.objects.count() and nuevas > 0
    fila = PronosticoModelo.objects.get(punto="puerto-ayora", modelo="gfs_seamless", fecha=dia)
    assert fila.mm == 24.0 and fila.anticipacion == 1
    assert pronostico.guardar_archivo(tmp_path / "pronostico")[1] == 0  # repetir no duplica

    # Lo publicado.
    publicado = tmp_path / "pronostico.json"
    publicado.write_text(json.dumps({"generado": (obtenido).strftime("%Y-%m-%dT%H:%M:%SZ"), "hoy_local": str(dia - timedelta(days=1)), "zonas": {"la-cascada": {"puntos": [
        {"id": "puerto-ayora", "dias": [{"fecha": str(dia), "prob": {"10": 0.9, "20": 0.8, "50": 0.1}, "consenso": 0.9, "n_modelos": 7, "mm_modelos_mediana": 22.0, "nivel": "alta", "calibrado": True}]}]}}}))
    assert pronostico.guardar_emitido(publicado) == 1 and pronostico.guardar_emitido(publicado) == 0
    assert PronosticoEmitido.objects.get().anticipacion == 1

    # Lo que llovió: una estación de Puerto Ayora con el día completo y 30 mm.
    con = sqlite3.connect(origen)
    con.execute("INSERT INTO estaciones VALUES ('inamhi','M0191','Puerto Ayora','Santa Cruz',-0.74,-90.31,6,'INAMHI',NULL,NULL)")
    inicio = datetime.combine(dia, datetime.min.time(), timezone.utc) + timedelta(hours=6)
    con.executemany("INSERT INTO obs VALUES ('inamhi','M0191','lluvia_mm',?,?)", [(iso(inicio + timedelta(hours=h)), 1.25) for h in range(24)])
    con.commit()
    con.close()
    sincronizar(completa=True, ruta=origen)
    v = pronostico.verificar(dias=10)
    assert v["dias_observados"] == 1 and v["dias_de_lluvia_fuerte"] == 1
    gfs = next(m for m in v["por_modelo"] if m["modelo"] == "gfs_seamless" and m["anticipacion"] == 1)
    assert gfs == {"modelo": "gfs_seamless", "anticipacion": 1, "dias": 1, "error_medio_mm": 6.0, "sesgo_mm": -6.0, "dias_de_lluvia_fuerte": 1, "avisados": 1, "falsas_alarmas": 0, "brier": None}
    icon = next(m for m in v["por_modelo"] if m["modelo"] == "icon_seamless" and m["anticipacion"] == 1)
    assert icon["avisados"] == 0 and icon["sesgo_mm"] == -30.0  # no avisó: se le pasó
    assert v["publicado"][0]["brier"] == pytest.approx(0.04) and v["publicado"][0]["punto"] == "puerto-ayora"

    # Un sensor marcado como dañado no cuenta como observación.
    EstacionDanada.objects.create(estacion=Estacion.objects.get(codigo="M0191"), variable="lluvia_mm", desde=inicio - timedelta(days=2), motivo="prueba")
    assert pronostico.verificar(dias=10)["dias_observados"] == 0


def prueba_la_lluvia_de_un_sensor_danado_no_se_publica(origen, client):
    from clima.models import EstacionDanada

    sincronizar(completa=True, ruta=origen)
    EstacionDanada.objects.create(estacion=Estacion.objects.get(codigo="n1"), desde=AHORA - timedelta(days=5), motivo="marca lluvias imposibles")
    e = client.get("/riesgos/api/clima/estaciones").json()["estaciones"][0]
    assert e["lluvia_mm"] is None and e["danada"]["motivo"] == "marca lluvias imposibles"


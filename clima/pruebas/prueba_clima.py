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


def prueba_la_regresion_aprende_y_no_se_guarda_si_faltan_dias():
    from clima import pronostico

    # Con más milímetros pronosticados, más días de lluvia fuerte: la curva debe subir.
    pares = [(float(x), 1.0 if x > 2 else 0.0) for x in [0.5, 1, 1.5, 2, 2.5, 3, 3.5, 4] * 5]
    a, b = pronostico._ajustar(pares)
    assert b > 0 and pronostico._prob(a, b, 0.5) < 0.3 < 0.7 < pronostico._prob(a, b, 4)
    assert pronostico.predictor([0, 0, 0, 0]) == 0 and pronostico.predictor([1, 2, 3, 40]) > pronostico.predictor([1, 2, 3, 4])
    assert pronostico.recalibrar(guardar=False) == []  # sin pares guardados no hay curva


def prueba_el_pronostico_de_los_proximos_dias_responde_vacio(client):
    datos = client.get("/riesgos/api/clima/pronostico").json()
    assert len(datos["puntos"]) == 7 and datos["puntos"][0]["dias"][0]["recalibrado"] is None
    assert "no oficial" in datos["aviso"]


# ── Etapa 5: las fuentes las recoge esta aplicación, con el código del recolector anterior ──
@pytest.fixture
def metar(monkeypatch, settings):
    """La fuente de los aeropuertos, con la red simulada."""
    from clima.compat import modulos

    modulos()
    import fuentes_extra

    monkeypatch.setenv("CLIMA_METAR_API", "https://metar.test/api")
    settings.CLIMA_FUENTES_NATIVAS = ["metar"]
    t = int((AHORA - timedelta(minutes=20)).timestamp())
    respuesta = [{"icaoId": "SEGS", "obsTime": t, "temp": 27, "altim": 1012.5, "wspd": 10, "wxString": "+TSRA"}, {"icaoId": "KJFK", "obsTime": t, "temp": 5}]
    monkeypatch.setattr(fuentes_extra, "http_json", lambda url, **k: respuesta)
    return fuentes_extra


def prueba_una_fuente_nativa_se_recoge_aqui_y_deja_de_copiarse(origen, metar):
    from clima import fuentes

    con = sqlite3.connect(origen)
    con.execute("INSERT INTO obs VALUES ('metar','SEGS','temp_c',?,?)", [iso(AHORA - timedelta(hours=1)), 99.0])  # lo que trae el recolector anterior
    con.execute("INSERT INTO corridas VALUES (?,?,?,?,?,?)", [iso(AHORA - timedelta(minutes=3)), "metar", 1, 1, 1.0, None])
    con.commit()
    con.close()
    assert fuentes.recolectar() == {"metar": 4}
    assert Observacion.objects.filter(estacion__fuente="metar").count() == 4
    valores = {o.variable: o.valor for o in Observacion.objects.filter(estacion__fuente="metar")}
    assert valores == {"temp_c": 27.0, "presion_hpa": 1012.5, "viento_ms": 5.1, "lluvia_codigo": 3.0}  # nudos a m/s; tormenta = 3
    e = Estacion.objects.get(fuente="metar", codigo="SEGS")
    assert e.nombre.startswith("Aeropuerto Seymour") and abs(e.punto.y + 0.4539) < 1e-6
    assert Corrida.objects.filter(fuente="metar", ok=True).count() == 1
    assert Horaria.objects.filter(estacion=e, variable="temp_c").exists()  # los resúmenes por hora se rehacen
    # La copia no trae el 99 del recolector anterior ni borra lo recogido aquí.
    s = sincronizar(ruta=origen)
    assert not s.error and Observacion.objects.filter(estacion__fuente="metar").count() == 4
    assert not Observacion.objects.filter(valor=99.0).exists() and Corrida.objects.filter(fuente="metar").count() == 1
    assert Observacion.objects.filter(estacion__fuente="ierse").count() == 14  # las demás fuentes sí se copian


def prueba_si_una_fuente_nativa_falla_queda_anotado_y_siguen_las_demas(metar, monkeypatch, settings):
    from clima import fuentes

    def roto(url, **k):
        raise TimeoutError("sin respuesta")

    monkeypatch.setattr(metar, "http_json", roto)
    settings.CLIMA_FUENTES_NATIVAS = ["metar", "inventada"]
    assert fuentes.recolectar() == {"metar": "error: TimeoutError"}
    c = Corrida.objects.get(fuente="metar")
    assert not c.ok and "sin respuesta" in c.error


def prueba_una_fuente_sin_nada_nuevo_no_es_un_fallo(metar, monkeypatch):
    import io

    from clima import fuentes
    from clima.compat import modulos

    recolector = modulos()
    monkeypatch.setattr(metar, "http_json", recolector.http_json)  # la función de verdad, con la red simulada

    class SinContenido(io.BytesIO):  # como responde la fuente de noche: 204 y cuerpo vacío
        status = 204

    monkeypatch.setattr(recolector.urllib.request, "urlopen", lambda pedido, timeout=0: SinContenido(b""))
    assert fuentes.recolectar() == {"metar": 0}
    assert Corrida.objects.get(fuente="metar").ok is True


def prueba_la_conexion_de_compatibilidad_lee_y_escribe_como_sqlite(origen):
    """El código del recolector anterior usa «?», INSERT OR REPLACE y horas en texto: todo eso llega a los modelos."""
    from clima.compat import Conexion

    sincronizar(completa=True, ruta=origen)
    con = Conexion()
    hora = AHORA.replace(minute=0) - timedelta(hours=1)
    assert con.execute("SELECT MAX(ts) FROM obs WHERE fuente=? AND estacion=?", ("ierse", "n1")).fetchone()[0] == iso(hora + timedelta(minutes=55))
    con.executemany("INSERT OR REPLACE INTO obs VALUES (?,?,?,?,?)", [("ierse", "n1", "lluvia_mm", iso(hora), 9.5), ("nueva", "x1", "temp_c", iso(hora), 20.0)])
    assert Observacion.objects.get(estacion__codigo="n1", variable="lluvia_mm", ts=hora).valor == 9.5      # reemplaza
    assert Estacion.objects.filter(fuente="nueva", codigo="x1").exists()                                    # crea la estación si falta
    con.execute("DELETE FROM obs WHERE fuente='ierse' AND estacion=? AND substr(ts,1,13)=? AND variable='temp_c'", ("n1", iso(hora)[:13]))
    assert not Observacion.objects.filter(estacion__codigo="n1", variable="temp_c").exists()
    con.execute("INSERT OR REPLACE INTO estaciones VALUES (?,?,?,?,?,?,?,?,?,?)", ("nueva", "x1", "Nueva", "Isabela", -0.95, -90.97, 12, "Prueba", None, "{}"))
    e = Estacion.objects.get(fuente="nueva")
    assert e.nombre == "Nueva" and abs(e.punto.x + 90.97) < 1e-6
    con.execute("INSERT INTO corridas VALUES (?,?,?,?,?,?)", (iso(AHORA), "nueva", 1, 2, 0.5, None))
    assert Corrida.objects.get(fuente="nueva").ok is True
    assert con.execute("SELECT date(?, '-6 hours')", ("2026-11-21T03:00:00Z",)).fetchone()[0] == "2026-11-20"
    assert [r[0] for r in con.execute("SELECT estacion FROM estaciones WHERE fuente='goes'")] == []     # las zonas del satélite no son estaciones


def prueba_el_panel_se_genera_desde_esta_base_con_la_forma_de_siempre(origen, tmp_path, settings):
    import json

    from clima import panel
    from clima.models import EstacionDanada

    sincronizar(completa=True, ruta=origen)
    settings.CLIMA_SALIDA = str(tmp_path / "datos")
    (tmp_path / "datos").mkdir()
    (tmp_path / "datos" / "satelite.json").write_text(json.dumps({"generado": "x"}))
    r = panel.publicar()
    assert r["total_s"] < 20
    est = json.loads((tmp_path / "datos" / "estado.json").read_text())
    assert set(est) == {"generado", "estaciones", "fuentes", "eventos", "inundacion", "mareas", "pronostico", "satelite"}
    e = next(x for x in est["estaciones"] if x["estacion"] == "n1")
    assert e["nombre"] == "Los Guayabillos" and e["operador"] == "IERSE-WSN" and e["lluvia"]["24h"] == 6.0 and e["actual"]["temp_c"] == 22.0
    assert any(x["fuente"] == "darwin" and x["en_vivo"] is False for x in est["estaciones"])     # la red sin transmisión sigue listada
    assert not any(x["fuente"] == "goes" for x in est["estaciones"])
    assert est["fuentes"]["IERSE-WSN"]["ok"] in (0, 1) and est["satelite"] == {"generado": "x"}
    assert [z["id"] for z in est["inundacion"]["zonas"]] == ["la-cascada", "santa-cruz-alta", "san-cristobal", "isabela"]
    hor = json.loads((tmp_path / "datos" / "horario.json").read_text())
    assert hor["horas"] == len(hor["series"]["ierse/n1"]["lluvia_mm"]) and 6.0 in hor["series"]["ierse/n1"]["lluvia_mm"]
    dia = json.loads((tmp_path / "datos" / "diario.json").read_text())
    assert sum(v or 0 for v in dia["diario"]["ierse/n1"]["lluvia"]) == 6.0 and "estacionalidad" in dia
    # Un sensor dañado: su lluvia sale en blanco en los tres archivos.
    EstacionDanada.objects.create(estacion=Estacion.objects.get(codigo="n1"), desde=AHORA - timedelta(days=30), motivo="prueba")
    panel.publicar()
    est = json.loads((tmp_path / "datos" / "estado.json").read_text())
    e = next(x for x in est["estaciones"] if x["estacion"] == "n1")
    assert e["lluvia"]["24h"] is None and e["danada"]["motivo"] == "prueba"
    assert set(json.loads((tmp_path / "datos" / "horario.json").read_text())["series"]["ierse/n1"]["lluvia_mm"]) == {None}


def prueba_la_linea_del_tiempo_lee_la_lluvia_de_esta_base(origen):
    from reportes import clima as panel

    sincronizar(completa=True, ruta=origen)
    assert panel.estaciones_con_lluvia() == [{"id": "ierse/n1", "nombre": "Los Guayabillos", "isla": "Santa Cruz"}]
    hora = AHORA.replace(minute=0, second=0, microsecond=0) - timedelta(hours=1)
    inicio, valores = panel.lluvia_por_hora("ierse/n1", hora - timedelta(hours=1), hora + timedelta(hours=1))
    assert inicio == hora - timedelta(hours=1) and valores == [None, 6.0]

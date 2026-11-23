# SOS Galápagos · © 2026 Universidad San Francisco de Quito (USFQ) · Autor: Julián Maya <jamaya@usfq.edu.ec>
# Licencia Apache 2.0 (ver LICENSE y NOTICE): puede reutilizarse dando crédito.
"""Pruebas de las fuentes de clima: cada una convierte bien lo que llega y todas guardan en la base."""
import io
import json
from datetime import datetime, timedelta, timezone

import pytest

from clima import fuentes
from clima.fuentes import acumulado, ambient, base, gsc, ierse, inamhi, ioc, mar_modelo, metar, tempest, weatherlink, wunderground
from clima.models import Corrida, Estacion, Estado, Horaria, MareaExtremo, MarHora, Observacion

pytestmark = pytest.mark.django_db(transaction=True)
UTC = timezone.utc
AHORA = datetime.now(UTC).replace(minute=20, second=0, microsecond=0)


def valores(fuente, codigo=None):
    filtro = {"estacion__fuente": fuente, **({"estacion__codigo": codigo} if codigo else {})}
    return {(o.variable, o.ts): o.valor for o in Observacion.objects.filter(**filtro)}


# ── El ciclo ─────────────────────────────────────────────────────────────────
@pytest.fixture
def aeropuertos(monkeypatch):
    for nombre in list(__import__("os").environ):
        if nombre.startswith("CLIMA_"):
            monkeypatch.delenv(nombre)
    monkeypatch.setenv("CLIMA_METAR_API", "https://metar.test/api")
    t = int((AHORA - timedelta(minutes=20)).timestamp())
    respuesta = [{"icaoId": "SEGS", "obsTime": t, "temp": 27, "altim": 1012.5, "wspd": 10, "wxString": "+TSRA"}, {"icaoId": "KJFK", "obsTime": t, "temp": 5}]
    monkeypatch.setattr(base, "http_json", lambda url, *a, **k: respuesta)


def prueba_solo_corren_las_fuentes_configuradas_y_queda_anotado(aeropuertos):
    assert fuentes.activas() == ["metar"]
    assert fuentes.recolectar() == {"metar": 4}
    assert {v: x for (v, _), x in valores("metar").items()} == {"temp_c": 27.0, "presion_hpa": 1012.5, "viento_ms": 5.1, "lluvia_codigo": 3.0}  # nudos a m/s; tormenta = 3
    e = Estacion.objects.get(fuente="metar", codigo="SEGS")
    assert e.nombre.startswith("Aeropuerto Seymour") and abs(e.punto.y + 0.4539) < 1e-6
    assert Corrida.objects.get(fuente="metar").ok and Horaria.objects.filter(estacion=e, variable="temp_c").exists()


def prueba_si_una_fuente_falla_queda_anotado_y_no_se_guarda_a_medias(aeropuertos, monkeypatch):
    def rota(url, *a, **k):
        raise TimeoutError("sin respuesta")

    monkeypatch.setattr(base, "http_json", rota)
    assert fuentes.recolectar(["metar", "inventada"]) == {"metar": "error: TimeoutError"}
    c = Corrida.objects.get(fuente="metar")
    assert not c.ok and "sin respuesta" in c.error and not Observacion.objects.exists()


def prueba_una_fuente_sin_nada_nuevo_no_es_un_fallo(monkeypatch):
    class SinContenido(io.BytesIO):  # como responden los aeropuertos de noche: 204 y cuerpo vacío
        status = 204

    monkeypatch.setattr(base.urllib.request, "urlopen", lambda pedido, timeout=0: SinContenido(b""))
    assert base.http_json("https://metar.test/api") == [] and metar.filas_de([]) == []
    assert [metar.codigo_lluvia(x) for x in (None, "BR", "-RA", "DZ", "RA", "+RA", "TSRA")] == [0, 0, 1, 1, 2, 3, 3]


# ── Lluvia por diferencia del acumulado ──────────────────────────────────────
def prueba_la_lluvia_por_diferencia_no_cuenta_dos_veces_ni_inventa():
    t = AHORA
    antes = lambda minutos, mm: (t - timedelta(minutes=minutos), mm)  # noqa: E731
    assert acumulado.lluvia_por_diferencia(t, 12.4, antes(5, 12.0)) == 0.4
    assert acumulado.lluvia_por_diferencia(t, 0.6, antes(5, 30.0)) == 0.6      # el contador se reinició
    assert acumulado.lluvia_por_diferencia(t, 25.0, antes(5, 30.0)) == 0.0     # baja sin llegar a cero: no cuenta
    assert acumulado.lluvia_por_diferencia(t, 80.0, antes(5, 12.0)) is None    # salto imposible
    assert acumulado.lluvia_por_diferencia(t, 20.0, antes(90, 12.0)) is None   # tras un hueco no se atribuye nada
    assert acumulado.lluvia_por_diferencia(t, 20.0, None) is None


def prueba_recalcular_rehace_la_lluvia_desde_el_acumulado():
    t0 = AHORA - timedelta(hours=1)
    base.guardar("wunderground", [("casa_marina", "lluvia_dia_acum_mm", t0 + timedelta(minutes=5 * i), mm) for i, mm in enumerate([10.0, 10.5, 12.0, 0.3])])
    base.guardar("wunderground", [("casa_marina", "lluvia_mm", t0 + timedelta(minutes=5), 99.0)])  # un valor mal calculado
    assert acumulado.recalcular("wunderground/casa_marina", t0) == 3
    assert [v for _, v in base.serie("wunderground", "casa_marina", "lluvia_mm")] == [0.5, 1.5, 0.3]


# ── Cada fuente ──────────────────────────────────────────────────────────────
def prueba_inamhi_cinco_minutos_en_hora_continental_y_respaldo_solo_donde_falta(monkeypatch):
    monkeypatch.setenv("CLIMA_INAMHI_API", "https://inamhi.test")
    d = {"ok": True, "intervalo_minutos": 5, "inicio": 600, "fecha": "2026-11-22", "estaciones": [{"codigo": "M0191", "mm": [0.2, None, 1.0]}],
         "temperatura": {"estaciones": [{"codigo": "M0191", "serie": [25.5]}]}}
    filas, horas = inamhi.filas_de_5min("M0191", d)
    diez = datetime(2026, 11, 22, 15, 0, tzinfo=UTC)  # las 10:00 continentales
    assert filas == [("M0191", "lluvia_mm", diez, 0.2), ("M0191", "lluvia_mm", diez + timedelta(minutes=10), 1.0), ("M0191", "temp_c", diez, 25.5)]
    assert horas == {diez}
    with pytest.raises(ValueError):
        inamhi.filas_de_5min("M0191", {"ok": False})
    # El historial por hora solo entra en las horas sin datos de 5 minutos, y sale cuando llegan.
    base.guardar("inamhi", filas)
    historial = {"filas": [{"codigo": "M0191", "hora": "2026-11-22T10:00:00", "n_lluvia": 12, "lluvia_mm": 9.0}, {"codigo": "M0191", "hora": "2026-11-22T09:00:00", "n_lluvia": 12, "lluvia_mm": 3.0, "n_temp": 12, "t_prom": 24.0},
                           {"codigo": "OTRA", "hora": "2026-11-22T09:00:00", "n_lluvia": 1, "lluvia_mm": 1.0}]}
    respaldo = datetime(2026, 11, 22, 14, 30, 30, tzinfo=UTC)
    assert inamhi.filas_de_historial(historial) == [("M0191", "lluvia_mm", respaldo, 3.0), ("M0191", "temp_c", respaldo, 24.0)]
    base.guardar("inamhi", inamhi.filas_de_historial(historial))
    monkeypatch.setattr(base, "http_json", lambda url, *a, **k: {**d, "inicio": 540})  # ahora llegan los 5 minutos de las 09:00
    inamhi.recoger(ahora=datetime(2026, 11, 22, 15, 20, tzinfo=UTC))
    assert not base.existe("inamhi", "M0191", en=respaldo)
    assert Estacion.objects.filter(fuente="inamhi").count() == 2
    # Una estación sin datos frescos no arrastra a la otra; si fallan las dos, la corrida es un fallo.
    monkeypatch.setattr(base, "http_json", lambda url, *a, **k: {"ok": False, "reason": "datos_antiguos_o_vacios"} if "-90.315" in url else {**d, "estaciones": [{"codigo": "M0221", "mm": [0.4]}]})
    assert inamhi.recoger(ahora=datetime(2026, 11, 22, 15, 20, tzinfo=UTC)) == 1
    monkeypatch.setattr(base, "http_json", lambda url, *a, **k: {"ok": False})
    with pytest.raises(ValueError):
        inamhi.recoger(ahora=datetime(2026, 11, 22, 15, 20, tzinfo=UTC))


def prueba_ioc_elige_el_sensor_vivo_y_resta_el_desfase():
    datos = [{"sensor": "ras", "slevel": 2.0 + 0.01 * i, "stime": f"2026-11-22 10:{i:02d}:00"} for i in range(8)] + [{"sensor": "rad", "slevel": 7.0, "stime": "2026-11-22 10:00:00"}] * 8
    filas = ioc.filas_de("sant", datos, {"ras": {"desfase_cm": 50}, "rad": {"desfase_cm": 540}})
    assert len(filas) == 8 and filas[0] == ("sant", "nivel_mar_m", datetime(2026, 11, 22, 10, 0, tzinfo=UTC), 1.5)
    congelado = [{"sensor": "ras", "slevel": 2.0, "stime": f"2026-11-22 10:{i:02d}:00"} for i in range(8)]
    assert ioc.filas_de("sant", congelado, {"ras": {"desfase_cm": 50}}) == []   # un sensor que no se mueve está caído
    assert "sant" in ioc.desfases() and "balt" in ioc.desfases()


def prueba_weatherlink_convierte_unidades_e_ignora_las_inactivas():
    d = {"lastTimestamp": int(AHORA.timestamp()) + 42, "dailyRain": "0.50", "rainUnit": "in", "temperature": "77", "temperatureUnit": "°F", "humidity": "80",
         "barometer": "29.92", "barometerUnit": "in Hg", "windSpeed": "10", "windSpeedUnit": "mph"}
    t, v = weatherlink.leer("pa_weatherlink", d, AHORA)
    assert t == AHORA and v == {"lluvia_dia_acum_mm": 12.7, "temp_c": 25.0, "hr_pct": 80.0, "presion_hpa": 1013.2, "viento_ms": 4.5}
    assert weatherlink.leer("x", {**d, "lastTimestamp": int((AHORA - timedelta(days=4)).timestamp())}, AHORA) is None
    assert weatherlink.leer("x", {**d, "dailyRain": "--"}, AHORA) is None


def prueba_weatherlink_guarda_la_lluvia_del_intervalo(monkeypatch):
    monkeypatch.setenv("CLIMA_WEATHERLINK_API", "https://wl.test")
    monkeypatch.setenv("CLIMA_WEATHERLINK_ESTACIONES", "abc:pa_weatherlink,zzz:desconocida")
    monkeypatch.delenv("CLIMA_RESPALDO_ERNA_API", raising=False)
    lectura = {"lastTimestamp": int((AHORA - timedelta(minutes=5)).timestamp()), "dailyRain": "10.0", "rainUnit": "mm"}
    monkeypatch.setattr(base, "http_json", lambda url, *a, **k: lectura)
    assert weatherlink.recoger(AHORA) == 1                      # la primera lectura no tiene con qué restar
    lectura.update(lastTimestamp=int(AHORA.timestamp()), dailyRain="12.5")
    assert weatherlink.recoger(AHORA) == 2 and weatherlink.recoger(AHORA) == 0   # la misma lectura no se guarda dos veces
    assert valores("weatherlink")[("lluvia_mm", AHORA)] == 2.5
    assert Estacion.objects.get(fuente="weatherlink").nombre == "Puerto Ayora (Erna)"


def prueba_tempest_agrupa_los_minutos_en_bloques_de_cinco():
    t0 = int((AHORA - timedelta(minutes=20)).timestamp())
    minuto = lambda i, lluvia: [t0 + 60 * i, 0, 3.0, 0, 0, 0, 1010.0, 24.0, 80.0, 0, 0, 0, lluvia]  # noqa: E731
    filas = tempest.filas_de("punta_estrada", [minuto(i, 0.2) for i in range(10)] + [minuto(21, 5.0), "roto", [None] * 13], AHORA)
    lluvia = sorted((t, x) for _, v, t, x in filas if v == "lluvia_mm")
    assert lluvia == [(AHORA - timedelta(minutes=20), 1.0), (AHORA - timedelta(minutes=15), 1.0)]  # el bloque en curso espera a la próxima corrida
    assert ("punta_estrada", "viento_ms", AHORA - timedelta(minutes=20), 3.0) in filas


def prueba_ambient_usa_el_acumulado_anual_y_no_reparte_un_hueco():
    ms = lambda minutos: int((AHORA - timedelta(minutes=minutos)).timestamp() * 1000)  # noqa: E731
    registros = [{"dateutc": ms(130), "yearlyrainin": 10.0, "dailyrainin": 1.0, "tempf": 77.0}, {"dateutc": ms(10), "yearlyrainin": 12.0, "dailyrainin": 0.5},
                 {"dateutc": ms(5), "yearlyrainin": 12.1, "dailyrainin": 0.6, "humidity": 90, "baromabsin": 29.92, "windspeedmph": 10}]
    filas = ambient.filas_de("miconia", registros)
    assert [(t, x) for _, v, t, x in filas if v == "lluvia_mm"] == [(AHORA - timedelta(minutes=10), 2.54)]  # las 2 pulgadas del hueco de dos horas no se cuentan
    assert ("miconia", "temp_c", AHORA - timedelta(minutes=135), 25.0) in filas and ("miconia", "presion_hpa", AHORA - timedelta(minutes=10), 1013.2) in filas


def prueba_wunderground_lee_la_pagina_y_convierte_segun_la_unidad():
    pagina = ('<div data-obs-time-utc="Sun Nov 22 2026 10:15:00 GMT-0600"></div><rain-widget-view data-status="connected" data-unit="e" data-precip-total="0.5"></rain-widget-view>'
              '<temp-widget-view data-status="connected" data-unit="m" data-temp="26.5"></temp-widget-view><wind-widget-view data-status="connected" data-unit="x" data-wind-speed="9"></wind-widget-view>'
              '<humidity-widget-view data-status="offline" data-humidity="70"></humidity-widget-view>')
    assert wunderground.leer(pagina) == {"ts": datetime(2026, 11, 22, 16, 15, tzinfo=UTC), "lluvia_dia_mm": 12.7, "temp_c": 26.5}  # unidad desconocida o sensor apagado: sin dato
    assert wunderground.leer("<html></html>") is None


def prueba_gsc_lee_los_graficos_con_su_hora_continental():
    grafico = lambda y: {"x": {"data": [{"data": [{"name": "El Junco", "x": ["2026-11-22T10:00:00Z", "2026-11-22T10:05:00Z"], "y": y}, {"name": "vacío", "x": []}]}]}}  # noqa: E731
    filas = gsc.filas_de([grafico([0.5, None]), grafico([21.0, 21.5])])
    assert filas == [("junco", "lluvia_mm", datetime(2026, 11, 22, 15, 0, tzinfo=UTC), 0.5), ("junco", "temp_c", datetime(2026, 11, 22, 15, 0, tzinfo=UTC), 21.0),
                     ("junco", "temp_c", datetime(2026, 11, 22, 15, 5, tzinfo=UTC), 21.5)]
    assert [gsc.codigo(n) for n in ("Cerro Alto", "El Mirador", "GSC")] == ["cerro_alto", "mirador", "gsc"]


# ── IERSE por el relevo ──────────────────────────────────────────────────────
@pytest.fixture
def relevo(monkeypatch, settings):
    monkeypatch.setenv("CLIMA_IERSE_API", "https://ierse.test/api")
    settings.CLIMA_RELEVO_LLAVE = "llave-del-relevo"
    return {"HTTP_X_LLAVE": "llave-del-relevo"}


def prueba_el_relevo_exige_la_llave(relevo, client, settings):
    assert client.get("/riesgos/api/clima/relevo/ierse").status_code == 403
    assert client.get("/riesgos/api/clima/relevo/ierse", HTTP_X_LLAVE="otra").status_code == 403
    assert client.post("/riesgos/api/clima/relevo/ierse", "{}", content_type="application/json").status_code == 403
    settings.CLIMA_RELEVO_LLAVE = ""   # sin llave configurada, la puerta está cerrada para todos
    assert client.get("/riesgos/api/clima/relevo/ierse", HTTP_X_LLAVE="").status_code == 403


def prueba_el_relevo_pide_recibe_y_se_pone_al_dia(relevo, client):
    hoy = datetime.now(base.GALAPAGOS)
    # Primera ronda: aún no se conocen las estaciones; solo se pide la lista.
    plan = client.get("/riesgos/api/clima/relevo/ierse", **relevo).json()
    assert [p["id"] for p in plan["pedidos"]] == ["nodos"] and plan["pedidos"][0]["url"] == "https://ierse.test/api/oper_nodes"
    nodos = [{"node_id": "n_glps05", "node_name": "Los Guayabillos", "node_lat": -0.699, "node_long": -90.342}, {"node_id": "<script>", "node_name": "x"}]
    r = client.post("/riesgos/api/clima/relevo/ierse", json.dumps({"respuestas": {"nodos": nodos}}), content_type="application/json", **relevo).json()
    assert r == {"guardadas": 0, "pendiente": True}
    e = Estacion.objects.get(fuente="ierse")
    assert (e.codigo, e.nombre, e.altitud_m, e.operador) == ("n_glps05", "Los Guayabillos", 178, "IERSE-WSN")
    # Segunda ronda: los datos de cada variable y día. Sin datos previos, empieza diez días atrás y va de a tres.
    plan = client.get("/riesgos/api/clima/relevo/ierse", **relevo).json()["pedidos"]
    assert len(plan) == 1 + 3 * 4 and plan[1]["cuerpo"]["req_node"] == "n_glps05"
    assert plan[1]["id"] == f"datos|n_glps05|RAIN|{(hoy - timedelta(days=10)).date()}"
    # El relevo entrega las respuestas tal cual. Lo que no cuadra se descarta: otra estación, otra variable, valores que no son números, fechas absurdas.
    marca = lambda t: t.strftime("%Y-%m-%dT%H:%M:%S.000")  # noqa: E731
    hace10 = (hoy - timedelta(minutes=10)).replace(second=0, microsecond=0)
    respuestas = {"nodos": nodos[:1],
                  f"datos|n_glps05|RAIN|{hoy.date()}": [{"timestamp": marca(hace10), "sensor_value": 1.5}, {"timestamp": marca(hace10 + timedelta(minutes=5)), "sensor_value": None},
                                                        {"timestamp": "ayer", "sensor_value": 1}, {"timestamp": marca(hace10), "sensor_value": "mucho"}, {"timestamp": "2020-01-01T00:00:00.000", "sensor_value": 9}],
                  f"datos|n_glps05|Pressure|{hoy.date()}": [{"timestamp": marca(hace10), "sensor_value": 101300}],
                  f"datos|inventada|RAIN|{hoy.date()}": [{"timestamp": marca(hace10), "sensor_value": 50}], f"datos|n_glps05|Otra|{hoy.date()}": [{"timestamp": marca(hace10), "sensor_value": 50}]}
    r = client.post("/riesgos/api/clima/relevo/ierse", json.dumps({"respuestas": respuestas}), content_type="application/json", **relevo).json()
    assert r == {"guardadas": 3, "pendiente": False}
    v = valores("ierse")
    assert v[("lluvia_mm", hace10.astimezone(UTC))] == 1.5 and v[("presion_hpa", hace10.astimezone(UTC))] == 1013.0 and v[("lluvia_mm", (hace10 + timedelta(minutes=5)).astimezone(UTC))] is None
    assert Corrida.objects.filter(fuente="ierse", ok=True).exists() and Horaria.objects.filter(estacion=e, variable="lluvia_mm").exists()
    # Ya al día: la siguiente ronda solo pide hoy (y ayer, si acaba de pasar la medianoche).
    plan = client.get("/riesgos/api/clima/relevo/ierse", **relevo).json()["pedidos"]
    assert len(plan) in (5, 9) and plan[-1]["id"].endswith(str(hoy.date()))


def prueba_si_el_relevo_no_logra_hablar_con_ierse_queda_como_fallo(relevo, client):
    r = client.post("/riesgos/api/clima/relevo/ierse", json.dumps({"respuestas": {}, "errores": ["nodos: TimeoutError"]}), content_type="application/json", **relevo).json()
    assert r == {"guardadas": 0, "pendiente": False}
    c = Corrida.objects.get(fuente="ierse")
    assert not c.ok and "TimeoutError" in c.error
    assert client.post("/riesgos/api/clima/relevo/ierse", "esto no es json", content_type="application/json", **relevo).json() == {"error": "formato inesperado"}


def prueba_ierse_directo_solo_si_se_pide(monkeypatch):
    monkeypatch.setenv("CLIMA_IERSE_API", "https://ierse.test/api")
    monkeypatch.delenv("CLIMA_IERSE_DIRECTO", raising=False)
    assert "ierse" not in fuentes.activas()
    monkeypatch.setenv("CLIMA_IERSE_DIRECTO", "1")
    assert "ierse" in fuentes.activas()


# ── Mar y mareas ─────────────────────────────────────────────────────────────
def prueba_el_modelo_del_mar_se_guarda_en_su_tabla(monkeypatch):
    monkeypatch.setenv("CLIMA_OPENMETEO_MARINE_API", "https://mar.test/v1/marine")
    puerto = {"minutely_15": {"time": ["2026-11-22T10:00", "2026-11-22T10:15"], "sea_level_height_msl": [0.4, 0.5]}, "hourly": {"time": ["2026-11-22T10:00"], "wave_height": [1.2]}}
    monkeypatch.setattr(base, "http_json", lambda url, *a, **k: [puerto, puerto])
    assert mar_modelo.recoger(AHORA) == 4 and mar_modelo.recoger(AHORA + timedelta(minutes=10)) == 0  # una vez por hora
    fila = MarHora.objects.get(puerto="isabela", fuente="openmeteo", hora=datetime(2026, 11, 22, 10, 0, tzinfo=UTC))
    assert (fila.nivel_m, fila.ola_m) == (0.4, 1.2)
    # Convive con Stormglass en la misma hora sin pisarse.
    MarHora.objects.create(puerto="isabela", fuente="stormglass", hora=fila.hora, ola_m=2.0, obtenido=AHORA)
    assert MarHora.objects.filter(puerto="isabela", hora=fila.hora).count() == 2


def prueba_las_mareas_del_panel_salen_de_las_tablas(client):
    from clima import mar, mareas

    ahora = datetime.now(UTC)
    base.guardar("ioc", [("sant", "nivel_mar_m", ahora - timedelta(minutes=10 * i), 2.0) for i in range(30)])
    mar.guardar_mareas("san-cristobal", [(ahora + timedelta(hours=2), "P", 1.9), (ahora + timedelta(hours=8), "B", 0.3)], "inocar", "MLWS")
    mar.guardar_mareas("isabela", [(ahora + timedelta(hours=3), "P", 0.7)], "stormglass", "MSL")
    MarHora.objects.create(puerto="isabela", fuente="stormglass", hora=ahora + timedelta(hours=5), ola_m=2.2, fondo_m=1.4, periodo_s=12.0, viento_ms=6.0, obtenido=ahora)
    MarHora.objects.create(puerto="isabela", fuente="openmeteo", hora=ahora + timedelta(hours=5), ola_m=9.9, obtenido=ahora)
    MarHora.objects.create(puerto="san-cristobal", fuente="openmeteo", hora=ahora + timedelta(hours=5), ola_m=1.1, obtenido=ahora)
    m = mareas.calcular(ahora)
    sant = m["estaciones"]["sant"]
    assert len(sant["pred_cm"]) == len(sant["obs_cm"]) == 864 and sant["anomalia_fuente"] == "mareógrafo, últimas 6 h" and sant["proximos"]
    assert m["modelo"]["baquerizo"]["pleamares"] == [{"t": (ahora + timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M:%SZ"), "nivel_m": 1.9}]
    assert "INOCAR" in m["modelo"]["baquerizo"]["pleamares_fuente"] and m["modelo"]["baquerizo"]["ola_fuente"] == "Open-Meteo"   # sin Stormglass, el otro modelo
    assert m["modelo"]["villamil"]["ola_max_m"] == 2.2 and m["modelo"]["villamil"]["ola_fuente"] == "Stormglass" and "Stormglass" in m["modelo"]["villamil"]["pleamares_fuente"]
    # La API da además el mar hora a hora, para dibujarlo.
    isabela = next(p for p in client.get("/riesgos/api/clima/mar").json()["puertos"] if p["puerto"] == "isabela")
    assert isabela["mar_72h"]["modelo"] == "Stormglass" and isabela["mar_72h"]["horas"][0][1:5] == [2.2, 1.4, 12.0, 6.0]


# ── Estacionalidad, descargas y cargas históricas ────────────────────────────
def prueba_la_estacionalidad_sale_de_las_series_guardadas(tmp_path):
    from clima import estacionalidad
    from clima.management.commands.clima_importar import importar_fcd

    archivo = tmp_path / "fcd.csv"
    lineas = ["observation_date,precipitation"] + [f"{datetime(2020, 1, 1).date() + timedelta(days=i)},{2.0 if i % 10 == 0 else 0.0}" for i in range(800)] + ["2022-99-99,1", "2022-04-01,"]
    archivo.write_text("\n".join(lineas))
    assert importar_fcd("puerto-ayora", archivo) == 800
    dias = estacionalidad.dias_de("fcd/puerto-ayora")
    assert len(dias) == 800 and dias[datetime(2020, 1, 1).date()] == 2.0
    serie = next(s for s in estacionalidad.calcular()["series"] if s["id"] == "puerto-ayora")
    assert serie["dias"] == 800 and serie["desde"] == "2020-01-01" and serie["mensual"][0]["n"] == 3 and serie["operador"] == "FCD + INAMHI"
    assert not any(s["id"] == "bellavista" for s in estacionalidad.calcular()["series"])   # sin datos no hay serie


def prueba_las_descargas_llevan_los_datos_y_la_licencia_de_cada_fuente(tmp_path):
    import zipfile

    from clima import descargas
    from clima.models import EstacionDanada

    base.estacion("ierse", "n1", "Los Guayabillos", "Santa Cruz", -0.6991, -90.342, 178, "IERSE-WSN")
    t = datetime(2026, 10, 31, 23, 55, tzinfo=UTC)
    base.guardar("ierse", [("n1", "lluvia_mm", t, 1.5), ("n1", "lluvia_mm", t + timedelta(minutes=10), 2.0)])
    base.guardar("goes", [("la-cascada", "frio_pct", t, 12.0)])
    base.guardar("gsc", [("junco", "lluvia_dia_mm", datetime(2015, 6, 8, 5, 0, tzinfo=UTC), 2.54)])
    base.guardar("fcd", [("puerto-ayora", "lluvia_dia_mm", datetime(1965, 1, 2, 5, 0, tzinfo=UTC), 7.0)])
    base.resumir()
    EstacionDanada.objects.create(estacion=Estacion.objects.get(codigo="n1"), desde=t, motivo="obstruido")
    assert descargas.publicar(tmp_path, hoy=datetime(2026, 11, 22).date()) == 2
    carpeta = tmp_path / "descargas"
    with zipfile.ZipFile(carpeta / "clima_galapagos_2026-10.zip") as z:
        assert z.read("clima_galapagos_2026-10.csv").decode().splitlines() == ["ts_utc,fuente,estacion,variable,valor", "2026-10-31T23:55:00Z,ierse,n1,lluvia_mm,1.5"]  # el satélite no entra
    assert (carpeta / "historico_lluvia_diaria.csv").read_text().splitlines()[1:] == ["1965-01-02,fcd,puerto-ayora,7.0", "2015-06-08,gsc,junco,2.54"]
    leeme = (carpeta / "LEEME.txt").read_text()
    for texto in ("CC BY-NC-ND 4.0", "CC BY-NC-SA", "Galapagos Science Center", "INAMHI", "Fundación Charles Darwin", "jamaya@usfq.edu.ec", "ierse/n1: obstruido"):
        assert texto in leeme
    indice = json.loads((carpeta / "indice.json").read_text())
    assert {a["archivo"] for a in indice["archivos"]} == {"clima_galapagos_2026-10.zip", "clima_galapagos_2026-11.zip", "historico_lluvia_diaria.csv", "estaciones.csv", "LEEME.txt"}
    # Un mes cerrado no se vuelve a escribir.
    marca = (carpeta / "clima_galapagos_2026-10.zip").stat().st_mtime_ns
    descargas.publicar(tmp_path, hoy=datetime(2027, 3, 1).date())
    assert (carpeta / "clima_galapagos_2026-10.zip").stat().st_mtime_ns == marca


# ── Satélite ─────────────────────────────────────────────────────────────────
def prueba_el_satelite_agrega_por_zona_y_deja_el_resumen_en_la_base():
    import numpy as np

    from clima.satelite import colector, goes

    zonas = goes.zonas()
    assert list(zonas) == ["la-cascada", "santa-cruz-alta", "san-cristobal", "isabela"]
    ahora = datetime.now(UTC).replace(second=0, microsecond=0)
    t0 = ahora - timedelta(minutes=20)
    caja = zonas["la-cascada"]["bbox"]
    lat = np.array([(caja[1] + caja[3]) / 2, (caja[1] + caja[3]) / 2, 5.0])
    lon = np.array([(caja[0] + caja[2]) / 2, (caja[0] + caja[2]) / 2, -80.0])
    colector.guardar(colector.agregados("c13", np.array([210.0, 250.0, 200.0]), lat, lon, zonas, t0))
    colector.guardar(colector.agregados("rrqpe", np.array([12.0, np.nan, 99.0]), lat, lon, zonas, t0))
    v = valores("goes", "la-cascada")
    assert v[("tb_min_k", t0)] == 210.0 and v[("frio_pct", t0)] == 50.0 and v[("lluvia_sat_max_mmh", t0)] == 12.0
    assert valores("goes", "isabela")[("tb_min_k", t0)] is None            # sin píxeles en la zona: vacío, no cero
    assert sorted(c[2] for c in colector.rejilla(lat, lon, np.array([210.0, 250.0, 200.0]), "min", 235.0)) == [200.0, 210.0]   # una celda por sitio, con su mínimo
    r = colector.resumen(zonas, ahora, {"c13": {"ts": colector.iso(t0), "celdas": [[0, 0, 210.0]], "latencia_min": 12.0}}, {"ok": True})
    assert r["zonas"]["la-cascada"]["series"]["tb_min_k"] == [[colector.iso(t0), 210.0]] and r["zonas"]["la-cascada"]["vigilancia"]["estado"] == "vigilancia"
    assert "no es lluvia medida" in r["advertencia"] and r["nucleos"] == [[0, 0, 210.0]] and r["ultima_imagen"]["c13"]["latencia_min"] == 12.0
    colector.escribir_estado("satelite", r, ahora)
    assert Estado.objects.get(clave="satelite").datos["zonas"]["isabela"]["evaluada"] is False

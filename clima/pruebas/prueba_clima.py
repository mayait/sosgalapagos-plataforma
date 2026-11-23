# SOS Galápagos · © 2026 Universidad San Francisco de Quito (USFQ) · Autor: Julián Maya <jamaya@usfq.edu.ec>
# Todos los derechos reservados. Usar, copiar, modificar o derivar de este código requiere permiso escrito del autor (ver LICENSE).
"""Pruebas del clima: guardar mediciones, resúmenes por hora, fuentes, panel, pronóstico y API."""
from datetime import datetime, timedelta, timezone

import pytest

from clima import consultas
from clima.fuentes import base
from clima.models import Corrida, Estacion, Horaria, Observacion

pytestmark = pytest.mark.django_db(transaction=True)  # guardar usa COPY y tablas temporales
AHORA = datetime.now(timezone.utc).replace(minute=20, second=0, microsecond=0)
iso = lambda t: t.strftime("%Y-%m-%dT%H:%M:%SZ")  # noqa: E731
HORA = AHORA.replace(minute=0) - timedelta(hours=1)


@pytest.fixture
def cargada():
    """Una estación de IERSE con una hora de lluvia y temperatura, una zona del satélite y tres corridas."""
    base.estacion("ierse", "n1", "Los Guayabillos", "Santa Cruz", -0.6991, -90.342, 178, "IERSE")
    filas = [("n1", "lluvia_mm", HORA + timedelta(minutes=5 * i), 0.5) for i in range(12)]
    filas += [("n1", "temp_c", HORA + timedelta(minutes=30 * i), 20 + 2 * i) for i in range(2)]
    assert base.guardar("ierse", filas) == 14
    assert base.guardar("goes", [("la-cascada", "frio_pct", HORA, 12.0)]) == 1
    base.resumir()
    Corrida.objects.create(ts=AHORA - timedelta(minutes=10), fuente="ierse", ok=True, registros=12, segundos=1.5)
    Corrida.objects.create(ts=AHORA - timedelta(minutes=5), fuente="ierse", ok=False, registros=0, segundos=30.0, error="sin respuesta")
    Corrida.objects.create(ts=AHORA - timedelta(minutes=5), fuente="gsc", ok=True, registros=40, segundos=6.0)


def prueba_guarda_estaciones_y_mediciones_sin_duplicar(cargada):
    e = Estacion.objects.get(fuente="ierse", codigo="n1")
    assert e.nombre == "Los Guayabillos" and abs(e.punto.x + 90.342) < 1e-6 and e.ultima == HORA + timedelta(minutes=55) and e.primera == HORA
    assert Estacion.objects.filter(fuente="goes", codigo="la-cascada").exists()  # las zonas del satélite se crean solas
    assert Observacion.objects.count() == 15
    # Repetir no duplica; un valor distinto reemplaza al anterior; un NaN se guarda como vacío.
    base.guardar("ierse", [("n1", "lluvia_mm", HORA, 2.5), ("n1", "lluvia_mm", HORA + timedelta(minutes=5), float("nan"))])
    assert Observacion.objects.count() == 15
    assert Observacion.objects.get(estacion=e, variable="lluvia_mm", ts=HORA).valor == 2.5
    assert Observacion.objects.get(estacion=e, variable="lluvia_mm", ts=HORA + timedelta(minutes=5)).valor is None
    base.resumir(HORA)
    assert Horaria.objects.get(estacion=e, variable="lluvia_mm", hora=HORA).suma == pytest.approx(7.5)


def prueba_resume_por_hora(cargada):
    lluvia = Horaria.objects.get(estacion__codigo="n1", variable="lluvia_mm", hora=HORA)
    assert lluvia.suma == pytest.approx(6.0) and lluvia.n == 12
    temperatura = Horaria.objects.get(estacion__codigo="n1", variable="temp_c", hora=HORA)
    assert temperatura.media == pytest.approx(21.0) and temperatura.maximo == 22


def prueba_preguntar_y_borrar_distingue_las_filas_de_respaldo(cargada):
    respaldo = HORA + timedelta(hours=1, minutes=30, seconds=30)
    base.guardar("ierse", [("n1", "lluvia_mm", respaldo, 4.0)])
    assert base.ultimo("ierse", "n1", "lluvia_mm") == respaldo and base.ultimo("ierse", "n1", "lluvia_mm", de_cinco_min=True) == HORA + timedelta(minutes=55)
    assert base.existe("ierse", "n1", en=HORA) and not base.existe("ierse", "n1", en=HORA + timedelta(seconds=1))
    assert base.serie("ierse", "n1", "lluvia_mm", antes_de=HORA + timedelta(minutes=5), orden="DESC", limite=1) == [(HORA, 0.5)]
    assert base.borrar("ierse", "n1", "lluvia_mm", desde=HORA, de_respaldo=True) == 1
    assert Observacion.objects.filter(variable="lluvia_mm").count() == 12
    assert base.ultimo("nadie") is None


def prueba_la_api_da_series_estaciones_y_salud(cargada, client):
    estaciones = client.get("/riesgos/api/clima/estaciones").json()["estaciones"]
    assert [e["id"] for e in estaciones] == ["ierse/n1"]  # las zonas del satélite no son estaciones
    assert estaciones[0]["lluvia_mm"]["24h"] == 6.0
    serie = client.get("/riesgos/api/clima/serie", {"estacion": "ierse/n1", "desde": iso(HORA - timedelta(hours=1)), "hasta": iso(HORA + timedelta(hours=1))}).json()
    assert serie["valores"] == [None, 6.0]
    dia = client.get("/riesgos/api/clima/serie", {"estacion": "ierse/n1", "paso": "dia", "desde": iso(HORA - timedelta(days=1)), "hasta": iso(HORA + timedelta(hours=1))}).json()
    assert sum(v or 0 for v in dia["valores"]) == 6.0
    assert client.get("/riesgos/api/clima/serie", {"estacion": "no/existe"}).status_code == 404
    assert client.get("/riesgos/api/clima/serie", {"estacion": "ierse/n1", "variable": "otra"}).status_code == 400
    salud = client.get("/riesgos/api/clima/salud").json()
    ierse = next(f for f in salud["fuentes"] if f["fuente"] == "ierse")
    assert ierse["corridas"] == 2 and ierse["bien"] == 1 and ierse["acierto_pct"] == 50
    assert salud["observaciones"] == 15 and "copia" not in salud


# ── Pronóstico: bajar, guardar, publicar y verificar ─────────────────────────
def _respuesta(base_utc, mm_por_hora, horas=72):
    """Una respuesta como la de los modelos deterministas: 7 puntos, dos modelos."""
    tiempos = [(base_utc + timedelta(hours=i)).strftime("%Y-%m-%dT%H:%M") for i in range(horas)]
    return [{"hourly": {"time": tiempos, "precipitation_gfs_seamless": [mm_por_hora] * horas, "precipitation_icon_seamless": [0.0] * horas}} for _ in range(7)]


def prueba_el_dia_del_modelo_es_el_de_galapagos():
    from clima.fuentes import modelos

    # 24 horas que terminan entre las 07:00 y las 06:00 UTC del día siguiente = el día de Galápagos.
    inicio = datetime(2026, 11, 10, 7, 0, tzinfo=timezone.utc)
    horas = [(inicio + timedelta(hours=i)).strftime("%Y-%m-%dT%H:%M") for i in range(30)]
    dias, bloques = modelos.sumar(horas, [[1.0, 2.0]] * 30)
    assert dias == {"2026-11-10": [24.0, 48.0]}  # el día incompleto no se cuenta
    assert bloques["2026-11-10T00"] == [6.0, 12.0] and "2026-11-11T06" not in bloques


def prueba_el_cape_se_guarda_como_maximo_del_dia():
    from clima.fuentes import modelos

    # El CAPE es instantáneo: la hora t cuenta para el día local de t (06:00 UTC = 00:00 en Galápagos).
    inicio = datetime(2026, 11, 10, 6, 0, tzinfo=timezone.utc)
    horas = [(inicio + timedelta(hours=i)).strftime("%Y-%m-%dT%H:%M") for i in range(30)]
    cape = [100.0 * i for i in range(30)]
    cape[5] = None
    assert modelos.maximos_diarios(horas, cape) == {"2026-11-10": 2300}  # el día siguiente, con 6 horas, no cuenta

    respuesta = [{"hourly": {"time": horas, "precipitation_gfs_seamless": [1.0] * 30, "cape_gfs_seamless": cape,
                             "precipitation_ecmwf_aifs025_single": [1.0] * 30, "cape_ecmwf_aifs025_single": [None] * 30}}] * 7
    gfs = modelos.resumen_determinista("gfs_seamless", respuesta)["puerto-ayora"]
    assert gfs["cape_max"] == {"2026-11-10": 2300} and "dias" in gfs
    assert "cape_max" not in modelos.resumen_determinista("ecmwf_aifs025_single", respuesta)["puerto-ayora"]  # AIFS no da CAPE


def prueba_guarda_solo_lo_que_cambia_y_verifica(cargada):
    from clima import pronostico
    from clima.fuentes import modelos
    from clima.models import EstacionDanada, PronosticoCorrida, PronosticoEmitido, PronosticoModelo

    dia = (AHORA.astimezone(consultas.GALAPAGOS) - timedelta(days=1)).date()  # ayer en Galápagos
    inicio = datetime.combine(dia - timedelta(days=1), datetime.min.time(), timezone.utc) + timedelta(hours=7)
    obtenido = datetime.combine(dia - timedelta(days=1), datetime.min.time(), timezone.utc) + timedelta(hours=12)
    respuesta = _respuesta(inicio, 1.0)
    for hora, modelo in ((0, "gfs_seamless"), (0, "icon_seamless"), (1, "gfs_seamless")):  # la segunda del GFS dice lo mismo: no añade filas
        modelos._guardar(modelo, "determinista", obtenido + timedelta(hours=hora - 6), None, obtenido + timedelta(hours=hora), modelos.resumen_determinista(modelo, respuesta))
    assert PronosticoCorrida.objects.count() == 3
    leidas, nuevas = pronostico.guardar_modelos()
    assert leidas == 3 and nuevas == PronosticoModelo.objects.count() and nuevas > 0
    fila = PronosticoModelo.objects.get(punto="puerto-ayora", modelo="gfs_seamless", fecha=dia)
    assert fila.mm == 24.0 and fila.anticipacion == 1
    assert pronostico.guardar_modelos()[1] == 0  # repetir no duplica

    # Un conjunto: se guarda la mediana, el percentil 90 y la fracción de miembros con lluvia fuerte.
    conjunto = PronosticoCorrida.objects.create(modelo="gfs025", tipo="conjunto", referencia=obtenido, recibido=obtenido + timedelta(hours=2),
                                                datos={"puerto-ayora": {"dias": {str(dia): [0.0, 10.0, 30.0, 40.0]}, "bloques6h": {}}})
    f = pronostico.filas_de_corrida(conjunto)[0]
    assert (f.modelo, f.mm, f.miembros, f.prob20) == ("conjunto:gfs025", 20.0, 4, 0.5)

    # Lo publicado.
    publicado = {"generado": iso(obtenido), "hoy_local": str(dia - timedelta(days=1)), "zonas": {"la-cascada": {"puntos": [
        {"id": "puerto-ayora", "dias": [{"fecha": str(dia), "prob": {"10": 0.9, "20": 0.8, "50": 0.1}, "consenso": 0.9, "n_modelos": 7, "mm_modelos_mediana": 22.0, "nivel": "alta", "calibrado": True}]}]}}}
    assert pronostico.guardar_emitido(publicado) == 1 and pronostico.guardar_emitido(publicado) == 0
    assert PronosticoEmitido.objects.get().anticipacion == 1

    # Lo que llovió: una estación de Puerto Ayora con el día completo y 30 mm.
    base.estacion("inamhi", "M0191", "Puerto Ayora", "Santa Cruz", -0.74, -90.31, 6, "INAMHI")
    amanecer = datetime.combine(dia, datetime.min.time(), timezone.utc) + timedelta(hours=6)
    base.guardar("inamhi", [("M0191", "lluvia_mm", amanecer + timedelta(hours=h), 1.25) for h in range(24)])
    base.resumir()
    v = pronostico.verificar(dias=10)
    assert v["dias_observados"] == 1 and v["dias_de_lluvia_fuerte"] == 1
    gfs = next(m for m in v["por_modelo"] if m["modelo"] == "gfs_seamless" and m["anticipacion"] == 1)
    assert gfs == {"modelo": "gfs_seamless", "anticipacion": 1, "dias": 1, "error_medio_mm": 6.0, "sesgo_mm": -6.0, "dias_de_lluvia_fuerte": 1, "avisados": 1, "falsas_alarmas": 0, "brier": None}
    icon = next(m for m in v["por_modelo"] if m["modelo"] == "icon_seamless" and m["anticipacion"] == 1)
    assert icon["avisados"] == 0 and icon["sesgo_mm"] == -30.0  # no avisó: se le pasó
    assert v["publicado"][0]["brier"] == pytest.approx(0.04) and v["publicado"][0]["punto"] == "puerto-ayora"

    # Un sensor marcado como dañado no cuenta como observación.
    EstacionDanada.objects.create(estacion=Estacion.objects.get(codigo="M0191"), variable="lluvia_mm", desde=amanecer - timedelta(days=2), motivo="prueba")
    assert pronostico.verificar(dias=10)["dias_observados"] == 0


def prueba_baja_los_modelos_a_la_base_y_publica_la_senal(monkeypatch):
    """Una hora de pronóstico de punta a punta, con la red simulada: corridas guardadas y pronóstico con la forma que lee el panel."""
    from clima import senal
    from clima.fuentes import modelos
    from clima.models import PronosticoCorrida

    ahora = datetime(2026, 11, 22, 15, 0, tzinfo=timezone.utc)   # las 9 de la mañana en Galápagos
    monkeypatch.setenv("CLIMA_OPENMETEO_FORECAST_API", "https://modelos.test/v1/forecast")
    monkeypatch.setenv("CLIMA_OPENMETEO_ENSEMBLE_API", "https://conjuntos.test/v1/ensemble")
    inicio = datetime(2026, 11, 21, 0, 0, tzinfo=timezone.utc)
    tiempos = [(inicio + timedelta(hours=i)).strftime("%Y-%m-%dT%H:%M") for i in range(168)]
    corrida = int((ahora - timedelta(hours=9)).timestamp())

    def red(url, cuerpo=None, **k):
        if url.endswith("/meta.json"):
            if "dwd_icon_eps" in url:
                raise TimeoutError  # metadatos caídos: la hora de la corrida no se conoce
            return {"last_run_initialisation_time": corrida, "last_run_availability_time": corrida + 6 * 3600}
        if "modelos.test" in url:
            return [{"hourly": {"time": tiempos, **{f"precipitation_{m}": [2.0] * 168 for m in modelos.DETERMINISTAS}}} for _ in range(7)]
        return [{"hourly": {"time": tiempos, "precipitation": [1.0] * 168, "precipitation_member01": [3.0] * 168}} for _ in range(7)]

    monkeypatch.setattr(modelos.base, "http_json", red)
    assert modelos.recoger(ahora) == 13                    # 8 deterministas y 5 conjuntos, todos nuevos
    assert modelos.recoger(ahora + timedelta(minutes=30)) == 0   # una vez por hora basta
    assert modelos.recoger(ahora + timedelta(hours=1)) == 0      # misma corrida: nada nuevo, y no se repiten filas
    assert PronosticoCorrida.objects.count() == 13
    icon = PronosticoCorrida.objects.get(modelo="icon_global")
    assert icon.corrida is None and icon.referencia == ahora.replace(hour=12)
    ifs = PronosticoCorrida.objects.get(modelo="ecmwf_ifs")
    assert ifs.corrida == ahora - timedelta(hours=9) and ifs.datos["puerto-ayora"]["dias"]["2026-11-22"] == 48.0 and len(ifs.datos["puerto-ayora"]["horario"]["mm"]) == 168
    assert PronosticoCorrida.objects.get(modelo="gfs025").datos["el-junco"]["bloques6h"]["2026-11-22T06"] == [6.0, 18.0]

    p = senal.publicado(ahora + timedelta(hours=1))
    assert set(p) == {"generado", "generado_local", "hoy_local", "modelos", "zonas", "reglas"} and p["hoy_local"] == "2026-11-22"
    assert len(p["modelos"]) == 13 and all(m["vigente"] for m in p["modelos"])
    assert next(m for m in p["modelos"] if m["id"] == "gfs_seamless")["corrida_local"] == "2026-11-22T00:00"
    punto = p["zonas"]["la-cascada"]["puntos"][1]
    assert punto["id"] == "puerto-ayora" and [d["fecha"] for d in punto["dias"]][:2] == ["2026-11-22", "2026-11-23"]
    assert punto["dias"][0]["n_modelos"] >= 4 and punto["dias"][0]["mm_modelos_mediana"] == 48.0 and "20" in punto["dias"][0]["prob"]
    assert punto["bloques6h"][0] == {"inicio": "2026-11-22T06:00", "n_conjuntos": 5, "mediana": 12.0, "p90": 16.8}
    assert punto["detalle"]["modelo"] == "ECMWF IFS 9 km" and punto["detalle"]["hora_local_fin"][0] == "2026-11-22T11:00"
    # Con corridas viejas no se publica ninguna cifra: mejor nada que un pronóstico caducado.
    viejo = senal.publicado(ahora + timedelta(days=3))
    assert not any(m["vigente"] for m in viejo["modelos"]) and viejo["zonas"]["la-cascada"]["puntos"][1]["dias"] == []


def prueba_la_lluvia_de_un_sensor_danado_no_se_publica(cargada, client):
    from clima.models import EstacionDanada

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


def prueba_el_panel_se_genera_desde_esta_base(cargada, tmp_path, settings):
    import json

    from clima import panel
    from clima.models import EstacionDanada, Estado

    settings.CLIMA_SALIDA = str(tmp_path / "datos")
    Estado.objects.create(clave="satelite", datos={"generado": "x"}, generado=AHORA)
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


def prueba_la_linea_del_tiempo_lee_la_lluvia_de_esta_base(cargada):
    from reportes import clima as panel

    assert panel.estaciones_con_lluvia() == [{"id": "ierse/n1", "nombre": "Los Guayabillos", "isla": "Santa Cruz"}]
    inicio, valores = panel.lluvia_por_hora("ierse/n1", HORA - timedelta(hours=1), HORA + timedelta(hours=1))
    assert inicio == HORA - timedelta(hours=1) and valores == [None, 6.0]


def prueba_la_tabla_del_inocar_se_pide_dia_por_dia(monkeypatch, settings):
    """Una página por día: si una trae menos días de lo prometido, no queda un hueco en la curva de marea."""
    from datetime import date

    from clima import mar

    settings.CLIMA_INOCAR_MAREAS_URL = "prueba://{cp}/{fecha}"
    pedidas = []
    monkeypatch.setattr(mar, "_bajar", lambda url, *a, **k: pedidas.append(url) or b"")
    mar.actualizar_inocar(dias=9, hoy=date(2026, 11, 22))
    santa_cruz = sorted(u.rsplit("/", 1)[1] for u in pedidas if u.startswith("prueba://30/"))
    assert santa_cruz == [f"2026-11-{d}" for d in range(22, 31)]

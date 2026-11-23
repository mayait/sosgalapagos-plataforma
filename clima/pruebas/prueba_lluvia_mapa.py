# SOS Galápagos · © 2026 Universidad San Francisco de Quito (USFQ) · Autor: Julián Maya <jamaya@usfq.edu.ec>
# Licencia Apache 2.0 (ver LICENSE y NOTICE): puede reutilizarse dando crédito.
"""Pruebas del mapa de lluvia de los modelos. Sin red: Open-Meteo se simula."""
import base64
import datetime as dt
import json

from clima import lluvia_mapa as lm


def prueba_codificacion_de_lluvia_y_viento():
    assert lm.codificar_lluvia(0) == 0
    assert lm.codificar_lluvia(None) == 255
    assert abs((lm.codificar_lluvia(25) / 10) ** 2 - 25) < 0.01
    assert lm.codificar_lluvia(10_000) == 254
    assert lm.codificar_viento(0) == 128
    assert lm.codificar_viento(-100) == 0 and lm.codificar_viento(100) == 254


def prueba_viento_del_sureste_sopla_hacia_el_noroeste():
    u, v = lm.componentes(10, 135)   # viene del SE
    assert u < 0 and v > 0           # va hacia el oeste y el norte


def prueba_rejilla_de_norte_a_sur():
    lats, lons = lm.rejilla((-1, 1, -91, -90), 0.5)
    assert lats == [1, 0.5, 0, -0.5, -1] and lons == [-91, -90.5, -90]


def prueba_exportar(tmp_path, monkeypatch):
    ahora = dt.datetime(2026, 11, 22, 13, 30, tzinfo=dt.timezone.utc)
    horas = [f"2026-11-21T{h:02d}:00" for h in range(0, 24, 3)] + [f"2026-11-22T{h:02d}:00" for h in range(0, 24, 3)] + \
            [f"2026-11-23T{h:02d}:00" for h in range(0, 24, 3)]

    def falso_pedir(api, puntos, modelos, dias, pausa):
        h = {"time": horas}
        for m in modelos:
            h[f"precipitation_{m}"] = [1.2] * len(horas)
            h[f"wind_speed_10m_{m}"] = [5.0] * len(horas)
            h[f"wind_direction_10m_{m}"] = [90.0] * len(horas)
        return [{"hourly": h} for _ in puntos]

    monkeypatch.setattr(lm, "_pedir", falso_pedir)
    monkeypatch.setattr(lm, "corrida", lambda api, meta: (dt.datetime(2026, 11, 22, 0, tzinfo=dt.timezone.utc), None))
    ruta = lm.exportar(tmp_path, ahora=ahora, horas=24, caja=(-1, 0, -91, -90), paso=0.5, api="x")
    d = json.loads(ruta.read_text())
    assert d["rejilla"] == {"norte": 0, "oeste": -91, "paso": 0.5, "nlat": 3, "nlon": 3}
    # El primer cuadro que se muestra es el bloque en curso (12:00–15:00 UTC)
    assert d["horas"][d["inicio"]] == "2026-11-22T15:00Z"
    assert d["horas"][0] == "2026-11-21T15:00Z"   # 24 h antes, para el acumulado
    m = d["modelos"][0]
    assert m["corrida"] == "2026-11-22T00:00Z"
    assert base64.b64decode(m["lluvia"][0])[0] == lm.codificar_lluvia(1.2)
    assert base64.b64decode(m["u"][0])[0] == lm.codificar_viento(-5.0)   # del este, hacia el oeste
    assert not lm.hay_corrida_nueva(tmp_path, api="x")                       # recién escrito
    import time
    assert not lm.hay_corrida_nueva(tmp_path, api="x", ahora=time.time() + 6 * 3600)  # misma corrida


def prueba_sin_metadatos_no_se_gasta_la_cuota(tmp_path, monkeypatch):
    """Si los metadatos fallan, no se refresca en cada pasada: solo cuando el archivo ya es viejo."""
    import time
    (tmp_path / lm.NOMBRE).write_text('{"modelos": []}')
    monkeypatch.setattr(lm, "corrida", lambda api, meta: (None, None))
    ahora = time.time()
    assert not lm.hay_corrida_nueva(tmp_path, api="x", ahora=ahora + 1 * 3600)
    assert not lm.hay_corrida_nueva(tmp_path, api="x", ahora=ahora + 8 * 3600)
    assert lm.hay_corrida_nueva(tmp_path, api="x", ahora=ahora + 13 * 3600)

# SOS Galápagos · © 2026 Universidad San Francisco de Quito (USFQ) · Autor: Julián Maya <jamaya@usfq.edu.ec>
# Licencia Apache 2.0 (ver LICENSE y NOTICE): puede reutilizarse dando crédito.
"""Pruebas de la lluvia estimada PDIR-Now (lector con rejillas sintéticas) y del fondo GeoColor de GIBS. Sin red."""
import array
import base64
import datetime as dt
import gzip
import json
import sys

import pytest

from clima.satelite import gibs, goes, pdir

UTC = dt.timezone.utc


def _archivo(celdas, filas=pdir.FILAS, columnas=pdir.COLUMNAS):
    """Archivo PDIR-Now sintético (gzip): ceros salvo {(fila, columna): valor en mm/h × 100}."""
    a = array.array("h", bytes(2 * filas * columnas))
    for (f, c), v in celdas.items():
        a[f * columnas + c] = v
    if sys.byteorder != "little":
        a.byteswap()
    return gzip.compress(a.tobytes(), compresslevel=1)


def prueba_geometria_de_la_rejilla_global():
    assert pdir.fila_de(59.98) == 0 and pdir.columna_de(0.02) == 0
    assert pdir.centro(0, 0) == (59.98, 0.02)
    f, c = pdir.fila_de(-0.68), pdir.columna_de(-90.33)
    la, lo = pdir.centro(f, c)
    assert abs(la + 0.68) <= 0.02 and abs(lo + 90.33) <= 0.02   # oeste = lon + 360, de vuelta a −180…180


def prueba_una_celda_en_la_cascada_cae_en_la_cascada():
    """Rejilla real de 3000 × 9000: una sola celda con lluvia en la cuenca alta de La Cascada."""
    f, c = pdir.fila_de(-0.68), pdir.columna_de(-90.33)
    r = pdir.leer_gz(_archivo({(f, c): 1234, (f + 1, c): -9999}))
    zonas = goes.zonas()
    z = pdir.por_zona(r, zonas)
    assert z["la-cascada"]["max_mmh"] == 12.34
    assert z["santa-cruz-alta"]["max_mmh_25km"] == 12.34
    assert z["san-cristobal"]["max_mmh"] == 0 and z["isabela"]["max_mmh"] == 0
    # La celda queda en su sitio dentro del recorte
    i, j = f - r["fila0"], c - r["col0"]
    assert r["mmh"][i][j] == 12.34 and r["mmh"][i + 1][j] is None


def prueba_cada_zona_tiene_al_menos_una_celda():
    r = pdir.leer_gz(_archivo({}))
    for zid, v in pdir.por_zona(r, goes.zonas()).items():
        assert v["max_mmh"] == 0, zid   # 0 y no None: la zona toca al menos una celda


def prueba_sin_dato_no_es_cero():
    r = {"fila0": 0, "col0": 0, "mmh": [[None, None], [None, None]]}
    caja = [pdir.LON0 - 0.02, pdir.LAT0 - 0.06, pdir.LON0 + 0.06, pdir.LAT0 + 0.02]
    assert pdir.maximo(r, caja) is None
    assert pdir.codificar(None) == 255 and pdir.decodificar(255) is None
    assert pdir.codificar(0) == 0 and abs(pdir.decodificar(pdir.codificar(25)) - 25) < 0.01
    assert pdir.codificar(10_000) == 254


def prueba_recorte_pequeno_con_dimensiones_propias():
    """El lector acepta otras dimensiones (rejillas de prueba pequeñas)."""
    import io
    a = array.array("h", range(20 * 30))
    f0, f1, c0, c1 = 2, 4, 5, 9
    caja = (pdir.LAT0 - 0.04 * f1, pdir.LAT0 - 0.04 * f0, pdir.LON0 + 0.04 * c0, pdir.LON0 + 0.04 * c1)
    if sys.byteorder != "little":
        a.byteswap()
    r = pdir.recortar(io.BytesIO(a.tobytes()), caja, columnas=30)
    assert (r["filas"], r["columnas"], r["fila0"], r["col0"]) == (3, 5, 2, 5)
    assert r["mmh"][0][0] == (2 * 30 + 5) / 100 and r["mmh"][2][4] == (4 * 30 + 9) / 100


def prueba_actualizar_guarda_horas_y_reintenta_con_calma(tmp_path):
    ahora = dt.datetime(2026, 11, 23, 5, 30, tzinfo=UTC)
    f, c = pdir.fila_de(-0.70), pdir.columna_de(-90.32)
    lleno = _archivo({(f, c): 500})
    pedidas = []

    def falso(hora):
        pedidas.append(hora.hour)
        return None if hora.hour in (4, 1) else lleno   # la de las 04 todavía no sale; la de la 01 falta

    r = pdir.actualizar(tmp_path, goes.zonas(), ahora, bajar_=falso)
    assert pedidas == [4, 3, 2, 1, 0, 23]
    assert r["faltan"] == ["2026-11-23T04:00:00Z", "2026-11-23T01:00:00Z"] and not r["errores"]
    d = json.loads((tmp_path / pdir.NOMBRE).read_text())
    assert [h["inicio"] for h in d["horas"]] == ["2026-11-22T23:00:00Z", "2026-11-23T00:00:00Z", "2026-11-23T02:00:00Z", "2026-11-23T03:00:00Z"]
    h = d["horas"][-1]
    assert h["fin"] == "2026-11-23T04:00:00Z" and h["zonas"]["la-cascada"]["max_mmh"] == 5.0
    plano = base64.b64decode(h["b64"])
    assert len(plano) == d["filas"] * d["columnas"] == 89 * 101
    i = round((d["norte"] - 0.02 - pdir.centro(f, c)[0]) / d["paso"])
    j = round((pdir.centro(f, c)[1] - d["oeste"] - 0.02) / d["paso"])
    assert abs(pdir.decodificar(plano[i * d["columnas"] + j]) - 5.0) < 0.25   # resolución del byte a 5 mm/h
    assert "garúa" in d["advertencia"] and "No entra" in d["advertencia"]
    # Diez minutos después: solo se vuelve a pedir la hora más reciente que falta (la 01 espera 30 min)
    pedidas.clear()
    pdir.actualizar(tmp_path, goes.zonas(), ahora + dt.timedelta(minutes=10), bajar_=falso)
    assert pedidas == [4]
    pedidas.clear()
    pdir.actualizar(tmp_path, goes.zonas(), ahora + dt.timedelta(minutes=31), bajar_=falso)
    assert pedidas == [4, 1]


def prueba_actualizar_aguanta_la_red_caida(tmp_path):
    def caida(hora):
        raise ConnectionError("sin red")

    r = pdir.actualizar(tmp_path, goes.zonas(), dt.datetime(2026, 11, 23, 5, 30, tzinfo=UTC), bajar_=caida)
    assert len(r["errores"]) == 6 and json.loads((tmp_path / pdir.NOMBRE).read_text())["horas"] == []


# ── GIBS ─────────────────────────────────────────────────────────────────────
def prueba_expandir_el_dominio_de_tiempo():
    desde, hasta = dt.datetime(2026, 11, 23, 2, 5, tzinfo=UTC), dt.datetime(2026, 11, 23, 3, 0, tzinfo=UTC)
    dom = "2026-11-22T23:00:00Z/2026-11-23T02:30:00Z/PT10M,2026-11-23T02:50:00Z/2026-11-23T04:30:00Z/PT10M"
    assert gibs.expandir(dom, desde, hasta) == ["2026-11-23T02:10:00Z", "2026-11-23T02:20:00Z", "2026-11-23T02:30:00Z",
                                                "2026-11-23T02:50:00Z", "2026-11-23T03:00:00Z"]
    assert gibs.expandir("2026-11-23T02:40:00Z", desde, hasta) == ["2026-11-23T02:40:00Z"]


@pytest.fixture
def gibs_limpio(monkeypatch):
    monkeypatch.setattr(gibs, "_cache", {"t": 0.0, "datos": None})
    monkeypatch.setenv("CLIMA_GIBS_WMTS", "https://wmts.ejemplo.test/raiz/")


def prueba_capas_da_las_ultimas_tres_horas(gibs_limpio):
    ahora = dt.datetime(2026, 11, 23, 5, 25, tzinfo=UTC)
    d = gibs.capas(ahora, pedir=lambda r, a, b: "2026-11-23T00:00:00Z/2026-11-23T04:30:00Z/PT10M")
    assert d["plantilla"] == "https://wmts.ejemplo.test/raiz/GOES-East_ABI_GeoColor/default/{t}/GoogleMapsCompatible_Level7/{z}/{y}/{x}.png"
    assert len(d["tiempos"]) == 18 and d["tiempos"][-1] == "2026-11-23T04:30:00Z" and d["zoom_max"] == 7
    assert "NASA GIBS" in d["atribucion"]


def prueba_capas_sin_gibs_no_falla(gibs_limpio, monkeypatch):
    def caido(r, a, b):
        raise TimeoutError

    assert gibs.capas(pedir=caido)["tiempos"] == []
    monkeypatch.delenv("CLIMA_GIBS_WMTS")
    assert gibs.capas()["plantilla"] is None


def prueba_api_satelite_capas(client, gibs_limpio, monkeypatch):
    monkeypatch.setattr(gibs, "dominio_remoto", lambda r, a, b: f"{gibs._iso(b - dt.timedelta(minutes=80))}/{gibs._iso(b)}/PT10M")
    r = client.get("/riesgos/api/clima/satelite-capas")
    assert r.status_code == 200 and "max-age" in r["Cache-Control"]
    d = r.json()
    assert d["capa"] == "GOES-East_ABI_GeoColor" and 8 <= len(d["tiempos"]) <= 9 and "{t}" in d["plantilla"]


def prueba_api_pdirnow(client, settings, tmp_path):
    settings.CLIMA_SALIDA = str(tmp_path)
    assert client.get("/riesgos/api/clima/pdirnow.json").status_code == 404   # todavía no se generó
    pdir.escribir(tmp_path, {"generado": "x", "horas": []})
    r = client.get("/riesgos/api/clima/pdirnow.json")
    assert r.status_code == 200 and json.loads(b"".join(r.streaming_content)) == {"generado": "x", "horas": []}

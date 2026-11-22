# SOS Galápagos · © 2026 Universidad San Francisco de Quito (USFQ) · Autor: Julián Maya <jamaya@usfq.edu.ec>
# Todos los derechos reservados. Usar, copiar, modificar o derivar de este código requiere permiso escrito del autor (ver LICENSE).
"""Pruebas de los lectores de El Niño (archivos del CPC, ERDDAP, MJO) y de la ZCIT del NHC. No usan red ni base de datos."""
import json
from pathlib import Path

from clima import nino, zcit

DATOS = Path(__file__).parent / "datos"

SEMANAL = """ Weekly SST data starts week centered on 2Sept1981

                Nino1+2      Nino3        Nino34        Nino4
 Week          SST SSTA     SST SSTA     SST SSTA     SST SSTA
 02SEP1981     20.6-0.1     24.8-0.1     26.5-0.2     28.3-0.3
 11NOV2026     27.1 5.4     29.4 4.3     29.9 3.2     29.9 1.3
"""
ONI = """   SEAS  YR   TOTAL   ANOM
   DJF 1950   24.72  -1.53
   ASO 2026   29.23   2.46
"""
MENSUAL = """YR MON  NINO1+2   ANOM   NINO3    ANOM   NINO4    ANOM NINO3.4    ANOM
2026  10   26.12    5.25   29.24    4.16   29.88    1.20   30.01    3.25
"""
ESTADO = "<p>12 November 2026</p> ENSO Alert System Status: El Ni&ntilde;o Advisory &nbsp; Synopsis: &nbsp; El Ni&ntilde;o continues, with a strong-to-very strong El Ni&ntilde;o likely"
ROMI = "2026 11 17  0     0.75582     1.10313     1.33722\n2026 11 18  0    -1.00000     0.10000     1.00500\n"
ERDDAP = """time,latitude,longitude,CRW_SSTANOMALY
UTC,degrees_north,degrees_east,Celsius
2026-11-21T12:00:00Z,0.5,-91.0,5.0
2026-11-21T12:00:00Z,0.5,-90.5,NaN
2026-11-21T12:00:00Z,0.0,-91.0,6.0
2026-11-21T12:00:00Z,0.0,-90.5,7.0
"""


def prueba_semanal_con_negativos_pegados():
    s = nino.leer_semanal(SEMANAL)
    assert s[0]["nino12"] == {"sst": 20.6, "anom": -0.1}
    assert s[-1]["semana"] == "2026-11-11"
    assert s[-1]["nino12"]["anom"] == 5.4 and s[-1]["nino34"]["anom"] == 3.2 and s[-1]["nino4"]["anom"] == 1.3


def prueba_oni_mensual_y_estado():
    o = nino.leer_oni(ONI)
    assert o[-1] == {"temporada": "ASO", "anio": 2026, "mes": "2026-09", "sst": 29.23, "anom": 2.46}
    assert nino.categoria(2.46) == "El Niño muy fuerte" and nino.categoria(0.2) == "Neutral"
    assert nino.leer_mensual(MENSUAL)[0]["nino34"]["anom"] == 3.25
    e = nino.leer_estado_cpc(ESTADO)
    assert e["estado"] == "Advertencia de El Niño" and e["fecha"] == "2026-11-12" and e["intensidad_esperada"] == "fuerte a muy fuerte"


def prueba_fase_mjo():
    m = nino.leer_mjo(ROMI)
    assert m[0]["fase"] == 4  # PC2 > 0 y −PC1 < 0: Indonesia
    assert m[1]["fase"] == 6  # PC2 ≈ 0 y −PC1 > 0: Pacífico oeste
    assert "débil" not in nino.frase_mjo(m[0])


def prueba_rejilla_y_media():
    r = nino._a_rejilla(nino._erddap_filas(ERDDAP), "CRW_SSTANOMALY", 10)
    assert (r["nlat"], r["nlon"], r["lat_n"], r["lon_o"]) == (2, 2, 0.5, -91.0)
    assert r["valores"] == [50, None, 60, 70]  # norte → sur, oeste → este; tierra = None
    assert nino.media_region(r, 1, -1, -92, -90) == 6.0


def prueba_zcit_noviembre():
    d = zcit.leer((DATOS / "twd_ep_2026-11-22.txt").read_text())
    assert d["emitido"] == "2026-11-22T22:05:00+00:00" and d["analisis"] == "2026-11-22T18:00:00+00:00"
    assert d["lineas"][0] == {"tipo": "vaguada_monzonica", "puntos": [[5.0, -77.5], [-1.0, -83.5], [2.0, -93.0]], "reanuda": False}
    assert [x["tipo"] for x in d["lineas"]] == ["vaguada_monzonica", "zcit", "zcit"]
    assert 0.9 <= d["galapagos"]["lat_zcit_90o"] <= 1.1 and d["galapagos"]["al"] == "encima"
    assert {"n": 0.0, "s": -3.4, "o": -120.0, "e": -116.0} in d["conveccion"]
    assert d["ondas"] == []
    assert "http" not in str(d)


def prueba_zcit_julio_con_ondas():
    d = zcit.leer((DATOS / "twd_ep_2026-07-14.txt").read_text())
    cerca = [o for o in d["ondas"] if o["cerca"]]
    assert len(d["ondas"]) == 3 and len(cerca) == 1
    assert cerca[0]["lon"] == -91.0 and cerca[0]["velocidad_kt"] == [15, 20] and cerca[0]["lat_s"] == 3.0
    assert len([x for x in d["lineas"] if x["tipo"] == "zcit"]) == 3
    assert d["galapagos"]["al"] == "norte"
    assert any("onda tropical en 91° O" in f for f in d["frases"])


def prueba_coordenadas():
    assert zcit.coordenadas("from EQ95W to 03.4S100W and 06.5N120.5W") == [[0.0, -95.0], [-3.4, -100.0], [6.5, -120.5]]


def prueba_la_api_sirve_los_archivos_de_el_nino(client, settings, tmp_path):
    settings.CLIMA_SALIDA = str(tmp_path)
    assert client.get("/riesgos/api/clima/nino.json").status_code == 404  # todavía no hay archivo
    zcit.exportar(tmp_path, texto=(DATOS / "twd_ep_2026-11-22.txt").read_text(), con_ia=False)
    (tmp_path / "nino.json").write_text('{"aviso": "contexto"}')
    leer = lambda r: json.loads(b"".join(r.streaming_content))  # noqa: E731  (FileResponse va por partes)
    assert leer(client.get("/riesgos/api/clima/nino.json")) == {"aviso": "contexto"}
    r = client.get("/riesgos/api/clima/zcit.json")
    assert r.status_code == 200 and leer(r)["galapagos"]["al"] == "encima"

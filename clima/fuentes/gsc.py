"""GSC · USFQ (San Cristóbal): cinco estaciones, cada 5 minutos.

Su página es una aplicación sin API: se abre una sesión por websocket, como un navegador, y
se leen los gráficos de «últimas 24 horas, cada 5 minutos» de cada variable.

Sus horas llevan una «Z» que no es cierta: son hora continental (UTC−5). Verificado.
"""
import asyncio
import datetime as dt
import json
import time
from urllib.parse import urlparse

from . import base

FUENTE = "gsc"
VARIABLES = {"Rain_Tot": "lluvia_mm", "Air_Temp": "temp_c", "SR": "rad_wm2", "RH": "hr_pct"}
ESTACIONES = {  # código: (nombre, lat, lon, altitud), del mapa de su página
    # También son estaciones del INAMHI: se muestran los dos nombres (el del GSC y el nombre y código del INAMHI).
    "merceditas": ("Merceditas · USFQ - SAN CRISTOBAL EN LAS MERCEDITAS (M5300)", -0.889712, -89.442020, 100),
    "junco": ("El Junco · USFQ - SAN CRISTOBAL EN EL JUNCO (M5301)", -0.896537, -89.481624, 548),
    "cerro_alto": ("Cerro Alto · USFQ - SAN CRISTOBAL EN CERRO ALTO (M5302)", -0.887049, -89.530986, 517),
    "mirador": ("El Mirador · USFQ - SAN CRISTOBAL EN EL MIRADOR (M5303)", -0.886248, -89.539587, 387),
    "gsc": ("GSC (Puerto Baquerizo Moreno)", -0.895653, -89.608702, 20),
}


def codigo(nombre):
    return nombre.lower().replace(" ", "_").replace("el_", "")


def _hora(texto):
    return dt.datetime.fromisoformat(texto[:19]).replace(tzinfo=base.CONTINENTE)


def _inicio(extra=None):
    anfitrion = urlparse(base.endpoint("CLIMA_GSC_ORIGEN")).hostname
    d = {"variable_selection_xh": "Rain_Tot", "Variable_selection_xd": "Rain_Tot", "var_hist": "Precip",
         "time_hist": "diario", "ldas_var": "streamflow", "tabset1": "tab-4532-2",
         ".clientdata_pixelratio": 1, ".clientdata_url_protocol": "https:",
         ".clientdata_url_hostname": anfitrion, ".clientdata_url_port": "",
         ".clientdata_url_pathname": "/", ".clientdata_url_search": "", ".clientdata_url_hash_initial": "",
         ".clientdata_url_hash": "", ".clientdata_singletons": "", ".clientdata_allowDataUriScheme": True}
    for salida in ("Time_series_xh", "Time_series_xd", "ts_hist", "mymap"):
        d[f".clientdata_output_{salida}_width"] = 1000
        d[f".clientdata_output_{salida}_height"] = 400
        d[f".clientdata_output_{salida}_hidden"] = salida != "Time_series_xh"
    d.update(extra or {})
    return d


async def _sesion(pasos, espera=45):
    """pasos: [(datos a enviar, salida que se espera)]. Devuelve el valor de esa salida en cada paso."""
    import websockets

    resultados = []
    async with websockets.connect(base.endpoint("CLIMA_GSC_WS"), origin=base.endpoint("CLIMA_GSC_ORIGEN"), max_size=2**28,
                                  open_timeout=30, user_agent_header=base.AGENTE) as ws:
        for i, (datos, salida) in enumerate(pasos):
            await ws.send(json.dumps({"method": "init" if i == 0 else "update", "data": datos}))
            fin = time.time() + espera
            while True:
                mensaje = json.loads(await asyncio.wait_for(ws.recv(), timeout=max(1, fin - time.time())))
                if salida in (mensaje.get("values") or {}):
                    resultados.append(mensaje["values"][salida])
                    break
    return resultados


def series(grafico):
    """(código de estación, horas, valores) de cada trazo de un gráfico."""
    for d in grafico["x"]["data"]:
        for trazo in d.get("data", []):
            if trazo.get("x"):
                yield codigo(trazo.get("name", "")), trazo["x"], trazo["y"]


def filas_de(graficos):
    """De los gráficos (uno por variable, en el orden de VARIABLES) a filas para guardar."""
    filas = []
    for variable, grafico in zip(VARIABLES, graficos):
        for est, xs, ys in series(grafico):
            filas += [(est, VARIABLES[variable], _hora(x), y) for x, y in zip(xs, ys) if y is not None]
    return filas


def recoger():
    for cod, (nombre, lat, lon, altitud) in ESTACIONES.items():
        base.estacion(FUENTE, cod, nombre, "San Cristóbal", lat, lon, altitud, "GSC-USFQ")
    variables = list(VARIABLES)
    pasos = [(_inicio({"variable_selection_xh": variables[0]}), "Time_series_xh")]
    pasos += [({"variable_selection_xh": v}, "Time_series_xh") for v in variables[1:]]
    return base.guardar(FUENTE, filas_de(asyncio.run(_sesion(pasos))))


def importar_historico():
    """Lluvia diaria desde 2015 (su pestaña de registros históricos)."""
    pasos = [(_inicio({"tabset1": "tab-4532-3", "filter_hist": ["2015-01-01", dt.date.today().isoformat()],
                       ".clientdata_output_ts_hist_hidden": False, ".clientdata_output_Time_series_xh_hidden": True}), "ts_hist")]
    grafico = asyncio.run(_sesion(pasos, espera=120))[0]
    filas = []
    for est, xs, ys in series(grafico):
        filas += [(est, "lluvia_dia_mm", dt.datetime.fromisoformat(x[:10]).replace(tzinfo=base.CONTINENTE), y) for x, y in zip(xs, ys) if y is not None]
    return base.guardar(FUENTE, filas)

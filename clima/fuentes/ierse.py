# SOS Galápagos · © 2026 Universidad San Francisco de Quito (USFQ) · Autor: Julián Maya <jamaya@usfq.edu.ec>
# Todos los derechos reservados. Usar, copiar, modificar o derivar de este código requiere permiso escrito del autor (ver LICENSE).
"""IERSE-WSN (Universidad del Azuay): cuatro estaciones en Santa Cruz, cada 5 minutos.

El servidor de IERSE solo responde a conexiones desde Ecuador, y el de sosgalapagos.org está
fuera. Por eso esta fuente tiene dos caminos, con la misma lógica:

- **Relevo** (el normal): una máquina en Ecuador corre `despliegue/relevo/relevo.py`, que no
  sabe nada de IERSE. Pregunta aquí qué pedir (`pedidos()`), lo pide y devuelve las respuestas
  tal cual (`procesar()`). Toda la interpretación está en este archivo.
- **Directo** (`CLIMA_IERSE_DIRECTO=1`): si algún día IERSE autoriza la dirección del servidor,
  o la plataforma corre en Ecuador, `recoger()` hace los mismos pedidos por su cuenta.

Licencia de los datos: CC BY-NC-ND 4.0, con cita obligatoria (ver LICENCIA-DATOS.md).
Las horas de IERSE son de Galápagos (UTC−6).
"""
import datetime as dt
import re

from . import base

FUENTE = "ierse"
RED = "ntw003_glps"
VARIABLES = {"RAIN": ("lluvia_mm", 1.0), "Temperature": ("temp_c", 1.0), "Humidity": ("hr_pct", 1.0), "Pressure": ("presion_hpa", 0.01)}
ALTITUD = {"n_glps01": 861, "n_glps05": 178, "n_glps06": 14, "n_glps09": 416}  # DEM Copernicus 30 m
DIAS_ATRAS = 10      # tras un corte del relevo se recupera hasta aquí
DIAS_POR_RONDA = 3   # y de a pocos días por ronda, para que ninguna tarde demasiado
_CODIGO = re.compile(r"^[A-Za-z0-9_.-]{1,40}$")


def _hora(texto):  # '2026-10-31T00:02:11.000', hora de Galápagos (verificado contra la hora actual)
    return dt.datetime.fromisoformat(texto[:19]).replace(tzinfo=base.GALAPAGOS)


def _nodos_conocidos():
    from ..models import Estacion

    return list(Estacion.objects.filter(fuente=FUENTE).values_list("codigo", flat=True))


def _dias(ahora):
    """(días que toca pedir en esta ronda, ¿quedan más?). Desde el día del último dato guardado."""
    hoy = ahora.astimezone(base.GALAPAGOS)
    desde = hoy.date() - dt.timedelta(days=DIAS_ATRAS)
    ultimo = base.ultimo(FUENTE)
    if ultimo:
        desde = max(desde, ultimo.astimezone(base.GALAPAGOS).date())
    # Si la ronda anterior (hace poco) ya repasó días sin datos, no se vuelven a pedir.
    from ..models import Estado

    avance = Estado.objects.filter(clave="ierse_avance", generado__gte=ahora - dt.timedelta(minutes=30)).first()
    if avance:
        desde = max(desde, dt.date.fromisoformat(avance.datos["dia"]))
    if hoy.hour < 2:  # pasada la medianoche se repasa el día anterior
        desde = min(desde, hoy.date() - dt.timedelta(days=1))
    desde = min(desde, hoy.date())
    todos = [desde + dt.timedelta(days=i) for i in range((hoy.date() - desde).days + 1)]
    return todos[:DIAS_POR_RONDA], len(todos) > DIAS_POR_RONDA


def pedidos(ahora=None):
    """Lo que hay que pedirle a IERSE ahora: [{id, url, cuerpo}]. Y si después de esto queda más por pedir."""
    ahora = ahora or dt.datetime.now(base.UTC)
    api = base.endpoint("CLIMA_IERSE_API")
    lista = [{"id": "nodos", "url": api + "/oper_nodes", "cuerpo": {"req_netw": RED}}]
    dias, quedan = _dias(ahora)
    for dia in dias:
        for variable in VARIABLES:
            for nodo in _nodos_conocidos():
                lista.append({"id": f"datos|{nodo}|{variable}|{dia.isoformat()}", "url": api + "/node_data",
                              "cuerpo": {"req_var": variable, "req_date": dia.isoformat(), "req_node": nodo, "req_netw": RED, "pub_query": "1"}})
    return lista, quedan or len(lista) == 1  # sin nodos conocidos aún: la siguiente ronda ya los tendrá


def procesar(respuestas):
    """respuestas: {id del pedido: lo que respondió IERSE}. Guarda estaciones y mediciones. Devuelve cuántas.

    Lo que llega se valida entero: viene de fuera (del relevo) y termina publicado.
    """
    for n in respuestas.get("nodos") or []:
        if not (isinstance(n, dict) and isinstance(n.get("node_id"), str) and _CODIGO.match(n["node_id"])):
            continue
        nombre = str(n.get("node_name") or n["node_id"])[:120]
        if any(c in nombre for c in "<>`"):
            nombre = n["node_id"]
        lat, lon = n.get("node_lat"), n.get("node_long")
        if not all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in (lat, lon)):
            lat = lon = None
        base.estacion(FUENTE, n["node_id"], nombre, "Santa Cruz", lat, lon, ALTITUD.get(n["node_id"]), "IERSE-WSN")
    conocidos, filas = set(_nodos_conocidos()), []
    ahora = dt.datetime.now(base.UTC)
    for clave, serie in respuestas.items():
        partes = clave.split("|")
        if len(partes) != 4 or partes[0] != "datos" or partes[1] not in conocidos or partes[2] not in VARIABLES or not isinstance(serie, list):
            continue
        nombre, factor = VARIABLES[partes[2]]
        for punto in serie[:2000]:
            try:
                ts, valor = _hora(punto["timestamp"]), punto["sensor_value"]
            except (KeyError, TypeError, ValueError):
                continue
            if valor is not None and (isinstance(valor, bool) or not isinstance(valor, (int, float))):
                continue
            if not ahora - dt.timedelta(days=DIAS_ATRAS + 2) <= ts <= ahora + dt.timedelta(hours=1):
                continue
            filas.append((partes[1], nombre, ts, None if valor is None else valor * factor))
    dias = [c.split("|")[3] for c in respuestas if c.count("|") == 3]
    if dias:
        from ..models import Estado

        Estado.objects.update_or_create(clave="ierse_avance", defaults={"datos": {"dia": max(dias)[:10]}, "generado": ahora})
    return base.guardar(FUENTE, filas)


def desde_del_resumen(respuestas):
    """Desde qué hora hay que rehacer los resúmenes por hora tras procesar estas respuestas."""
    dias = [c.split("|")[3][:10] for c in respuestas if c.count("|") == 3]
    primero = dt.date.fromisoformat(min(dias)) if dias else dt.datetime.now(base.GALAPAGOS).date()
    return dt.datetime.combine(primero, dt.time(), base.GALAPAGOS).astimezone(base.UTC)


def recoger():
    """Camino directo: solo sirve donde IERSE responde (Ecuador)."""
    total = 0
    for _ in range(6):
        lista, quedan = pedidos()
        total += procesar({p["id"]: base.http_json(p["url"], p["cuerpo"]) for p in lista})
        if not quedan:
            break
    return total


def importar(carpeta):
    """Carga el histórico guardado en CSV (clima/datos/ierse-wsn/crudos del repositorio de datos)."""
    import csv
    import gzip
    from pathlib import Path

    total = 0
    for archivo in sorted(Path(carpeta).glob("*/*.csv.gz")):
        with gzip.open(archivo, "rt") as f:
            filas = [(r["estacion_id"], VARIABLES[r["variable"]][0], _hora(r["fecha_hora_local"]),
                      float(r["valor"]) * VARIABLES[r["variable"]][1] if r["valor"] else None)
                     for r in csv.DictReader(f) if r["variable"] in VARIABLES]
        total += base.guardar(FUENTE, filas)
    return total

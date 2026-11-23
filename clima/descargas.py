# SOS Galápagos · © 2026 Universidad San Francisco de Quito (USFQ) · Autor: Julián Maya <jamaya@usfq.edu.ec>
# Licencia Apache 2.0 (ver LICENSE y NOTICE): puede reutilizarse dando crédito.
"""Descargas de datos del clima: un ZIP por mes con las mediciones crudas de las estaciones,
y cada noche un ZIP con todo (clima_galapagos_todo.zip): todas las mediciones y las
estimaciones propias (nivel por zona, pronóstico publicado, modelos, satélite y mar modelado).

Van a CLIMA_SALIDA/descargas, que el servidor publica en /clima/datos/descargas/. Los ZIP del
mes se rehacen cada hora; los meses cerrados no se vuelven a escribir.

Se publican con permiso de cada operador (IERSE, GSC-USFQ, Fundación Charles Darwin e INAMHI:
confirmado por Julián Maya el 22-nov-2026). Cada fuente conserva SU licencia, que va escrita en
el LEEME.txt de la carpeta. No entran aquí los modelos ni el satélite: son estimaciones propias.
"""
import csv
import datetime as dt
import io
import json
import os
import zipfile
from pathlib import Path

from django.conf import settings
from django.db import connection

from . import danadas
from .fuentes import DE_ESTACION

UTC = dt.timezone.utc

LEEME = """Datos meteorológicos de Galápagos reunidos por SOS Galápagos
Actualizado: {generado} (los ZIP del mes, cada hora; clima_galapagos_todo.zip, cada noche)
https://sosgalapagos.org/clima/

DATOS CRUDOS: cada valor está tal como llegó de su fuente, sin control de calidad ni
correcciones. La regla de nivel de lluvia de la página filtra estaciones; estos archivos no.
{danadas}
LICENCIAS Y CÓMO CITAR
Cada fuente es de su operador y conserva su licencia. SOS Galápagos las publica con permiso
de cada uno. Al usarlas, cite al operador y respete su licencia:

- IERSE-WSN (Santa Cruz). Licencia CC BY-NC-ND 4.0 (atribución, no comercial, sin obras
  derivadas): Orellana-Samaniego, M.L., Cabrera-Lituma, A., Omar, D., Célleri, R., Bendix, J.,
  y Ballari, D. 2023. Proyecto DARWIN. Versión 2023.1. IERSE, Universidad del Azuay.
  <http://opengeodata.uazuay.edu.ec/EstudioDarwin/>, fecha de acceso.
- GSC-USFQ (San Cristóbal). Publicado con permiso del Galapagos Science Center, que no declara
  una licencia abierta: para reutilizarlos, pídale permiso. Cita: Universidad San Francisco de
  Quito; Galapagos Science Center. (2026). Weather Data - GSC. Recuperado el <fecha> de
  https://weathergsc.usfq.edu.ec/
- Fundación Charles Darwin (series diarias históricas de Puerto Ayora y Bellavista, en
  historico_lluvia_diaria.csv). Licencia CC BY-NC-SA (atribución, no comercial, compartir
  igual). Publicado con su permiso; cite a la Fundación Charles Darwin.
- INAMHI (Instituto Nacional de Meteorología e Hidrología del Ecuador). Publicado con su
  permiso; cite al INAMHI. No declara una licencia abierta para estos datos.
- IOC (mareógrafos, Sea Level Station Monitoring Facility, UNESCO/IOC) y METAR de los
  aeropuertos: datos públicos; cite al operador.
- Estaciones particulares (WeatherLink, Tempest, Ambient Weather, Weather Underground): datos
  de sus dueños, publicados con su permiso; cite la estación y la plataforma.

La recopilación (estos archivos, tal como están armados) es de SOS Galápagos · Universidad San
Francisco de Quito (USFQ), autor Julián Maya <jamaya@usfq.edu.ec>, y se distribuye bajo
CC BY 4.0: se puede copiar, adaptar y usar, también con fines comerciales, dando crédito así:
«SOS Galápagos · Universidad San Francisco de Quito (USFQ) · Julián Maya
<jamaya@usfq.edu.ec>. Licencia CC BY 4.0». Donde la licencia de una fuente sea más
restrictiva, manda la de la fuente.

- Estimaciones propias de SOS Galápagos (solo en clima_galapagos_todo.zip): nivel de lluvia
  peligrosa por zona, probabilidad publicada, lluvia de los modelos (Open-Meteo, CC BY 4.0),
  señal del satélite GOES-19 (NOAA, dominio público) y mar modelado. NO son datos oficiales:
  son modelos propios o de terceros, sin calibrar del todo. Lo oficial es del INAMHI, el
  INOCAR, la SNGR y el ECU 911. No se incluyen el oleaje de Stormglass (su licencia no permite
  redistribuirlo) ni la tabla de mareas del INOCAR (consúltela en su página).

ARCHIVOS
clima_galapagos_todo.zip         TODO en un archivo, se rehace cada noche (~02:00 de Galápagos):
    LEEME.txt, estaciones.csv, historico_lluvia_diaria.csv
    mediciones/clima_galapagos_AAAA-MM.csv   lo mismo que los ZIP del mes (ver abajo)
    estimaciones/nivel_zona.csv              nivel calculado cada 5 min: zona, calculado_utc,
                                             nivel, instantaneo, silencio, R1h, R3h, R24h, R72h (mm)
    estimaciones/nivel_manual.csv            niveles subidos a mano por reportes de campo
    estimaciones/pronostico_publicado.csv    probabilidad de superar 10, 20 y 50 mm en el día
    estimaciones/pronostico_modelos.csv      lluvia del día que dio cada modelo (mm de modelo)
    estimaciones/satelite_goes.csv           agregados por zona del GOES-19 (topes fríos, RRQPE, rayos)
    estimaciones/mar_modelo.csv              nivel del mar y oleaje modelados (Open-Meteo Marine)
clima_galapagos_AAAA-MM.zip      todas las mediciones de estaciones del mes (un CSV dentro)
    ts_utc     hora en UTC (Galápagos = UTC-6)
    fuente     ierse | gsc | inamhi | ioc | metar | weatherlink | tempest | ambient | wunderground
    estacion   identificador (ver estaciones.csv)
    variable   lluvia_mm (lluvia del intervalo de ~5 min que empieza o termina en ts; 1 h en
               las filas con segundos :30: respaldo por hora del INAMHI y de Erna),
               lluvia_dia_acum_mm (acumulado del día que da la estación), temp_c, hr_pct,
               presion_hpa, rad_wm2, viento_ms, nivel_mar_m, lluvia_codigo (METAR: 0 nada,
               1 débil, 2 moderada, 3 fuerte o tormenta)
    valor      tal como llega de la fuente
historico_lluvia_diaria.csv      lluvia diaria: GSC desde 2015 y FCD desde 1965 (fecha local)
estaciones.csv                   nombre, isla, coordenadas, altitud y operador
indice.json                      lista de archivos con tamaño y fecha

Cuidado: durante los cortes de transmisión la lluvia no se mide (no queda en cero ni se
acumula después). Mire la cobertura antes de sumar.
"""


def _z(t):
    return t.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _mes_siguiente(mes):
    return (mes.replace(day=28) + dt.timedelta(days=4)).replace(day=1)


def _escribir_mes(ruta, mes, fuentes):
    """Un ZIP con un CSV dentro: se abre con doble clic en Windows, macOS y Linux."""
    inicio = dt.datetime(mes.year, mes.month, 1, tzinfo=UTC)
    fin = dt.datetime.combine(_mes_siguiente(mes), dt.time(), UTC)
    tmp = ruta.with_name(f".{ruta.name}.{os.getpid()}.tmp")
    with zipfile.ZipFile(tmp, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as z, \
            z.open(f"{ruta.stem}.csv", "w") as crudo, io.TextIOWrapper(crudo, encoding="utf-8", newline="") as f, \
            connection.cursor() as c:
        w = csv.writer(f)
        w.writerow(["ts_utc", "fuente", "estacion", "variable", "valor"])
        c.execute("""SELECT to_char(o.ts AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS"Z"'), e.fuente, e.codigo, o.variable, o.valor
                     FROM clima_observacion o JOIN clima_estacion e ON e.id = o.estacion_id
                     WHERE o.ts >= %s AND o.ts < %s AND e.fuente = ANY(%s) AND o.variable <> 'lluvia_dia_mm'
                     ORDER BY o.ts, e.fuente, e.codigo, o.variable""", [inicio, fin, list(fuentes)])
        while filas := c.fetchmany(20000):
            w.writerows(filas)
    os.chmod(tmp, 0o644)
    os.replace(tmp, ruta)


def _texto(ruta, contenido):
    ruta.write_text(contenido)
    os.chmod(ruta, 0o644)


def _csv(z, nombre, encabezado, sql, params=()):
    """Una consulta a un CSV dentro del ZIP, por partes para no cargarla entera en memoria."""
    with z.open(nombre, "w") as crudo, io.TextIOWrapper(crudo, encoding="utf-8", newline="") as f, connection.cursor() as c:
        w = csv.writer(f)
        w.writerow(encabezado)
        c.execute(sql, params)
        while filas := c.fetchmany(20000):
            w.writerows(filas)


def _indice(destino):
    archivos = sorted(p for p in destino.iterdir() if p.is_file() and not p.name.startswith(".") and p.suffix in (".zip", ".csv", ".txt"))
    _texto(destino / "indice.json", json.dumps({"generado": _z(dt.datetime.now(UTC)), "archivos": [
        {"archivo": p.name, "bytes": p.stat().st_size, "actualizado": _z(dt.datetime.fromtimestamp(p.stat().st_mtime, UTC))} for p in archivos]},
        ensure_ascii=False, separators=(",", ":")))


TS = """to_char({} AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS"Z"')"""


def publicar_todo(carpeta=None):
    """Cada noche: clima_galapagos_todo.zip con todas las mediciones y las estimaciones propias.

    Primero rehace las descargas del mes (así el LEEME y las listas van al día) y después junta
    todo en un ZIP. Se escribe aparte y se cambia de un golpe: nadie baja un archivo a medias.
    """
    from .models import MarHora, NivelManual, NivelZona, PronosticoEmitido, PronosticoModelo

    publicar(carpeta)
    destino = Path(carpeta or settings.CLIMA_SALIDA) / "descargas"
    ruta = destino / "clima_galapagos_todo.zip"
    tmp = ruta.with_name(f".{ruta.name}.{os.getpid()}.tmp")
    with connection.cursor() as c:
        c.execute("""SELECT DISTINCT date_trunc('month', h.hora AT TIME ZONE 'UTC')::date FROM clima_horaria h
                     JOIN clima_estacion e ON e.id = h.estacion_id WHERE e.fuente = ANY(%s)""", [list(DE_ESTACION)])
        meses = sorted(m for (m,) in c.fetchall())
    t = lambda m: m._meta.db_table  # noqa: E731
    with zipfile.ZipFile(tmp, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        for nombre in ("LEEME.txt", "estaciones.csv", "historico_lluvia_diaria.csv"):
            z.write(destino / nombre, nombre)
        for mes in meses:
            inicio = dt.datetime(mes.year, mes.month, 1, tzinfo=UTC)
            fin = dt.datetime.combine(_mes_siguiente(mes), dt.time(), UTC)
            _csv(z, f"mediciones/clima_galapagos_{mes:%Y-%m}.csv", ["ts_utc", "fuente", "estacion", "variable", "valor"],
                 f"""SELECT {TS.format("o.ts")}, e.fuente, e.codigo, o.variable, o.valor FROM clima_observacion o JOIN clima_estacion e ON e.id = o.estacion_id
                     WHERE o.ts >= %s AND o.ts < %s AND e.fuente = ANY(%s) AND o.variable <> 'lluvia_dia_mm'
                     ORDER BY o.ts, e.fuente, e.codigo, o.variable""", [inicio, fin, list(DE_ESTACION)])
        _csv(z, "estimaciones/nivel_zona.csv", ["zona", "calculado_utc", "nivel", "instantaneo", "silencio", "R1h", "R3h", "R24h", "R72h"],
             f"""SELECT zona, {TS.format("calculado")}, nivel, instantaneo, silencio, lluvia->>'R1h', lluvia->>'R3h', lluvia->>'R24h', lluvia->>'R72h'
                 FROM {t(NivelZona)} ORDER BY calculado, zona""")
        _csv(z, "estimaciones/nivel_manual.csv", ["zona", "nivel", "desde_utc", "hasta_utc"],
             f"SELECT zona, nivel, {TS.format('desde')}, {TS.format('hasta')} FROM {t(NivelManual)} ORDER BY desde")
        _csv(z, "estimaciones/pronostico_publicado.csv", ["punto", "emitido_utc", "fecha", "anticipacion_dias", "prob10", "prob20", "prob50", "consenso", "n_modelos", "mediana_mm", "nivel", "calibrado"],
             f"""SELECT punto, {TS.format("emitido")}, fecha, anticipacion, prob10, prob20, prob50, consenso, n_modelos, mediana_mm, nivel, calibrado
                 FROM {t(PronosticoEmitido)} ORDER BY emitido, punto, fecha""")
        _csv(z, "estimaciones/pronostico_modelos.csv", ["punto", "modelo", "obtenido_utc", "fecha", "anticipacion_dias", "mm", "miembros"],
             f"""SELECT punto, modelo, {TS.format("obtenido")}, fecha, anticipacion, mm, miembros
                 FROM {t(PronosticoModelo)} ORDER BY obtenido, punto, modelo, fecha""")
        _csv(z, "estimaciones/satelite_goes.csv", ["ts_utc", "zona", "variable", "valor"],
             f"""SELECT {TS.format("o.ts")}, e.codigo, o.variable, o.valor FROM clima_observacion o JOIN clima_estacion e ON e.id = o.estacion_id
                 WHERE e.fuente = 'goes' ORDER BY o.ts, e.codigo, o.variable""")
        _csv(z, "estimaciones/mar_modelo.csv", ["puerto", "hora_utc", "nivel_m", "ola_m", "fondo_m", "periodo_s", "direccion", "viento_ms", "agua_c"],
             f"""SELECT puerto, {TS.format("hora")}, nivel_m, ola_m, fondo_m, periodo_s, direccion, viento_ms, agua_c
                 FROM {t(MarHora)} WHERE fuente = 'openmeteo' ORDER BY hora, puerto""")
    os.chmod(tmp, 0o644)
    os.replace(tmp, ruta)
    _indice(destino)
    return ruta.stat().st_size


def publicar(carpeta=None, meses_abiertos=2, hoy=None):
    """Rehace las descargas. Devuelve cuántos ZIP hay."""
    destino = Path(carpeta or settings.CLIMA_SALIDA) / "descargas"
    destino.mkdir(parents=True, exist_ok=True)
    hoy = hoy or dt.datetime.now(UTC).date()
    abierto_desde = (hoy.replace(day=1) - dt.timedelta(days=31 * meses_abiertos)).strftime("%Y-%m")
    with connection.cursor() as c:
        c.execute("""SELECT DISTINCT date_trunc('month', h.hora AT TIME ZONE 'UTC')::date FROM clima_horaria h
                     JOIN clima_estacion e ON e.id = h.estacion_id WHERE e.fuente = ANY(%s)""", [list(DE_ESTACION)])
        meses = sorted(m for (m,) in c.fetchall())
    for mes in meses:
        ruta = destino / f"clima_galapagos_{mes:%Y-%m}.zip"
        if ruta.exists() and f"{mes:%Y-%m}" < abierto_desde:
            continue  # mes cerrado: ya está escrito
        _escribir_mes(ruta, mes, DE_ESTACION)

    with open(destino / "historico_lluvia_diaria.csv", "w", newline="") as f, connection.cursor() as c:
        w = csv.writer(f)
        w.writerow(["fecha_local", "fuente", "estacion", "lluvia_mm"])
        c.execute("""SELECT (o.ts - interval '5 hours')::date, e.fuente, e.codigo, o.valor FROM clima_observacion o
                     JOIN clima_estacion e ON e.id = o.estacion_id WHERE o.variable = 'lluvia_dia_mm' ORDER BY 1, 2, 3""")
        w.writerows(c.fetchall())
    with open(destino / "estaciones.csv", "w", newline="") as f, connection.cursor() as c:
        w = csv.writer(f)
        w.writerow(["fuente", "estacion", "nombre", "isla", "lat", "lon", "altitud_m", "operador"])
        c.execute("""SELECT fuente, codigo, nombre, isla, ST_Y(punto), ST_X(punto), altitud_m, operador FROM clima_estacion
                     WHERE fuente = ANY(%s) ORDER BY 1, 2""", [list(DE_ESTACION) + ["fcd"]])
        w.writerows(c.fetchall())

    marcadas = [f"- {k}: {x.get('motivo') or 'dañada'} (desde {x['desde']}; variables: {', '.join(x['variables'])})." for k, x in danadas.vigentes().items()]
    aviso = ("\nESTACIONES MARCADAS CON ERRORES (sus datos siguen aquí, pero la página no los usa):\n" + "\n".join(marcadas) + "\n") if marcadas else ""
    _texto(destino / "LEEME.txt", LEEME.format(generado=_z(dt.datetime.now(UTC)), danadas=aviso))
    _indice(destino)
    return len(list(destino.glob("clima_galapagos_????-??.zip")))

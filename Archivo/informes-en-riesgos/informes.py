"""Informes y mapas en PDF que ya publica la portada del sitio (sosgalapagos.org/#informes).

Los publica el repo sosgalapagos-datos (`servidores/publicar.sh descargas`) en
/srv/sosgalapagos-descargas, que Caddy sirve en /descargas/. El índice (`indice.json`) no
se publica por la web: se lee del disco, con la carpeta montada en solo lectura.
Si la carpeta o el índice no existen (como en la Mac), no se muestra la sección.

Aquí solo se enlaza lo que ya está publicado. Qué informe se publica lo decide Julián,
uno por uno, en el repo de datos.
"""
import json
import re
from pathlib import Path

from django.conf import settings

ARCHIVO = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*\.pdf$")
PORTADA = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*\.(jpg|png)$")
FECHA = re.compile(r"^\d{4}-\d{2}-\d{2}$")
MAXIMO = 30


def _texto(valor, largo):
    return valor.strip()[:largo] if isinstance(valor, str) else ""


def validar(dato):
    """Deja solo las entradas bien formadas, con nombres de archivo simples. Las más recientes, primero."""
    lista = dato.get("informes") if isinstance(dato, dict) else None
    if not isinstance(lista, list):
        return []
    informes = []
    for x in lista:
        if not isinstance(x, dict):
            continue
        archivo, titulo, fecha = _texto(x.get("archivo"), 120), _texto(x.get("titulo"), 140), _texto(x.get("fecha"), 10)
        if not ARCHIVO.match(archivo) or not titulo or not FECHA.match(fecha):
            continue
        portada = _texto(x.get("portada"), 120)
        paginas = x.get("paginas")
        informes.append(
            {
                "archivo": archivo,
                "titulo": titulo,
                "fecha": fecha,
                "resumen": _texto(x.get("resumen"), 400),
                "portada": portada if PORTADA.match(portada) else "",
                "paginas": round(paginas) if isinstance(paginas, (int, float)) and paginas > 0 else None,
                "formato": _texto(x.get("formato"), 30),
                "tamano": _texto(x.get("tamano"), 20),
            }
        )
    informes.sort(key=lambda i: i["fecha"], reverse=True)  # estable: a igual fecha, el orden del índice
    return informes[:MAXIMO]


def leer():
    try:
        return validar(json.loads((Path(settings.INFORMES_DIR) / "indice.json").read_text()))
    except (OSError, ValueError):
        return []

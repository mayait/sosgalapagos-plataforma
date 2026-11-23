# SOS Galápagos · © 2026 Universidad San Francisco de Quito (USFQ) · Autor: Julián Maya <jamaya@usfq.edu.ec>
# Licencia Apache 2.0 (ver LICENSE y NOTICE): puede reutilizarse dando crédito.
"""Compara lo que publica /mapas con lo que el mapa sabe dibujar.

Otro equipo cambia las capas y el manifiesto varias veces al día. Esta orden baja el
capas.json publicado y avisa de lo que el mapa todavía no entiende: un tipo de capa nuevo
o una clave de estilo nueva. Si todo es conocido, no hay nada que hacer en el código.

Uso: manage.py revisar_capas            (sale con error si encuentra algo desconocido)
"""
import json
from urllib.request import Request, urlopen

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

# Lo que estaticos/mapa/capas.js sabe leer. Al enseñarle algo nuevo, se añade aquí.
TIPOS = {"poligono", "linea", "punto", "raster", "teselas"}
MARCADORES = {"reporte", "corazon"}  # formas de marcador que el mapa sabe dibujar
CLAVES = {
    "capa": {"id", "titulo", "tipo", "archivo", "visible", "visible_movil", "fuente", "descripcion", "elementos", "estilo",
             "clasificar", "estilo_si", "filtro", "patron", "borde", "rotulo", "popup", "leyenda", "zoom_min", "opacidad",
             "raster", "teselas", "solo_rotulo", "marcador", "fotos_base", "extrusion",
             # se aceptan y no cambian el dibujo: «pane» (el apilado va por tipo) y «corto» (nombre breve del buscador)
             "pane", "corto"},
    "estilo": {"color", "weight", "opacity", "fill", "fillColor", "fillOpacity", "dashArray", "radius"},
    "clasificar": {"propiedad", "valores", "rangos", "otro"},
    "clase": {"etiqueta", "simbolo", "hasta", "color", "weight", "opacity", "fillColor", "fillOpacity", "dashArray"},
    "rotulo": {"propiedad", "permanente", "zoom_min", "sufijo"},
    "popup": {"titulo", "titulo_defecto", "sufijo_titulo", "campos", "texto", "fotos"},
    "borde": {"color", "weight", "opacity", "fill"},
    "patron": {"id", "color", "separacion", "grosor", "fondo", "opacidad", "opacidad_fondo"},
    "filtro": {"propiedad", "en"},
    "extrusion": {"altura", "auto_3d"},  # volumen en la vista 3D: propiedad con la altura (m) y si se enciende sola
    "grupo": {"id", "titulo", "capas", "descripcion", "enlace"},
}


class Command(BaseCommand):
    help = "Avisa si /mapas publica algo que el mapa todavía no sabe dibujar"

    def handle(self, **opciones):
        def bajar(nombre):
            pedido = Request(settings.CAPAS_ORIGEN + nombre, headers={"User-Agent": "sosgalapagos-plataforma"})
            with urlopen(pedido, timeout=30) as r:
                return r.read().decode()

        manifiesto = json.loads(bajar("capas.json"))
        try:
            version = bajar("version.txt").strip()
        except Exception:
            version = "sin version.txt"
        nuevo = []

        def revisar(que, donde, datos):
            for clave in set(datos or {}) - CLAVES[que]:
                nuevo.append(f"{donde}: clave «{clave}» en {que}")

        capas = 0
        for grupo in manifiesto["grupos"]:
            revisar("grupo", grupo["id"], grupo)
            for capa in grupo["capas"]:
                capas += 1
                donde = capa["id"]
                if capa["tipo"] not in TIPOS:
                    nuevo.append(f"{donde}: tipo de capa «{capa['tipo']}»")
                if capa.get("marcador") and capa["marcador"] not in MARCADORES:
                    nuevo.append(f"{donde}: marcador «{capa['marcador']}»")
                revisar("capa", donde, capa)
                for parte in ("estilo", "rotulo", "popup", "borde", "patron", "filtro", "extrusion"):
                    revisar(parte, donde, capa.get(parte))
                clasificar = capa.get("clasificar") or {}
                revisar("clasificar", donde, clasificar)
                clases = list((clasificar.get("valores") or {}).values()) + list(clasificar.get("rangos") or [])
                for clase in clases + ([clasificar["otro"]] if clasificar.get("otro") else []):
                    revisar("clase", donde, clase)

        self.stdout.write(f"/mapas {version}: {len(manifiesto['grupos'])} grupos y {capas} capas")
        if nuevo:
            for linea in sorted(set(nuevo)):
                self.stdout.write("  NUEVO  " + linea)
            raise CommandError("El manifiesto trae cosas que el mapa no conoce. Revisa estaticos/mapa/capas.js.")
        self.stdout.write("Todo lo publicado es conocido por el mapa.")

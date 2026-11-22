"""Genera los datos del panel de /clima/ desde esta base y, si se pide, los compara con los publicados.

  manage.py clima_panel --comparar   genera en una carpeta aparte y dice en qué difieren de los que están publicados
  manage.py clima_panel --publicar   los escribe en la carpeta que lee el panel
  manage.py clima_panel --recoger ioc inamhi   corre esas fuentes una vez con el recolector de esta aplicación
"""
import json
import tempfile
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand

from clima import fuentes, panel


def _hojas(o, ruta=""):
    if isinstance(o, dict):
        for k, v in o.items():
            yield from _hojas(v, f"{ruta}/{k}")
    elif isinstance(o, list):
        for i, v in enumerate(o):
            yield from _hojas(v, f"{ruta}[{i}]")
    else:
        yield ruta, o


def _iguales(a, b, tolerancia):
    if a == b:
        return True
    if isinstance(a, (int, float)) and isinstance(b, (int, float)) and not isinstance(a, bool) and not isinstance(b, bool):
        return abs(a - b) <= tolerancia
    return False


class Command(BaseCommand):
    help = "Datos del panel de clima generados desde PostgreSQL"

    def add_arguments(self, parser):
        parser.add_argument("--comparar", action="store_true")
        parser.add_argument("--publicar", action="store_true")
        parser.add_argument("--recoger", nargs="*")

    def handle(self, comparar, publicar, recoger, **opciones):
        if recoger is not None:
            for fuente, r in fuentes.recolectar(recoger or None).items():
                self.stdout.write(f"{fuente:14} {r}")
            return
        if publicar:
            self.stdout.write(str(panel.publicar()))
            return
        if not comparar:
            self.stdout.write("Indica --comparar, --publicar o --recoger.")
            return
        publicados = Path(settings.CLIMA_SALIDA)
        with tempfile.TemporaryDirectory() as carpeta:
            self.stdout.write(f"generado en {panel.publicar(carpeta)}")
            for nombre, tolerancia, ignorar in (("estado.json", 0.15, ("/generado", "/calculado", "/segundos", "/fuentes/", "/pronostico/", "/satelite", "ahora_i", "/ts")),
                                                ("horario.json", 0.15, ("/generado",)), ("diario.json", 0.15, ("/generado",))):
                nuevo = dict(_hojas(json.loads((Path(carpeta) / nombre).read_text())))
                viejo = dict(_hojas(json.loads((publicados / nombre).read_text())))
                claves = [k for k in set(nuevo) | set(viejo) if not any(x in k for x in ignorar)]
                faltan = [k for k in claves if k not in nuevo]
                sobran = [k for k in claves if k not in viejo]
                distintos = [k for k in claves if k in nuevo and k in viejo and not _iguales(nuevo[k], viejo[k], tolerancia)]
                self.stdout.write(f"\n{nombre}: {len(claves)} valores comparados · distintos {len(distintos)} · solo en el publicado {len(faltan)} · solo en el nuevo {len(sobran)}")
                for k in sorted(distintos)[:12]:
                    self.stdout.write(f"   ≠ {k}: publicado {str(viejo[k])[:50]!r} · nuevo {str(nuevo[k])[:50]!r}")
                for k in sorted(faltan)[:6]:
                    self.stdout.write(f"   − {k}: {str(viejo[k])[:60]!r}")
                for k in sorted(sobran)[:6]:
                    self.stdout.write(f"   + {k}: {str(nuevo[k])[:60]!r}")

"""Copia las mediciones del recolector anterior a esta base.

  manage.py clima_sincronizar              los últimos 3 días (lo que corre cada 5 minutos)
  manage.py clima_sincronizar --completa   toda la historia (la primera vez, o para conciliar)
  manage.py clima_sincronizar --comparar   solo cuenta filas en los dos lados, por fuente
"""
import sqlite3

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import connection

from clima.sincronizar import sincronizar


class Command(BaseCommand):
    help = "Copia el clima de la base SQLite del recolector a PostgreSQL"

    def add_arguments(self, parser):
        parser.add_argument("--completa", action="store_true")
        parser.add_argument("--dias", type=int, default=3)
        parser.add_argument("--comparar", action="store_true")

    def handle(self, completa, dias, comparar, **opciones):
        if comparar:
            origen = sqlite3.connect(f"file:{settings.CLIMA_SQLITE}?mode=ro", uri=True, timeout=60)
            alla = dict(origen.execute("SELECT fuente, count(*) FROM obs GROUP BY 1"))
            with connection.cursor() as c:
                c.execute("SELECT e.fuente, count(*) FROM clima_observacion o JOIN clima_estacion e ON e.id = o.estacion_id GROUP BY 1")
                aqui = dict(c.fetchall())
            iguales = True
            for fuente in sorted(set(alla) | set(aqui)):
                a, b = alla.get(fuente, 0), aqui.get(fuente, 0)
                iguales &= a == b
                self.stdout.write(f"{fuente:14} origen {a:>9}  aquí {b:>9}  {'=' if a == b else 'DISTINTO (' + str(b - a) + ')'}")
            self.stdout.write("Iguales." if iguales else "Hay diferencias (es normal durante unos minutos: el recolector sigue escribiendo).")
            return
        s = sincronizar(dias=dias, completa=completa)
        self.stdout.write(f"{'ERROR: ' + s.error if s.error else 'bien'} · leídas {s.leidas} · cambiadas {s.cambiadas} · borradas {s.borradas} · {s.segundos} s")

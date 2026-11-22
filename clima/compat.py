"""Conexión de compatibilidad: deja que el recolector anterior (escrito para SQLite) hable con PostgreSQL.

Sus consultas son pocas y simples, sobre tres tablas: obs, estaciones y corridas. En PostgreSQL
esas tres existen como vistas sobre los modelos de Django (migración 0007), con disparadores que
convierten cada INSERT y DELETE. Aquí solo se traduce la sintaxis: «?» por «%s» e
«INSERT OR REPLACE» por «INSERT».
"""
import sys
from pathlib import Path

from django.db import connection

ANTERIOR = Path(__file__).resolve().parent / "anterior"


def modulos():
    """Importa los módulos del recolector anterior (se importan entre sí por su nombre a secas)."""
    if str(ANTERIOR) not in sys.path:
        sys.path.insert(0, str(ANTERIOR))
    import danadas
    import fuentes_extra
    import recolector

    recolector.FUENTES.update(fuentes_extra.FUENTES_EXTRA)
    danadas.DANADAS.refrescar()
    return recolector


class Conexion:
    """Lo que el recolector anterior usa de una conexión de SQLite."""

    @staticmethod
    def _traducir(sql):
        return sql.replace("%", "%%").replace("INSERT OR REPLACE", "INSERT").replace("?", "%s")

    def execute(self, sql, parametros=()):
        c = connection.cursor()
        c.execute(self._traducir(sql), list(parametros))
        return c

    def executemany(self, sql, filas):
        filas = [list(f) for f in filas]
        if filas:
            with connection.cursor() as c:
                c.executemany(self._traducir(sql), filas)

    def commit(self):
        pass  # lo decide la transacción de Django

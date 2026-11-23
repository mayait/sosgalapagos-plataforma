# SOS Galápagos · © 2026 Universidad San Francisco de Quito (USFQ) · Autor: Julián Maya <jamaya@usfq.edu.ec>
# Licencia Apache 2.0 (ver LICENSE y NOTICE): puede reutilizarse dando crédito.
"""El clima queda entero en esta aplicación: sin la base SQLite ni la capa de compatibilidad.

- Se quitan las vistas, funciones y disparadores que imitaban la base SQLite del recolector anterior.
- El registro de copias desde SQLite deja de ser un modelo. Su tabla no se borra: se guarda con
  el nombre archivo_clima_sincronizacion.
- Las corridas de los modelos de pronóstico pasan de archivos a una tabla.
- El mar modelado guarda de qué fuente viene (Stormglass u Open-Meteo).
"""
import django.db.models.deletion  # noqa: F401
from django.db import migrations, models

QUITAR_COMPATIBILIDAD = """
DROP VIEW IF EXISTS obs CASCADE;
DROP VIEW IF EXISTS estaciones CASCADE;
DROP VIEW IF EXISTS corridas CASCADE;
DROP FUNCTION IF EXISTS obs_insertar() CASCADE;
DROP FUNCTION IF EXISTS obs_borrar() CASCADE;
DROP FUNCTION IF EXISTS estaciones_insertar() CASCADE;
DROP FUNCTION IF EXISTS corridas_insertar() CASCADE;
DROP FUNCTION IF EXISTS date(text, text) CASCADE;
"""


class Migration(migrations.Migration):
    dependencies = [("clima", "0007_compatibilidad")]

    operations = [
        migrations.RunSQL(QUITAR_COMPATIBILIDAD, migrations.RunSQL.noop),
        migrations.SeparateDatabaseAndState(
            state_operations=[migrations.DeleteModel(name="Sincronizacion")],
            database_operations=[migrations.RunSQL("ALTER TABLE clima_sincronizacion RENAME TO archivo_clima_sincronizacion",
                                                   "ALTER TABLE archivo_clima_sincronizacion RENAME TO clima_sincronizacion")],
        ),
        migrations.CreateModel(
            name="PronosticoCorrida",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("modelo", models.CharField(max_length=40)),
                ("tipo", models.CharField(max_length=12)),
                ("referencia", models.DateTimeField()),
                ("corrida", models.DateTimeField(blank=True, null=True)),
                ("disponible", models.DateTimeField(blank=True, null=True)),
                ("recibido", models.DateTimeField()),
                ("datos", models.JSONField(default=dict)),
            ],
            options={"verbose_name": "corrida de un modelo", "verbose_name_plural": "corridas de los modelos", "ordering": ["-recibido"]},
        ),
        migrations.AddConstraint(model_name="pronosticocorrida", constraint=models.UniqueConstraint(fields=("modelo", "tipo", "referencia"), name="pronostico_corrida_unica")),
        migrations.AddIndex(model_name="pronosticocorrida", index=models.Index(fields=["tipo", "modelo", "-recibido"], name="pronostico_corrida_ultima")),
        migrations.RemoveConstraint(model_name="marhora", name="mar_hora_unica"),
        migrations.AddField(model_name="marhora", name="fuente", field=models.CharField(default="stormglass", max_length=12)),
        migrations.AddConstraint(model_name="marhora", constraint=models.UniqueConstraint(fields=("puerto", "fuente", "hora"), name="mar_hora_unica")),
    ]

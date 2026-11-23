# SOS Galápagos · © 2026 Universidad San Francisco de Quito (USFQ) · Autor: Julián Maya <jamaya@usfq.edu.ec>
# Todos los derechos reservados. Usar, copiar, modificar o derivar de este código requiere permiso escrito del autor (ver LICENSE).
"""Informe comunitario en la línea del tiempo y el tipo de aviso «Encañada obstruida».

La encañada obstruida es un peligro que dura hasta que se limpia: plazo de un año y la coordinación lo
cierra a mano cuando llega la maquinaria. Nace con el informe de campo del barrio Tomás de Berlanga (13-nov-2026).
"""
from django.db import migrations, models


def crear_tipo(apps, schema_editor):
    TipoRiesgo = apps.get_model("reportes", "TipoRiesgo")
    TipoRiesgo.objects.get_or_create(codigo="encanada_obstruida", defaults={
        "nombre": "Encañada obstruida", "icono": "quebrada", "plazo_horas": 24 * 365, "orden": 8, "clase": "riesgo"})


class Migration(migrations.Migration):

    dependencies = [("reportes", "0008_avisos_y_cronica")]

    operations = [
        migrations.AlterField(
            model_name="suceso",
            name="clase",
            field=models.CharField(choices=[("oficial", "Informe o comunicado oficial"), ("noticia", "Noticia"),
                                            ("informe", "Informe o mapa de SOS Galápagos"), ("nota", "Nota de coordinación"),
                                            ("barrio", "Informe comunitario")], default="nota", max_length=8),
        ),
        migrations.RunPython(crear_tipo, migrations.RunPython.noop),
    ]

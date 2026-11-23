# SOS Galápagos · © 2026 Universidad San Francisco de Quito (USFQ) · Autor: Julián Maya <jamaya@usfq.edu.ec>
# Licencia Apache 2.0 (ver LICENSE y NOTICE): puede reutilizarse dando crédito.
"""Título propio y fotos adicionales en los avisos; «Dónde donar o colaborar» pasa a llevar un corazón."""
import django.db.models.deletion
from django.db import migrations, models


def corazon(apps, editor):
    apps.get_model("reportes", "TipoRiesgo").objects.filter(codigo="donar_colaborar", icono="manos").update(icono="corazon")


class Migration(migrations.Migration):
    dependencies = [("reportes", "0003_clases_de_aviso")]
    operations = [
        migrations.AddField(
            model_name="reporte", name="titulo", field=models.CharField(blank=True, max_length=80, verbose_name="título")
        ),
        migrations.CreateModel(
            name="FotoReporte",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("foto", models.ImageField(upload_to="reportes/%Y/%m/")),
                ("pie", models.CharField(blank=True, max_length=140)),
                ("orden", models.PositiveSmallIntegerField(default=0)),
                ("reporte", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="fotos_extra", to="reportes.reporte")),
            ],
            options={"verbose_name": "foto adicional", "verbose_name_plural": "fotos adicionales", "ordering": ["orden", "id"]},
        ),
        migrations.RunPython(corazon, migrations.RunPython.noop),
    ]

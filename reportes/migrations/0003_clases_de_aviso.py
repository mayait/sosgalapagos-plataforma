# SOS Galápagos · © 2026 Universidad San Francisco de Quito (USFQ) · Autor: Julián Maya <jamaya@usfq.edu.ec>
# Todos los derechos reservados. Usar, copiar, modificar o derivar de este código requiere permiso escrito del autor (ver LICENSE).
"""Clases de aviso: además de los peligros, cosas buenas y lugares donde donar o colaborar."""
from django.db import migrations, models

NUEVOS = [
    # código, nombre, icono, plazo en horas, clase
    ("algo_bueno", "Algo bueno", "corazon", 48, "bueno"),
    ("donar_colaborar", "Dónde donar o colaborar", "manos", 72, "ayuda"),
]


def cargar(apps, editor):
    TipoRiesgo = apps.get_model("reportes", "TipoRiesgo")
    for orden, (codigo, nombre, icono, horas, clase) in enumerate(NUEVOS, start=20):
        TipoRiesgo.objects.get_or_create(
            codigo=codigo, defaults={"nombre": nombre, "icono": icono, "plazo_horas": horas, "orden": orden, "clase": clase}
        )


class Migration(migrations.Migration):
    dependencies = [("reportes", "0002_tipos_iniciales")]
    operations = [
        migrations.AddField(
            model_name="tiporiesgo",
            name="clase",
            field=models.CharField(
                choices=[("riesgo", "Un peligro"), ("bueno", "Algo bueno"), ("ayuda", "Dónde donar o colaborar")],
                default="riesgo",
                max_length=8,
            ),
        ),
        migrations.AlterModelOptions(
            name="tiporiesgo",
            options={"ordering": ["orden", "nombre"], "verbose_name": "tipo de aviso", "verbose_name_plural": "tipos de aviso"},
        ),
        migrations.RunPython(cargar, migrations.RunPython.noop),
    ]

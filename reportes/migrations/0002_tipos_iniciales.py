# SOS Galápagos · © 2026 Universidad San Francisco de Quito (USFQ) · Autor: Julián Maya <jamaya@usfq.edu.ec>
# Todos los derechos reservados. Usar, copiar, modificar o derivar de este código requiere permiso escrito del autor (ver LICENSE).
"""Tipos de riesgo iniciales, con su plazo de vida. Se editan después en el admin."""
from django.db import migrations

TIPOS = [
    ("agua_via", "Agua en la vía", "agua", 6),
    ("quebrada", "Quebrada crecida", "quebrada", 6),
    ("via_cortada", "Vía cortada", "corte", 24),
    ("vivienda", "Vivienda anegada", "casa", 24),
    ("cable", "Cable caído", "cable", 24),
    ("deslizamiento", "Deslizamiento", "deslizamiento", 72),
]


def cargar(apps, editor):
    TipoRiesgo = apps.get_model("reportes", "TipoRiesgo")
    for orden, (codigo, nombre, icono, horas) in enumerate(TIPOS, start=1):
        TipoRiesgo.objects.get_or_create(
            codigo=codigo, defaults={"nombre": nombre, "icono": icono, "plazo_horas": horas, "orden": orden}
        )


class Migration(migrations.Migration):
    dependencies = [("reportes", "0001_initial")]
    operations = [migrations.RunPython(cargar, migrations.RunPython.noop)]

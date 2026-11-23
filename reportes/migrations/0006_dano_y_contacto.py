# SOS Galápagos · © 2026 Universidad San Francisco de Quito (USFQ) · Autor: Julián Maya <jamaya@usfq.edu.ec>
# Licencia Apache 2.0 (ver LICENSE y NOTICE): puede reutilizarse dando crédito.
"""Daño en infraestructura pública (dura más que una inundación) y contacto en los lugares de donación."""
from django.db import migrations


def cargar(apps, editor):
    TipoRiesgo = apps.get_model("reportes", "TipoRiesgo")
    # Un daño en una vía, un puente o una tubería no baja en horas: 14 días, renovables con «sigue ahí».
    TipoRiesgo.objects.get_or_create(
        codigo="dano_infraestructura",
        defaults={"nombre": "Daño en infraestructura pública", "icono": "obra", "plazo_horas": 14 * 24, "orden": 7, "clase": "riesgo"},
    )
    TipoRiesgo.objects.filter(codigo="donar_colaborar").update(pide_contacto=True)


class Migration(migrations.Migration):
    dependencies = [("reportes", "0005_fase2")]
    operations = [migrations.RunPython(cargar, migrations.RunPython.noop)]

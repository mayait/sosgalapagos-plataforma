# SOS Galápagos · © 2026 Universidad San Francisco de Quito (USFQ) · Autor: Julián Maya <jamaya@usfq.edu.ec>
# Licencia Apache 2.0 (ver LICENSE y NOTICE): puede reutilizarse dando crédito.
"""El tipo «refugio» lo usa coordinación para poner en el mapa los refugios vigentes, desde el admin.

Sigue inactivo para el público (no sale en el formulario ni en WhatsApp): un refugio falso o cerrado a destiempo
en una emergencia es peor que ninguno. Dura 30 días; coordinación lo cierra a mano cuando deja de funcionar.
"""
from django.db import migrations


def adelante(apps, schema_editor):
    TipoRiesgo = apps.get_model("reportes", "TipoRiesgo")
    TipoRiesgo.objects.filter(codigo="refugio").update(nombre="Refugio", plazo_horas=720, activo=False)


def atras(apps, schema_editor):
    TipoRiesgo = apps.get_model("reportes", "TipoRiesgo")
    TipoRiesgo.objects.filter(codigo="refugio").update(nombre="Refugio o alojamiento", plazo_horas=72)


class Migration(migrations.Migration):
    dependencies = [("reportes", "0014_historial_coordinacion_anterior")]
    operations = [migrations.RunPython(adelante, atras)]

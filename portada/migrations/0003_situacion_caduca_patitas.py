# SOS Galápagos · © 2026 Universidad San Francisco de Quito (USFQ) · Autor: Julián Maya <jamaya@usfq.edu.ec>
# Licencia Apache 2.0 (ver LICENSE y NOTICE): puede reutilizarse dando crédito.
"""«Situación hoy» caduca sola, y la cuenta de Patitas Galapagueñas se publica.

- Las líneas que había (revisadas el 4 de noviembre) quedan ya caducadas: estaban desactualizadas
  y la portada no muestra la sección mientras no haya una vigente.
- Patitas Galapagueñas: su cuenta está a nombre de una persona. Julián autorizó publicarla el
  23-nov-2026. Solo se llena si coordinación no puso otros datos.
"""
from datetime import datetime, timedelta, timezone

from django.db import migrations, models

GALAPAGOS = timezone(timedelta(hours=-6))
CADUCADA = datetime(2026, 11, 5, 7, 0, tzinfo=GALAPAGOS)  # un día después de la última revisión
PATITAS = "Banco Pichincha · Cuenta transaccional 2203496066\nTitular: Fátima Samanta Walthert"


def cargar(apps, schema_editor):
    Situacion = apps.get_model("portada", "Situacion")
    Organizacion = apps.get_model("portada", "Organizacion")
    Situacion.objects.filter(caduca__isnull=True, actualizado__lt=CADUCADA).update(caduca=CADUCADA)
    Organizacion.objects.filter(nombre="Patitas Galapagueñas", pago="").update(pago=PATITAS)


class Migration(migrations.Migration):
    dependencies = [("portada", "0002_contenido_actual")]
    operations = [
        migrations.AddField(
            model_name="situacion",
            name="caduca",
            field=models.DateTimeField(blank=True, help_text="Al pasar esta fecha y hora la línea se oculta sola. Vacío: se ve hasta que la ocultes.",
                                       null=True, verbose_name="deja de verse"),
        ),
        migrations.AlterField(
            model_name="organizacion",
            name="pago",
            field=models.TextField(blank=True, help_text="Cuentas a nombre de la organización (con su RUC). Una cuenta a nombre de una persona solo si coordinación lo autorizó.",
                                   verbose_name="datos de transferencia"),
        ),
        migrations.RunPython(cargar, migrations.RunPython.noop),
    ]

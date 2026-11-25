# SOS Galápagos · © 2026 Universidad San Francisco de Quito (USFQ) · Autor: Julián Maya <jamaya@usfq.edu.ec>
# Licencia Apache 2.0 (ver LICENSE y NOTICE): puede reutilizarse dando crédito.
"""Un documento oficial también puede ser una imagen: muchos boletines se publican como foto, no como PDF."""
from django.db import migrations, models

import reportes.models


class Migration(migrations.Migration):
    dependencies = [("reportes", "0015_refugio_de_coordinacion")]
    operations = [
        migrations.AddField(
            model_name="suceso",
            name="imagen",
            field=models.ImageField("imagen del documento", upload_to=reportes.models.ruta_imagen_oficial, blank=True,
                                    help_text="Si el documento es una imagen (un boletín publicado como foto). Es pública."),
        ),
    ]

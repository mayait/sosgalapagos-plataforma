"""Crea reportes de demostración en Puerto Ayora para ver el mapa en la Mac.

Uso: manage.py sembrar_demo [--cantidad 200]
Con --cantidad reparte reportes al azar: sirve para la prueba de rendimiento en un
teléfono de gama baja. NUNCA se corre en el servidor: se niega si DEPURAR no es 1.
"""
import random
from datetime import timedelta

from django.conf import settings
from django.contrib.gis.geos import Point
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from reportes import reglas
from reportes.models import Estado, Fuente, Gravedad, Profundidad, Reporte, TipoConfirmacion, TipoRiesgo
from zonas.models import zona_de

# (tipo, lon, lat, minutos de edad, gravedad, profundidad, fuente, nota)
ESCENA = [
    ("agua_via", -90.3128, -0.7392, 12, "no_pasar", "rodilla", "vecino", "El agua corre fuerte hacia la esquina"),
    ("quebrada", -90.3139, -0.7376, 35, "peligro_vida", "cintura", "coordinador", "Cauce desbordado; no cruzar"),
    ("vivienda", -90.3118, -0.7401, 80, "cuidado", "tobillo", "vecino", ""),
    ("agua_via", -90.3162, -0.7431, 200, "cuidado", "tobillo", "vecino", ""),
    ("via_cortada", -90.3189, -0.7352, 300, "no_pasar", "sin_dato", "institucion", "Vía a Bellavista cerrada por material en la calzada"),
    ("cable", -90.3099, -0.7446, 600, "peligro_vida", "sin_dato", "vecino", ""),
    ("agua_via", -90.3147, -0.7462, 320, "cuidado", "tobillo", "vecino", ""),
    ("deslizamiento", -90.3225, -0.7318, 1500, "no_pasar", "sin_dato", "coordinador", "Talud caído sobre media vía"),
    ("agua_via", -90.3075, -0.7419, 5, "no_pasar", "rodilla", "whatsapp", ""),
    ("algo_bueno", -90.3152, -0.7408, 40, "cuidado", "sin_dato", "coordinador", "Vecinos reparten almuerzos calientes en la cancha"),
    ("donar_colaborar", -90.3108, -0.7428, 90, "cuidado", "sin_dato", "coordinador", "Reciben agua y ropa seca de 8 a 18 h; faltan voluntarios para clasificar"),
]


class Command(BaseCommand):
    help = "Reportes de demostración (solo en la Mac)"

    def add_arguments(self, parser):
        parser.add_argument("--cantidad", type=int, default=0, help="Reportes al azar adicionales")

    def handle(self, cantidad, **opciones):
        if not settings.DEBUG:
            raise CommandError("sembrar_demo solo corre en desarrollo (DEPURAR=1).")
        ahora = timezone.now()
        tipos = {t.codigo: t for t in TipoRiesgo.objects.all()}
        creados = []
        for codigo, lon, lat, edad, gravedad, profundidad, fuente, nota in ESCENA:
            punto = Point(lon, lat, srid=4326)
            visto = ahora - timedelta(minutes=edad)
            r = reglas.crear_reporte(
                tipo=tipos[codigo], punto=punto, huella="demo", fuente=fuente, visto_en=visto, ahora=visto,
                gravedad=gravedad, profundidad=profundidad, nota=nota, zona=zona_de(punto),
            ).reporte
            creados.append(r)
        # Uno confirmado por coordinación, uno bajando y uno ya cerrado, para ver los tres estados.
        Reporte.objects.filter(pk=creados[0].pk).update(estado=Estado.CONFIRMADO, contenido_visible=True)
        reglas.confirmar(creados[3], TipoConfirmacion.YA_BAJO, "demo-2", ahora=ahora - timedelta(minutes=20))
        reglas.confirmar(creados[6], TipoConfirmacion.YA_BAJO, "demo-2", ahora=ahora - timedelta(minutes=50))
        reglas.confirmar(creados[6], TipoConfirmacion.YA_BAJO, "demo-3", ahora=ahora - timedelta(minutes=40))

        azar = random.Random(2026)
        for _ in range(cantidad):
            tipo = azar.choice(list(tipos.values()))
            punto = Point(-90.3145 + azar.uniform(-0.02, 0.02), -0.7435 + azar.uniform(-0.02, 0.012), srid=4326)
            visto = ahora - timedelta(minutes=azar.uniform(1, tipo.plazo_horas * 55))
            reglas.crear_reporte(
                tipo=tipo, punto=punto, huella=f"demo-{azar.random()}", visto_en=visto, ahora=visto,
                fuente=azar.choice([Fuente.VECINO, Fuente.VECINO, Fuente.COORDINADOR]),
                gravedad=azar.choice(Gravedad.values), profundidad=azar.choice(Profundidad.values), zona=zona_de(punto),
            )
        self.stdout.write(f"Reportes en la base: {Reporte.objects.count()} ({Reporte.objects.vivos().count()} vivos)")

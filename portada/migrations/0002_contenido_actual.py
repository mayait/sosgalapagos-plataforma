# SOS Galápagos · © 2026 Universidad San Francisco de Quito (USFQ) · Autor: Julián Maya <jamaya@usfq.edu.ec>
# Licencia Apache 2.0 (ver LICENSE y NOTICE): puede reutilizarse dando crédito.
"""Carga el contenido que tenía la portada anterior el 23-nov-2026, con sus fechas reales.

- El aviso del sábado 21 de noviembre entra ya vencido y desactivado: queda en el admin como modelo.
- «Situación hoy» se revisó por última vez el miércoles 4 de noviembre a las 07:00.
- Mascotas: de Patitas Galapagueñas no se carga la cuenta bancaria, porque está a nombre de una
  persona y trae su cédula; queda su Facebook.
Solo crea lo que falta: no pisa lo que coordinación ya haya editado.
"""
from datetime import datetime, timedelta, timezone

from django.db import migrations

GALAPAGOS = timezone(timedelta(hours=-6))

AVISO = {
    "titulo": "Hoy, sábado 21 de noviembre: se reportan inundaciones en Puerto Ayora y la parte alta",
    "texto": ("Desde las 05:00 hay reportes de vecinos de inundación en La Cascada (pasajes 4 y 5 y viviendas junto al cauce), la calle 8, "
              "Divino Niño, Curva Brava y el Parque El Bosque, y de vías colapsadas en la toma de agua y en la salida a Miramar. Llovió fuerte "
              "toda la noche en Bellavista, Cascajo y Santa Rosa. Si vives junto a un cauce o una encañada, sal ya hacia un lugar alto y no "
              "cruces calles por donde corre el agua. Emergencias: 911. Son reportes ciudadanos de las 05:00 a las 06:30, no un comunicado "
              "oficial: sigue las indicaciones del COE y del ECU 911."),
    "hasta": datetime(2026, 11, 21, 23, 59, tzinfo=GALAPAGOS),
    "activo": False,
    "creado": datetime(2026, 11, 21, 6, 30, tzinfo=GALAPAGOS),
}

REVISADO = datetime(2026, 11, 4, 7, 0, tzinfo=GALAPAGOS)
SITUACION = [
    ("Refugio", "El único refugio autorizado es el Colegio Miguel Ángel Cazares (Puerto Ayora). Se está trasladando ahí a las familias de otros sitios y de hoteles."),
    ("Donaciones en Santa Cruz", "Centro de acopio oficial: Colegio Miguel Ángel Cazares. También recibe la bodega del club de ciclismo, junto al coliseo de "
                                 "Puerto Ayora (punto comunitario), que reparte a La Cascada, El Bosque, Guayabillos y Aguacatal."),
    ("Comida", "Las cocinas comunitarias de la Fundación Torraja y de La Colmena dan comida a las familias afectadas todos los días. Necesitan víveres, verduras y proteína."),
    ("Salud", "Según un aviso difundido el 2 de noviembre, desde el 4 hay controles para embarazadas y madres que acaban de dar a luz en el Centro de Energías "
              "Renovables (Pampas Coloradas). Confirma el horario en el centro de salud. Ante fiebre, acude al centro de salud: hay riesgo de dengue."),
    ("Dengue", "Elimina el agua estancada cerca de tu casa, usa repelente y duerme con mosquitero."),
    ("Zonas que aún necesitan ayuda", "Bellavista y Miconia (parte alta), El Bosque, Guayabillos, Aguacatal, Scalesia y Los Arrayanes. Hacen falta vehículos para llegar."),
]

ORGANIZACIONES = [
    {"nombre": "USFQ Galápagos · Galápagos Science Center", "instagram": "usfqgalapagos", "enlace": "https://www.facebook.com/GalapagosGSC/",
     "enlace_texto": "Galápagos Science Center", "donar": "https://btnpagos.usfq.edu.ec/pagos/eventos.aspx?adm=810110836"},
    {"nombre": "Funcavid — Fundación Un Cambio por la Vida", "instagram": "fundacionuncambioxlavida"},
    {"nombre": "Fundación Charles Darwin (FCD)", "instagram": "charlesdarwinfoundation"},
    {"nombre": "Fundación Jocotoco", "instagram": "fundacion.jocotoco"},
    {"nombre": "Galápagos Life Fund", "instagram": "galapagos.life.fund"},
    {"nombre": "Galapagos Conservancy", "instagram": "galapagosconservancy"},
    {"nombre": "Fundación ECOS"},
    {"nombre": "CAPTURGAL — Cámara Provincial de Turismo de Galápagos", "instagram": "capturgal"},
    {"nombre": "Fundación Torraja corazones grandes — cocina comunitaria", "facebook": "https://www.facebook.com/profile.php?id=100087466970206"},
    {"categoria": "mascotas", "nombre": "Fundación Pan Animalia Galápagos",
     "detalle": "Atiende a los animales afectados. Recibe alimento para perros y gatos (balanceado o húmedo), collares y correas, kenneles o transportadoras y toallas.",
     "pago": "Banco del Pacífico · Cuenta corriente 8243689\nTitular: Fundación Pan Animalia Galápagos · RUC 2091767327001"},
    {"categoria": "mascotas", "nombre": "WVS South America", "detalle": "Clínica veterinaria en Puerto Ayora, en alianza con Worldwide Veterinary Service y Pan Animalia.",
     "facebook": "https://www.facebook.com/wvssouthamerica"},
    {"categoria": "mascotas", "nombre": "Patitas Galapagueñas", "facebook": "https://www.facebook.com/patitasgalapaguenas"},
    {"categoria": "mascotas", "nombre": "Juanchito al Rescate Galápagos", "facebook": "https://www.facebook.com/Juanchitoalrescategps",
     "donar": "https://paypal.me/juanchitoalrescategp", "donar_texto": "Donar por PayPal"},
]


def cargar(apps, schema_editor):
    Aviso = apps.get_model("portada", "Aviso")
    Situacion = apps.get_model("portada", "Situacion")
    Organizacion = apps.get_model("portada", "Organizacion")
    if not Aviso.objects.exists():
        Aviso.objects.create(**AVISO)
    if not Situacion.objects.exists():
        for orden, (tema, texto) in enumerate(SITUACION, start=1):
            Situacion.objects.create(tema=tema, texto=texto, orden=orden, actualizado=REVISADO)
    if not Organizacion.objects.exists():
        for orden, datos in enumerate(ORGANIZACIONES, start=1):
            Organizacion.objects.create(orden=orden, **datos)


class Migration(migrations.Migration):
    dependencies = [("portada", "0001_initial")]
    operations = [migrations.RunPython(cargar, migrations.RunPython.noop)]

"""Ajustes de la plataforma de reportes de SOS Galápagos.

Todo lo que cambia entre la Mac y el servidor llega por variables de entorno.
Los umbrales de las reglas de vida están al final y son preliminares.
"""
import os
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent


def entorno(nombre, defecto=None):
    return os.environ.get(nombre, defecto)


DEBUG = entorno("DEPURAR", "0") == "1"
SECRET_KEY = entorno("CLAVE_SECRETA", "solo-para-desarrollo-local" if DEBUG else None)
if not SECRET_KEY:
    raise RuntimeError("Falta la variable CLAVE_SECRETA")

# En desarrollo se acepta cualquier nombre, para abrir el mapa desde un teléfono de la misma red.
ALLOWED_HOSTS = ["*"] if DEBUG else entorno("ANFITRIONES", "localhost,127.0.0.1").split(",")
CSRF_TRUSTED_ORIGINS = [o for o in entorno("ORIGENES_CONFIABLES", "").split(",") if o]

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.gis",
    "django_tasks_db",
    "reportes",
    "zonas",
    "api",
    "entradas",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "plataforma.rutas"
WSGI_APPLICATION = "plataforma.wsgi.application"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [RAIZ / "plantillas"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

DATABASES = {
    "default": {
        "ENGINE": "django.contrib.gis.db.backends.postgis",
        "NAME": entorno("BD_NOMBRE", "plataforma"),
        "USER": entorno("BD_USUARIO", "plataforma"),
        "PASSWORD": entorno("BD_CLAVE", "plataforma"),
        "HOST": entorno("BD_ANFITRION", "localhost"),
        "PORT": entorno("BD_PUERTO", "5432"),
    }
}
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Tareas en segundo plano: en la base de datos, sin Redis ni Celery.
TASKS = {"default": {"BACKEND": "django_tasks_db.DatabaseBackend"}}

LANGUAGE_CODE = "es"
TIME_ZONE = "Pacific/Galapagos"
USE_I18N = True
USE_TZ = True  # en la base todo se guarda en UTC

# Todo lo de la plataforma vive bajo /riesgos/: el sitio actual ya usa /api y /admin.
STATIC_URL = "/riesgos/estaticos/"
STATICFILES_DIRS = [RAIZ / "estaticos"]
STATIC_ROOT = RAIZ / "estaticos_reunidos"
MEDIA_URL = "/riesgos/medios/"
MEDIA_ROOT = Path(entorno("MEDIOS_DIR", RAIZ / "medios"))
DATA_UPLOAD_MAX_MEMORY_SIZE = 8 * 1024 * 1024
FILE_UPLOAD_MAX_MEMORY_SIZE = 8 * 1024 * 1024

SESSION_COOKIE_SECURE = not DEBUG
CSRF_COOKIE_SECURE = not DEBUG
X_FRAME_OPTIONS = "SAMEORIGIN"  # igual que la cabecera que ya pone Caddy
# OpenStreetMap rechaza las teselas pedidas sin decir desde qué sitio (403 «Access blocked»).
# Django por defecto no envía el origen a otros dominios; aquí se envía solo el dominio, nunca la ruta.
SECURE_REFERRER_POLICY = "strict-origin-when-cross-origin"
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

# ── Mapa ──────────────────────────────────────────────────────────────────────
# Vista inicial: centro de Puerto Ayora, a nivel de calles (ver docs/visual-mapa.md).
MAPA_CENTRO = (-90.3145, -0.7435)  # longitud, latitud
MAPA_ZOOM = 16
# Mapa base al abrir: «calles» (Julián, 21-nov-2026; antes fue «satelite»). Es el mismo
# con el que abre /mapas. Son teselas de un tercero (OpenStreetMap): sin conexión el mapa
# usa la base gris propia, que va guardada en el teléfono. Otras: gris, satelite, topografico.
MAPA_BASE_INICIAL = "calles"

# Capas de riesgo: se leen de lo mismo que publica /mapas (repo sosgalapagos-datos):
#   capas.json       manifiesto de grupos, capas, estilos y leyendas
#   descargas.json   índice de descargas en Shapefile y GeoJSON de cada capa
#   datos/<variante>/…  los archivos de cada capa
# Así el mapa nuevo y /mapas muestran siempre las mismas capas, y cada una se
# puede encender, apagar y descargar.
CAPAS_URL = entorno("CAPAS_URL", "/mapas/")
CAPAS_VARIANTE = "completo"  # islas completas, sin recorte
# En la Mac no existe /mapas: se trae del sitio publicado y se guarda una copia local.
CAPAS_ORIGEN = entorno("CAPAS_ORIGEN", "https://sosgalapagos.org/mapas/")
CAPAS_COPIA = Path(entorno("CAPAS_COPIA", RAIZ / ".copia-mapas"))
# Capas que arrancan encendidas: las mismas que /mapas marca como visibles en su
# manifiesto (reportes de campo, riesgo modelado, quebradas, puntos clave, barrios…).
# No hay lista propia: si el repo de datos añade una capa visible, aquí también sale.
# En el teléfono /mapas apaga las capas pesadas («visible_movil»: false). Aquí eso se
# respeta, salvo en estos grupos, que deben salir siempre: el riesgo de inundación
# modelado y las quebradas (indicación de Julián, 21-nov-2026).
CAPAS_SIEMPRE_GRUPOS = ["lluvia", "hidrografia"]
# Única excepción: los puntos de salud, refugios y seguridad arrancan apagados aunque
# /mapas los encienda. Son círculos rojos, verdes y morados que se confunden con los
# pines de los reportes. Se encienden desde el panel Capas como cualquier otra.
CAPAS_APAGADAS_AL_ABRIR = ["puntos_criticos"]

# Lluvia: el JSON que publica /clima. Ruta de archivo en el servidor o URL en la Mac.
CLIMA_ESTADO = entorno("CLIMA_ESTADO", "https://sosgalapagos.org/clima/datos/estado.json")
CLIMA_MAX_EDAD_MIN = 20  # con datos más viejos no se muestra nivel
# Lluvia por hora de cada estación (para el informe): el otro JSON que publica /clima.
CLIMA_HORARIO = entorno("CLIMA_HORARIO", "https://sosgalapagos.org/clima/datos/horario.json")

# Relieve propio para la vista 3D: teselas de cota que genera sosgalapagos-datos
# (37_teselas_relieve3d.py; 47 MB, no van a git). Las sirve la plataforma desde una carpeta
# aparte, para no depender de que /mapas las publique. Si la carpeta no existe, el mapa
# prueba en /mapas y, al final, usa un relieve de terceros.
RELIEVE_DIR = Path(entorno("RELIEVE_DIR", RAIZ / ".copia-mapas" / "teselas" / "relieve3d"))
RELIEVE_URL = "/riesgos/relieve3d/"

# ── Reglas de vida del reporte (PRELIMINARES; ver reportes/reglas.py) ─────────
DUPLICADO_METROS = 50          # mismo tipo y más cerca que esto = confirmación del existente
YA_BAJO_PARA_CERRAR = 2        # confirmaciones «ya bajó» de dispositivos distintos
CERCA_METROS = 1500            # radio de «lo que hay cerca»
LIMITE_REPORTES_HORA = 12      # por dispositivo, en el formulario web

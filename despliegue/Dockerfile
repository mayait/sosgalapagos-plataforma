# SOS Galápagos · © 2026 Universidad San Francisco de Quito (USFQ) · Autor: Julián Maya <jamaya@usfq.edu.ec>
# Todos los derechos reservados. Usar, copiar, modificar o derivar de este código requiere permiso escrito del autor (ver LICENSE).
# Imagen de la plataforma: Django + GeoDjango. La misma sirve para la web, el trabajador y el reloj.
FROM python:3.12-slim-trixie
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
# gdal-bin trae GDAL, GEOS y PROJ, que GeoDjango carga en tiempo de ejecución.
RUN apt-get update \
 && apt-get install -y --no-install-recommends gdal-bin \
 && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requisitos.txt .
RUN pip install -r requisitos.txt
COPY . .
# Reúne los archivos estáticos para que los sirva WhiteNoise.
RUN DEPURAR=1 python manage.py collectstatic --noinput
EXPOSE 8000
CMD ["gunicorn", "plataforma.wsgi", "--bind", "0.0.0.0:8000", "--workers", "3"]

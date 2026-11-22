#!/bin/sh
# SOS Galápagos · © 2026 Universidad San Francisco de Quito (USFQ) · Autor: Julián Maya <jamaya@usfq.edu.ec>
# Todos los derechos reservados. Usar, copiar, modificar o derivar de este código requiere permiso escrito del autor (ver LICENSE).
# Entorno local en la Mac con «container» (Apple), porque aquí no hay Docker.
# Uso: despliegue/local.sh <orden de manage.py…>   p. ej.  despliegue/local.sh migrate
#      despliegue/local.sh servidor                levanta la web en http://localhost:8000
#      despliegue/local.sh pruebas                 corre pytest
# Requiere el contenedor de la base: ver «Arranque local» en el README.
set -eu
cd "$(dirname "$0")/.."
IP_BD=$(container inspect sosg-bd | python3 -c "import json,sys; print(json.load(sys.stdin)[0]['status']['networks'][0]['ipv4Address'].split('/')[0])")
COMUN="--rm -e DEPURAR=1 -e BD_ANFITRION=$IP_BD -v $(pwd):/app"
case "${1:-}" in
  servidor) container rm -f sosg-web >/dev/null 2>&1 || true
            exec container run -d --name sosg-web -p 8000:8000 $COMUN sosg-plataforma python manage.py runserver 0.0.0.0:8000 ;;
  pruebas)  shift; exec container run $COMUN sosg-plataforma pytest -q "$@" ;;
  *)        exec container run $COMUN sosg-plataforma python manage.py "$@" ;;
esac

#!/usr/bin/env bash
# Despliega o actualiza el mapa de riesgos en el servidor. Solo añade: no reinicia el sitio.
# Uso (en el servidor):  /opt/sosgalapagos-plataforma/despliegue/produccion/desplegar.sh
#
# La primera vez crea el .env con claves nuevas. La ruta /riesgos/ en Caddy se añade aparte
# (ver despliegue/servidor.md): este guion no toca el Caddy del sitio.
set -euo pipefail
cd "$(dirname "$0")"
REPO="$(cd ../.. && pwd)"

if [ ! -f .env ]; then
  echo "→ Creando .env con claves nuevas"
  umask 077
  sed -e "s|^POSTGRES_PASSWORD=.*|POSTGRES_PASSWORD=$(openssl rand -hex 24)|" \
      -e "s|^CLAVE_SECRETA=.*|CLAVE_SECRETA=$(openssl rand -hex 32)|" env.ejemplo > .env
fi

echo "→ Actualizando el código"
git -C "$REPO" pull --ff-only

echo "→ Construyendo y levantando (las migraciones corren antes que la web)"
docker compose up -d --build

echo "→ Esperando al mapa"
for i in $(seq 1 40); do
  if docker compose exec -T plataforma python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://localhost:8000/riesgos/api/reportes/vivos.geojson', timeout=5).status == 200 else 1)" 2>/dev/null; then
    echo "Mapa listo"; break
  fi
  sleep 3
  [ "$i" = 40 ] && { echo "El mapa no respondió"; docker compose logs --tail 60 plataforma; exit 1; }
done

echo "→ Zonas (barrios y sectores, de lo que publica /mapas)"
docker compose exec -T plataforma python manage.py cargar_zonas || echo "  (no se pudieron cargar ahora; se puede repetir)"

git -C "$REPO" log -1 --format='%h %cI' > version.txt
docker compose ps

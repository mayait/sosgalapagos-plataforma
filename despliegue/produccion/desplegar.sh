#!/usr/bin/env bash
# SOS Galápagos · © 2026 Universidad San Francisco de Quito (USFQ) · Autor: Julián Maya <jamaya@usfq.edu.ec>
# Licencia Apache 2.0 (ver LICENSE y NOTICE): puede reutilizarse dando crédito.
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

echo "→ Construyendo"
docker compose build

# Llaves que se crean una sola vez y nunca van a git.
if ! grep -q '^PUSH_PRIVADA=.\+' .env; then
  echo "→ Creando las llaves de los avisos del navegador"
  sed -i '/^PUSH_PUBLICA=/d;/^PUSH_PRIVADA=/d' .env
  docker compose run --rm --no-deps -T plataforma python manage.py llaves_push >> .env
fi
if ! grep -q '^WHATSAPP_SECRETO=.\+' .env; then
  sed -i '/^WHATSAPP_SECRETO=/d' .env
  echo "WHATSAPP_SECRETO=$(openssl rand -hex 24)" >> .env
fi

if ! grep -q '^CLIMA_RELEVO_LLAVE=.\+' .env; then
  # La llave con que se identifica la máquina de relevo de IERSE (despliegue/relevo/).
  sed -i '/^CLIMA_RELEVO_LLAVE=/d' .env
  echo "CLIMA_RELEVO_LLAVE=$(openssl rand -hex 32)" >> .env
fi

echo "→ Levantando (las migraciones corren antes que la web)"
docker compose up -d

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

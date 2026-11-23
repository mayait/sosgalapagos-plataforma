#!/usr/bin/env bash
# SOS Galápagos · © 2026 Universidad San Francisco de Quito (USFQ) · Autor: Julián Maya <jamaya@usfq.edu.ec>
# Licencia Apache 2.0 (ver LICENSE y NOTICE): puede reutilizarse dando crédito.
#
# Actualiza el frente del sitio (Caddy y comentarios). Uso (en el servidor):
#   /opt/sosgalapagos-plataforma/despliegue/sitio/desplegar.sh
# La plataforma se despliega aparte con despliegue/produccion/desplegar.sh.
# No usa --remove-orphans: los contenedores de la antigua plataforma de coordinación quedan detenidos, no borrados.
set -euo pipefail
cd "$(dirname "$0")"
[ -f .env ] || { echo "Falta despliegue/sitio/.env (copiar de .env.example)"; exit 1; }
git -C ../.. pull --ff-only
docker compose up -d --build comentarios caddy
docker compose exec -T caddy caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile
docker compose ps

#!/bin/sh
# SOS Galápagos · © 2026 Universidad San Francisco de Quito (USFQ) · Autor: Julián Maya <jamaya@usfq.edu.ec>
# Licencia Apache 2.0 (ver LICENSE y NOTICE): puede reutilizarse dando crédito.
# Copia diaria de la base de la plataforma (reportes, clima, avisos) y de las fotos.
# La corre sosgalapagos-plataforma-respaldo.timer. Guarda las 14 más recientes.
set -eu
cd "$(dirname "$0")"
D=/var/lib/sosgalapagos-plataforma/respaldos
mkdir -p "$D"
chmod 700 "$D"
F="$D/plataforma-$(date -u +%F).sql.gz"
docker compose exec -T postgis sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" --no-owner' | gzip > "$F.tmp"
# Una copia vacía o cortada no reemplaza a la buena.
[ "$(stat -c %s "$F.tmp")" -gt 100000 ] && mv "$F.tmp" "$F"
docker run --rm -v sosgalapagos-plataforma_medios:/medios:ro -v "$D":/destino alpine tar -czf "/destino/fotos-$(date -u +%F).tar.gz" -C /medios . 2>/dev/null || true
ls -1t "$D"/plataforma-*.sql.gz | tail -n +15 | xargs -r rm -f
ls -1t "$D"/fotos-*.tar.gz 2>/dev/null | tail -n +15 | xargs -r rm -f

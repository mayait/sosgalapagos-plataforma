# PostgreSQL 16 con PostGIS 3, desde los paquetes de Debian (sirve en amd64 y arm64).
FROM postgres:16-bookworm
RUN apt-get update \
 && apt-get install -y --no-install-recommends postgresql-16-postgis-3 \
 && rm -rf /var/lib/apt/lists/*

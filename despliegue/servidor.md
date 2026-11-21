# Despliegue en el servidor (preparado, sin aplicar)

**Nada de esto se ha ejecutado.** Son los fragmentos listos para cuando Julián apruebe el primer despliegue. Solo añaden; no reemplazan ninguna ruta existente.

El `docker-compose.yml` y el `Caddyfile` de todo el servidor viven en `mayait/sosgalapagos`, carpeta `deploy/sosgalapagos/`. Los cambios van allí, con pull request.

## Servicios nuevos en `docker-compose.yml`

```yaml
  postgis:
    build: /opt/sosgalapagos-plataforma/despliegue/postgis
    restart: unless-stopped
    env_file: plataforma.env          # POSTGRES_USER, POSTGRES_PASSWORD, POSTGRES_DB
    volumes:
      - plataformabd:/var/lib/postgresql/data

  plataforma: &plataforma
    build:
      context: /opt/sosgalapagos-plataforma
      dockerfile: despliegue/Dockerfile
    restart: unless-stopped
    env_file: plataforma.env          # CLAVE_SECRETA, BD_*, ANFITRIONES, ORIGENES_CONFIABLES
    environment:
      - BD_ANFITRION=postgis
      - CLIMA_ESTADO=/srv/clima/datos/estado.json
      - CAPAS_URL=/mapas/datos/        # por confirmar con lo que publica /mapas
      - MEDIOS_DIR=/medios
    volumes:
      - plataformamedios:/medios
      - /srv/sosgalapagos-clima:/srv/clima:ro
    depends_on: [postgis]
    expose: ['8000']

  plataforma-trabajador:
    <<: *plataforma
    command: python manage.py db_worker

  plataforma-reloj:
    <<: *plataforma
    command: python manage.py reloj
```

Volúmenes nuevos: `plataformabd` y `plataformamedios`.

## Bloques nuevos en el `Caddyfile`

Van antes del `handle` final, que manda todo lo demás a la web actual.

```
	handle /mapa/* {
		reverse_proxy plataforma:8000
	}
	handle /api/* {
		reverse_proxy plataforma:8000
	}
	handle_path /medios/* {
		root * /srv/plataforma-medios
		file_server
	}
```

## Antes de desplegar

- [ ] Comprobar que la web actual no usa ya la ruta `/api/`.
- [ ] Medir la memoria libre del servidor (4 vCPU, 8 GB).
- [ ] Confirmar la URL pública del manifiesto de capas y de sus archivos.
- [ ] Añadir la base nueva y las fotos al respaldo diario.
- [ ] Correr `collectstatic` en la imagen y servir `/estaticos/` con WhiteNoise.
- [ ] La cabecera `Permissions-Policy` de Caddy dice hoy `camera=()`. No afecta al botón de foto del formulario, que usa la cámara del sistema, pero hay que comprobarlo en un teléfono.

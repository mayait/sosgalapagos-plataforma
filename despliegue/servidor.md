# Despliegue en el servidor

El mapa de riesgos corre en el mismo servidor que el sitio (152.44.45.89), detrás del mismo Caddy, en `https://sosgalapagos.org/riesgos/`.

**Solo añade.** Es un proyecto de Compose aparte del sitio y no reinicia nada de lo que ya corre. `/mapas`, `/clima` y la portada no se tocan.

```
Cloudflare ─► Caddy del sitio ─┬─ /mapas/  /clima/  /          lo de siempre
                               └─ /riesgos/*  ─► plataforma:8000   (este repo)
                                                 │
                              postgis · trabajador · reloj      proyecto «sosgalapagos-plataforma»
```

La plataforma lee, en solo lectura, tres cosas que ya publican otros: la lluvia de `/clima` (`/srv/sosgalapagos-clima`), el índice de informes en PDF de la portada (`/srv/sosgalapagos-descargas`) y las capas de `/mapas` (por la web).

Todo lo de la plataforma vive bajo `/riesgos/`: páginas, `/riesgos/api/`, `/riesgos/admin/`, estáticos y fotos. El sitio actual ya usa `/api` y `/admin`, así que no se comparten.

## 1. La primera vez

```bash
ssh root@152.44.45.89
git clone https://github.com/mayait/sosgalapagos-plataforma.git /opt/sosgalapagos-plataforma
/opt/sosgalapagos-plataforma/despliegue/produccion/desplegar.sh   # crea el .env con claves nuevas, construye y levanta
```

## 2. La ruta en Caddy

Está en `mayait/sosgalapagos`, `deploy/sosgalapagos/Caddyfile`, antes del `handle` final:

```
	redir /riesgos /riesgos/ permanent
	handle /riesgos/* {
		reverse_proxy plataforma:8000
	}
```

Para aplicarla **sin reiniciar Caddy** (un reinicio corta todo el sitio unos segundos):

```bash
cd /opt/sosgalapagos && git pull --ff-only
cd deploy/sosgalapagos
docker compose cp Caddyfile caddy:/tmp/Caddyfile
docker compose exec -T caddy caddy validate --config /tmp/Caddyfile --adapter caddyfile   # si falla, no seguir
docker compose exec -T caddy caddy reload   --config /tmp/Caddyfile --adapter caddyfile
```

El archivo del repo queda igual que el que está cargado, así que el próximo reinicio de Caddy no cambia nada.

## 3. Actualizar

```bash
/opt/sosgalapagos-plataforma/despliegue/produccion/desplegar.sh
```

## 4. Comprobar

```bash
curl -sI https://sosgalapagos.org/riesgos/ | head -1
curl -s  https://sosgalapagos.org/riesgos/api/reportes/vivos.geojson | head -c 200
curl -sI https://sosgalapagos.org/mapas/ | head -1      # sigue igual
curl -sI https://sosgalapagos.org/clima/ | head -1      # sigue igual
cd /opt/sosgalapagos-plataforma/despliegue/produccion && docker compose ps
```

## 5. Volver atrás

- **Quitar la ruta:** revertir el commit del `Caddyfile` y repetir el paso 2. `/riesgos/` deja de responder y lo demás sigue igual.
- **Parar la plataforma:** `docker compose stop` en `despliegue/produccion`. Los datos quedan en los volúmenes `bd` y `medios`. No se borra nada.

## 6. Cuenta de coordinación

```bash
cd /opt/sosgalapagos-plataforma/despliegue/produccion
docker compose exec plataforma python manage.py createsuperuser
```

Se entra en `https://sosgalapagos.org/riesgos/admin/`. Ahí se revisan y publican las fotos y notas de los vecinos.

## Pendiente

- [ ] Sumar la base (`bd`) y las fotos (`medios`) al respaldo diario del servidor.
- [ ] Publicar las teselas de cota del 3D con `/mapas` (PR 101 de `sosgalapagos-datos`). Mientras tanto el 3D usa un relieve de respaldo.
- [ ] Marcar `version.txt` de `/mapas` como «no guardar» en Caddy, para que el mapa se entere antes de una publicación nueva.

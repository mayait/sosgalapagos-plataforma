# El frente del sitio: Caddy y comentarios

Aquí están el **Caddy** de `sosgalapagos.org` y el pequeño servicio de **comentarios** de `/estudios/`. Desde el 23-nov-2026 viven en este repositorio; antes estaban en `mayait/sosgalapagos/deploy/sosgalapagos/`, el fork de ResponseGrid, que se retiró y se archivó.

## Qué sirve cada ruta

| Ruta | Quién la sirve |
|---|---|
| `/`, `/privacidad`, `/robots.txt`, `/sitemap.xml` y todo lo que no esté abajo | La plataforma (Django, `despliegue/produccion/`) |
| `/riesgos/…` | La plataforma |
| `/mapas/…` | Carpeta `/srv/sosgalapagos-mapas` (la publica `sosgalapagos-datos`) |
| `/clima/` | Carpeta `/srv/sosgalapagos-clima`: la página y los tres JSON del panel |
| `/estudios/…` y `/estudios/api/…` | Carpeta `/srv/sosgalapagos-estudios` y el servicio `comentarios` |
| `/descargas/*.pdf\|jpg\|png` | Carpeta `/srv/sosgalapagos-descargas` |
| `/usfq/` y otros privados | Archivos `/srv/sosgalapagos-privado/caddy/*.caddy` del servidor |
| `/backend/…` | Responde 410: la API de la plataforma de coordinación anterior se retiró |

## Desplegar

```bash
# en el servidor, después de desplegar la plataforma si cambió
/opt/sosgalapagos-plataforma/despliegue/sitio/desplegar.sh
```

- El proyecto de Compose se llama `sosgalapagos`, igual que antes, así que se reusan los volúmenes (certificados de Caddy y comentarios) y la red `sosgalapagos_default`, a la que se une la plataforma.
- **Nunca** se usa `--remove-orphans`: los contenedores viejos de ResponseGrid (`postgres`, `redis`, `api`, `web`) quedan detenidos, no borrados. Su base tiene un respaldo en `/root/respaldo-responsegrid/`.
- Antes de desplegar, avisa a las otras sesiones y comprueba que no haya otro despliegue en curso.

## Cortafuegos

`firewall-cloudflare.sh` deja los puertos 80 y 443 abiertos solo para Cloudflare. Corre como servicio `sosgalapagos-firewall`.

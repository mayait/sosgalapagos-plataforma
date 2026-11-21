# Instrucciones para agentes y colaboradores

Plataforma de reportes de riesgo de SOS Galápagos: un mapa único donde la gente reporta lugares de peligro con fecha, y donde los reportes se retiran solos. Lee primero [`README.md`](README.md) y [`docs/plan-tecnico.md`](docs/plan-tecnico.md).

**Estás en:** `sosgalapagos-plataforma`, el mapa de riesgos de `sosgalapagos.org/riesgos/`. Desde el 21-nov-2026 es el único mapa del sitio. El árbol de los seis repositorios está al final de este archivo.

## Reglas duras

1. **No se toca producción ni el servidor sin aprobación explícita de Julián.** Subir a `main` no publica nada.
2. **Nunca se borran archivos, datos ni contenedores.** Lo que se descarta se mueve a `Archivo/`. Un reporte cerrado tampoco se borra: queda en el archivo.
3. **No se rompen los datos de `/mapas/…` ni `/clima`.** Este proyecto solo lee lo que publican. `/mapas/` ya no tiene visor (su página redirige aquí), pero su carpeta de datos no se da de baja nunca: este mapa lee todo de ahí.
4. **Las capas conservan los principios de `/mapas`: toda capa se puede encender, apagar y descargar** (Shapefile y GeoJSON). El panel Capas lee el `capas.json` y el `descargas.json` que publica `/mapas`; no se mantiene una lista de capas aparte. Una capa nueva se añade en el repo de datos y aparece sola aquí.
5. **No se copia código de ResponseGrid** (`mayait/sosgalapagos`, AGPL-3.0). Este proyecto es Apache 2.0. El visual se rehace desde [`docs/visual-mapa.md`](docs/visual-mapa.md).
6. **Privacidad:**
   - Ningún dato personal público. Nunca nombres de menores ni cédulas.
   - Las fotos se guardan sin metadatos (`reportes/fotos.py`).
   - Los teléfonos nunca en claro: solo un resumen con clave.
   - La foto y la nota de un vecino no se publican hasta que coordinación las revise.
7. **El mapa nunca dice «zona segura».** Donde no hay reportes dice «sin reportes activos». Hay una prueba que lo vigila.
8. **Se dice «refugio», nunca «albergue».**
9. **Repositorio público.** Sin secretos, sin endpoints de las fuentes de clima y nada de los repositorios privados.
10. **Se trabaja en ramas con pull request.**

## Convenciones

- **Idioma:** español en el código, los comentarios, los commits y los textos visibles. Los nombres que exige Django (`models.py`, `admin.py`, `migrations/`) se quedan como están.
- **Commits:** `tipo(ámbito): descripción`, sin líneas `Co-Authored-By`. Los agentes de Julián usan `Julian Maya <1101119+mayait@users.noreply.github.com>`.
- **Reglas de vida del reporte:** toda la lógica está en `reportes/reglas.py`, con pruebas en `reportes/pruebas/`. Las vistas y la API solo llaman. Un cambio de regla lleva su prueba.
- **Umbrales:** en `plataforma/ajustes.py`, marcados como preliminares.
- **Sin paso de compilación.** El JavaScript va tal cual en `estaticos/mapa/`. En las plantillas se enlaza con `{% propio 'mapa/…' %}`, que le pone la versión a la URL; con `{% static %}` el navegador puede quedarse con una copia vieja. Las librerías de terceros están en `estaticos/terceros/` con versión fija; no se cargan desde un CDN.
- **Marca:** sistema USFQ «WE WANT MORE». Solo rojo `#E11B22`, negro y blanco; fondo blanco y sin modo oscuro. El ámbar y el gris de los pines son señales del mapa, no de marca. La firma «MORE HUMANS, MORE DRAGONS.» va discreta, al pie. El logotipo de la USFQ aparece una sola vez, abajo, pequeño y tenue; no va en la cabecera.
- **El contenido manda en la hoja.** Lo primero que se ve al tocar un reporte es el reporte, empezando por sus fotos. «Reportar» es un botón pequeño junto al asa, no una barra.
- **Teléfono primero:** cada cambio de interfaz se revisa a 360 y 390 px de ancho, y en la hoja inferior se comprueba que se puede bajar hasta el último elemento. Los botones miden al menos 44 px y nada debe provocar desplazamiento horizontal.
- **Horas:** en la base, UTC. En pantalla, hora de Galápagos (UTC−6).
- **En la Mac no hay Docker:** se usa `container` (Apple). Ver `despliegue/local.sh`.
- **Las capas cambian en vivo.** Otro equipo publica modelos y capas en `/mapas` varias veces al día. Toda dirección de capa, tesela o descarga pasa por `conV()` (`estaticos/mapa/capas.js`), que le pone la versión publicada. Nunca se escribe una dirección de `/mapas` sin versión.
- **Después de cada publicación de `/mapas`:** `despliegue/local.sh revisar_capas`. Si avisa de algo nuevo, se enseña a `estaticos/mapa/capas.js` y se añade a la lista de la orden.
- **Lecciones:** los errores y las decisiones se anotan en [`docs/lecciones.md`](docs/lecciones.md).

## Mapa rápido

| Quiero… | Voy a… |
|---|---|
| Cambiar un plazo, un duplicado o una confirmación | `reportes/reglas.py` y `plataforma/ajustes.py` |
| Añadir o cambiar un tipo de aviso (peligro, algo bueno, donar o colaborar) | El admin (`/riesgos/admin/`), no el código |
| Tocar el informe (línea del tiempo y lluvia) | `estaticos/mapa/informe.js` y `plantillas/reportes/informe.html` |
| Saber cómo se retiró el visor de `/mapas` y cómo volver atrás | `docs/plan-baja-mapas.md` |
| Tocar el buscador o «Mis puntos» | `estaticos/mapa/buscar.js` |
| Desplegar o actualizar el servidor | `despliegue/servidor.md` y `despliegue/produccion/desplegar.sh` |
| Tocar el formulario | `plantillas/reportes/reportar.html` y `estaticos/mapa/reportar.js` |
| Tocar los pines o el desteñido | `estaticos/mapa/mapa.js` |
| Tocar el panel Capas | `estaticos/mapa/capas.js`. Las capas, sus estilos y sus descargas vienen de lo que publica `/mapas` |
| Añadir o cambiar una capa | El repo `sosgalapagos-datos` (`geodatos/`), no este |
| Cambiar el mapa base | `estaticos/mapa/base.js` |
| Ver qué falta | [`docs/plan-tecnico.md`](docs/plan-tecnico.md), sección de fases |

## Árbol de repositorios de SOS Galápagos

<!-- arbol-repos:inicio -->
> **Este bloque es idéntico en los seis repositorios** (en su `AGENTS.md`). Si cambias algo, cámbialo en los seis. Última revisión: 2026-11-21 (el mapa único es `/riesgos/`; el visor de `/mapas` se retiró).

SOS Galápagos no es un solo repositorio, son seis. No hay organización de GitHub: todos están en la cuenta `mayait`. En la Mac de Julián cada uno se clona en `~/dev/<nombre>`.

| Repositorio | Visibilidad | Qué contiene | Qué publica |
|---|---|---|---|
| [`sosgalapagos`](https://github.com/mayait/sosgalapagos) | público | La plataforma de coordinación: web y API. Es un fork de `GlobalEmergency/ResponseGrid`. También guarda el Caddy y el Docker Compose de **todo** el servidor (`deploy/sosgalapagos/`). | `sosgalapagos.org/` y `/backend` |
| [`sosgalapagos-datos`](https://github.com/mayait/sosgalapagos-datos) | público | Geodatos, clima, estudios de riesgo y modelos. Su carpeta `servidores/` es el índice de qué corre dónde. | Los datos de `/mapas/…` (capas y descargas, sin visor) y `/clima/` |
| [`sosgalapagos-plataforma`](https://github.com/mayait/sosgalapagos-plataforma) | público | El mapa de riesgos: reportes ciudadanos con vencimiento sobre las capas de riesgo, buscador, descargas e informe. Django + PostGIS, Apache 2.0. Es el único mapa del sitio desde el 21-nov-2026. | `/riesgos/` |
| [`sosgalapagos-bot`](https://github.com/mayait/sosgalapagos-bot) | **privado** | Asistente de WhatsApp: lee grupos, clasifica mensajes y crea pedidos en la plataforma. | Nada en la web; es un servicio systemd aparte (ver su `LEEME.md`) |
| [`RESPONSEGRID_GALAPAGOS`](https://github.com/mayait/RESPONSEGRID_GALAPAGOS) | público | Carpeta de trabajo local: arranque en la Mac y datos semilla. Clona `sosgalapagos` dentro de `app/`, que git ignora. Conserva la historia de geodatos hasta el 2-nov-2026. | Nada |
| [`estudiantes-riesgo-nino`](https://github.com/mayait/estudiantes-riesgo-nino) | **privado** | Viviendas de estudiantes de USFQ Galápagos cruzadas con el riesgo de inundación. Tiene datos personales. | `/usfq/`, con contraseña |

```
                         sosgalapagos.org (un solo servidor, detrás de Cloudflare)
                                          │
              Caddy + Docker Compose: sosgalapagos → deploy/sosgalapagos/
        ┌──────────────┬──────────────────┬──────────────────┬───────────────────────┐
        │ /  /backend  │ /riesgos/        │ /mapas/… /clima/ │ /usfq/ (contraseña)   │
        ▼              ▼                  ▼                  ▼                       │
   sosgalapagos   sosgalapagos-      sosgalapagos-datos   estudiantes-riesgo-nino    │
   (portada y     plataforma         (datos y modelos)    (privado)                  │
    coordinación) (mapa de riesgos)       │                    ▲                     │
        ▲              ▲  lee capas.json, │ capas y descargas  │ capas de geodatos   │
        │              └──────────────────┴────────────────────┘                     │
        │ API pública                                                                │
   sosgalapagos-bot (privado, servicio aparte) ◄─────────────────────────────────────┘

   /mapas/ ya no tiene visor: la página redirige a /riesgos/. Sus datos se siguen sirviendo.
   RESPONSEGRID_GALAPAGOS/app/  =  otro clon local de sosgalapagos
```

### Cómo dependen unos de otros

1. **Las rutas del servidor se definen en `sosgalapagos`.** El `Caddyfile` y el `docker-compose.yml` de `deploy/sosgalapagos/` sirven la plataforma, pasan `/riesgos/` al contenedor de `sosgalapagos-plataforma` (Compose aparte, en la misma red) y montan las carpetas que publican los demás: `/srv/sosgalapagos-mapas` y `/srv/sosgalapagos-clima` (de `sosgalapagos-datos`) y `/srv/sosgalapagos-privado` (de `estudiantes-riesgo-nino`). Una ruta nueva se añade allí y se despliega con `deploy/sosgalapagos/deploy.sh`, aunque el contenido venga de otro repositorio.
2. **Las capas del mapa de la plataforma se generan en `sosgalapagos-datos`** (`geodatos/export/`) y se sirven desde `sosgalapagos` (`apps/web/public/capas/galapagos-2026/`), dentro de la imagen web. Para que un cambio de capa llegue a la plataforma hay que copiarla y desplegar la app. La carpeta `geodatos/` de `sosgalapagos` no recibe cambios desde el 1-nov-2026: el proceso vivo está en `sosgalapagos-datos`.
3. **El bot habla con la plataforma solo por su API pública** (`https://sosgalapagos.org/backend`, cliente en `src/responsegrid.ts`). No toca la base de datos ni el código. Si cambias un endpoint o un DTO de la API en `sosgalapagos`, revisa ese cliente.
4. **`estudiantes-riesgo-nino` lee las capas de `sosgalapagos-datos`.** Su ruta por defecto apunta a la ubicación antigua, que ya no existe: se corre con `GEODATOS=~/dev/sosgalapagos-datos/geodatos`.
5. **`RESPONSEGRID_GALAPAGOS/app/` es un clon de `sosgalapagos`**, no una carpeta del repositorio que lo contiene. Lo que se hace commit allí va a `sosgalapagos`. Como hay dos clones locales del mismo repositorio (`~/dev/sosgalapagos` y `~/dev/RESPONSEGRID_GALAPAGOS/app`), haz `git pull` antes de trabajar en cualquiera.
6. **El mapa de `/riesgos/` lee lo que `sosgalapagos-datos` publica bajo `/mapas/`**: el manifiesto (`capas.json`), las capas, las teselas, `descargas.json` y `version.txt`. Una capa nueva se añade en `sosgalapagos-datos` y aparece sola en `/riesgos/`. **Nunca se da de baja la carpeta de `/mapas/`**: solo se retiró su página, que redirige a `/riesgos/`.

### Dónde va cada cambio

| Quiero cambiar… | Repositorio |
|---|---|
| La web, la API, la portada, formularios o la marca | `sosgalapagos` |
| Una ruta, un contenedor o el Caddy del servidor | `sosgalapagos` → `deploy/sosgalapagos/` |
| El mapa de riesgos: reportes, buscador, panel de capas, informe, página de descargas | `sosgalapagos-plataforma` |
| Una capa, un estudio, un modelo, el orden y los colores de las capas | `sosgalapagos-datos` → `geodatos/` |
| El panel de `/clima/`, el recolector, el pronóstico | `sosgalapagos-datos` → `clima/` |
| Qué servicio corre dónde y cómo se publica | `sosgalapagos-datos` → `servidores/README.md` |
| Cómo lee, responde o modera el asistente de WhatsApp | `sosgalapagos-bot` |
| El arranque local o los datos semilla | `RESPONSEGRID_GALAPAGOS` → `galapagos/` |
| El mapa o el informe de estudiantes en riesgo | `estudiantes-riesgo-nino` |

### Reglas que cruzan repositorios

- **No se copia código de `sosgalapagos` (AGPL-3.0) a `sosgalapagos-plataforma` (Apache 2.0).**
- **Nada de un repositorio privado pasa a uno público.** Ni los datos personales de `estudiantes-riesgo-nino` ni la lógica de detección de estafas del bot (`src/analista.ts`).
- **Cada repositorio tiene sus propias reglas de commit y de ramas.** Léelas en su `AGENTS.md` o `LEEME.md` antes de hacer commit. Dos que cambian: en `sosgalapagos` los commits van como «IA Humana» y sin `Co-Authored-By`; en `sosgalapagos-datos` y en `sosgalapagos-plataforma` se trabaja en una rama con pull request, también sin `Co-Authored-By`.
- **Desplegar es un paso aparte y manual.** Subir a `main` no publica nada en `sosgalapagos.org`. No despliegues si no te lo piden.
<!-- arbol-repos:fin -->

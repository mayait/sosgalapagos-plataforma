# Instrucciones para agentes y colaboradores

Plataforma de reportes de riesgo de SOS Galápagos: un mapa único donde la gente reporta lugares de peligro con fecha, y donde los reportes se retiran solos. Lee primero [`README.md`](README.md) y [`docs/plan-tecnico.md`](docs/plan-tecnico.md).

**Estás en:** `sosgalapagos-plataforma`, el mapa de riesgos de `sosgalapagos.org/riesgos/`. Desde el 21-nov-2026 es el único mapa del sitio. El árbol de los seis repositorios está al final de este archivo.

## Reglas duras

1. **No se toca producción ni el servidor sin aprobación explícita de Julián.** Subir a `main` no publica nada.
2. **Nunca se borran archivos, datos ni contenedores.** Lo que se descarta se mueve a `Archivo/`. Un reporte cerrado tampoco se borra: queda en el archivo.
3. **No se rompen los datos de `/mapas/…` ni `/clima`.** Este proyecto solo lee lo que publican. `/mapas/` ya no tiene visor (su página redirige aquí), pero su carpeta de datos no se da de baja nunca: este mapa lee todo de ahí.
4. **Las capas conservan los principios de `/mapas`: toda capa se puede encender, apagar y descargar** (Shapefile y GeoJSON). El panel Capas lee el `capas.json` y el `descargas.json` que publica `/mapas`; no se mantiene una lista de capas aparte. Una capa nueva se añade en el repo de datos y aparece sola aquí.
5. **No se copia código de ResponseGrid** (`mayait/sosgalapagos`, AGPL-3.0). Este proyecto es Apache 2.0 desde el 23-nov-2026 ([`LICENSE`](LICENSE) y [`NOTICE`](NOTICE)) y la AGPL no se puede mezclar con ella sin volverlo AGPL: cada archivo de código propio empieza con el aviso de autoría (USFQ · SOS Galápagos · Julián Maya) y ese aviso no se quita. Los datos y modelos propios van bajo CC BY 4.0 y los de terceros conservan su licencia ([`LICENCIA-DATOS.md`](LICENCIA-DATOS.md)). El visual se rehace desde [`docs/visual-mapa.md`](docs/visual-mapa.md).
6. **Privacidad:**
   - Ningún dato personal público. Nunca nombres de menores ni cédulas.
   - Las fotos se guardan sin metadatos (`reportes/fotos.py`).
   - Los teléfonos nunca en claro: solo un resumen con clave.
   - Todo lo que la gente publica (punto, foto y nota) sale al instante, sin pasar por el admin (decisión de Julián, 23-nov-2026). Coordinación solo entra para corregir u ocultar. En la nota, los números de 7 o más dígitos (teléfonos, cédulas) se ocultan solos.
7. **El mapa nunca dice «zona segura».** Donde no hay reportes dice «sin reportes activos». Hay una prueba que lo vigila.
8. **Se dice «refugio», nunca «albergue».**
9. **Repositorio público.** Sin secretos, sin endpoints de las fuentes de clima y nada de los repositorios privados.
10. **Se trabaja en ramas con pull request.**
11. **«No oficial» se dice una vez por página.**
    - El aviso general va en el menú del sitio (`reportes/menu.py`, `/riesgos/app.js`), y los documentos oficiales en su propia sección.
    - Sin sellos ni frases de «no oficial» en cada tarjeta. Solo las advertencias que informan (cuánto subestima un modelo, qué no ve el satélite).
    - Lo que sale de la página (mensajes de WhatsApp, PDF, descargas) sí lo dice.
    - Decisión de Julián, 23-nov-2026.

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
| Tocar la animación de lluvia de la portada (próximas 24 horas) | `LluviaMapa.reel` en `estaticos/mapa/lluvia-mapa.js` (el motor que comparte con `/clima/`), `estaticos/portada/portada.js` y `plantillas/portada/portada.html`. Los datos son el recorte `?horas=24` de `/riesgos/api/clima/lluvia-mapa.json` |
| Tocar WhatsApp (filtro, modelo, conversación) | `entradas/` y `docs/whatsapp.md`. Se prueba con `despliegue/local.sh whatsapp_probar` |
| Cambiar de modelo de lenguaje (Anthropic o Gemini) | La variable `IA_MODELO`; nada de código |
| Tocar «Ayúdanos a ubicar» (lista, mapa, regla de coincidencia) | `reportes/reglas.py` (`proponer_ubicacion`), `UBICAR_*` en los ajustes, `plantillas/reportes/ubicar*.html` y `estaticos/mapa/ubicar.js` |
| Tocar la entrada horaria de los grupos de WhatsApp (descarga, Jev, fotogramas) | `despliegue/ingesta/` (corre en la Mac) y `entradas/ingesta.py` (lo recibe el servidor) |
| Tocar los puntos | `reportes/reglas.py` (`sumar_puntos`) y `PUNTOS` en los ajustes |
| Tocar la instalación de la app o los avisos | `estaticos/mapa/app.js`, `reportes/avisos.py` y `plantillas/reportes/sw.js` |
| Desplegar o actualizar el servidor | `despliegue/servidor.md` y `despliegue/produccion/desplegar.sh` |
| Subir un documento oficial (PDF o imagen) y avisar a los teléfonos | `manage.py oficial_agregar … --aviso "qué pasó"` (`reportes/management/commands/oficial_agregar.py`) |
| Tocar el visor de documentos (adonde llevan los avisos; tiene botón de volver) | `plantillas/reportes/documento.html`, `estaticos/mapa/visor.js` y las vistas `oficial` y `boletin` |
| Tocar el formulario | `plantillas/reportes/reportar.html` y `estaticos/mapa/reportar.js` |
| Tocar los pines o el desteñido | `estaticos/mapa/mapa.js` |
| Tocar el panel Capas | `estaticos/mapa/capas.js`. Las capas, sus estilos y sus descargas vienen de lo que publica `/mapas` |
| Añadir o cambiar una capa | El repo `sosgalapagos-datos` (`geodatos/`), no este |
| Cambiar el mapa base | `estaticos/mapa/base.js` |
| Ver qué falta | [`docs/plan-tecnico.md`](docs/plan-tecnico.md), sección de fases |

## Árbol de repositorios de SOS Galápagos

<!-- arbol-repos:inicio -->
> **Este bloque es idéntico en los repositorios activos** (en su `AGENTS.md`). Si cambias algo, cámbialo en todos. Última revisión: 2026-11-24 (ResponseGrid retirado: la portada «/» y el Caddy pasan a `sosgalapagos-plataforma`; `mayait/sosgalapagos` queda archivado. Apache 2.0 y CC BY 4.0 en `sosgalapagos-datos` y `sosgalapagos-plataforma`; el mapa único es `/riesgos/`; todo el clima corre en `sosgalapagos-plataforma`).

SOS Galápagos son varios repositorios, todos en la cuenta `mayait` de GitHub (no hay organización). En la Mac de Julián cada uno se clona en `~/dev/<nombre>`.

| Repositorio | Visibilidad | Qué contiene | Qué publica |
|---|---|---|---|
| [`sosgalapagos-plataforma`](https://github.com/mayait/sosgalapagos-plataforma) | público | **El sitio**: la portada, el mapa de riesgos (reportes ciudadanos con vencimiento sobre las capas de riesgo, buscador, descargas, línea del tiempo), la privacidad y todo el clima (un solo stack desde el 22-nov-2026). Django + PostGIS. También guarda el **Caddy** del servidor (`despliegue/sitio/`). Código Apache 2.0; datos propios CC BY 4.0. | `sosgalapagos.org/`, `/riesgos/`, `/privacidad` |
| [`sosgalapagos-datos`](https://github.com/mayait/sosgalapagos-datos) | público | Geodatos, estudios de riesgo, modelos y el panel de `/clima/`. Su carpeta `servidores/` es el índice de qué corre dónde. Código Apache 2.0; datos propios CC BY 4.0. | Los datos de `/mapas/…` (capas y descargas, sin visor), `/estudios/`, `/descargas/` y la página de `/clima/` |
| [`estudiantes-riesgo-nino`](https://github.com/mayait/estudiantes-riesgo-nino) | **privado** | Viviendas de estudiantes de USFQ Galápagos cruzadas con el riesgo de inundación. Tiene datos personales. | `/usfq/`, con contraseña |
| [`sosgalapagos-bot`](https://github.com/mayait/sosgalapagos-bot) | **privado** | Asistente de WhatsApp de la etapa anterior: creaba pedidos en la API de ResponseGrid, que ya no existe. No corre. El WhatsApp vivo está en la plataforma (`entradas/`). | Nada |
| [`sosgalapagos`](https://github.com/mayait/sosgalapagos) | público, **archivado** | El fork de ResponseGrid (AGPL-3.0): la antigua plataforma de coordinación. Retirado el 24-nov-2026; sus contenedores están detenidos y su base, respaldada. | Nada (`/backend` responde 410) |
| [`RESPONSEGRID_GALAPAGOS`](https://github.com/mayait/RESPONSEGRID_GALAPAGOS) | público | Carpeta de trabajo local de la etapa anterior. Conserva la historia de geodatos hasta el 2-nov-2026. | Nada |

```
                    sosgalapagos.org (un solo servidor, detrás de Cloudflare)
                                     │
        Caddy: sosgalapagos-plataforma → despliegue/sitio/ (proyecto Compose «sosgalapagos»)
     ┌─────────────────────────────┬───────────────────────────────┬──────────────────────┐
     │ /  /riesgos/  /privacidad   │ /mapas/… /clima/ /estudios/   │ /usfq/ (contraseña)  │
     ▼                             │ /descargas/                   ▼                      │
 sosgalapagos-plataforma           ▼                         estudiantes-riesgo-nino     │
 (portada, mapa, clima)      sosgalapagos-datos              (privado)                   │
     ▲  lee capas.json,      (datos y modelos)                    ▲                      │
     └───────────────────────────┴────────────────────────────────┘ capas de geodatos   │
```

### Cómo dependen unos de otros

1. **Las rutas del servidor se definen en `sosgalapagos-plataforma`** (`despliegue/sitio/Caddyfile`). Caddy pasa «/», `/riesgos/` y `/privacidad` a la plataforma, y sirve las carpetas que publican los demás: `/srv/sosgalapagos-mapas`, `/srv/sosgalapagos-clima`, `/srv/sosgalapagos-estudios` y `/srv/sosgalapagos-descargas` (de `sosgalapagos-datos`) y `/srv/sosgalapagos-privado` (de `estudiantes-riesgo-nino`). Una ruta nueva se añade allí y se despliega con `despliegue/sitio/desplegar.sh`. **Nunca** con `--remove-orphans`: los contenedores de ResponseGrid quedan detenidos, no borrados.
2. **El mapa de `/riesgos/` lee lo que `sosgalapagos-datos` publica bajo `/mapas/`**: el manifiesto (`capas.json`), las capas, las teselas, `descargas.json` y `version.txt`. Una capa nueva se añade en `sosgalapagos-datos` y aparece sola en `/riesgos/`. **Nunca se da de baja la carpeta de `/mapas/`**: solo se retiró su página, que redirige a `/riesgos/`.
3. **`estudiantes-riesgo-nino` lee las capas de `sosgalapagos-datos`.** Se corre con `GEODATOS=~/dev/sosgalapagos-datos/geodatos`.
4. **El panel de `/clima/` es una página de `sosgalapagos-datos`**, pero sus datos, su código JS y sus APIs los sirve la plataforma (`/riesgos/api/clima/…`, `/riesgos/estaticos/mapa/…`).

### Dónde va cada cambio

| Quiero cambiar… | Repositorio |
|---|---|
| La portada, la privacidad, el menú del sitio o la marca | `sosgalapagos-plataforma` |
| El mapa de riesgos: reportes, buscador, panel de capas, línea del tiempo, página de descargas | `sosgalapagos-plataforma` |
| Una ruta o el Caddy del servidor | `sosgalapagos-plataforma` → `despliegue/sitio/` |
| Las fuentes de clima, el nivel de lluvia, el pronóstico, las mareas, el satélite | `sosgalapagos-plataforma` → `clima/` |
| Una capa, un estudio, un modelo, el orden y los colores de las capas | `sosgalapagos-datos` → `geodatos/` |
| La página del panel de `/clima/` | `sosgalapagos-datos` → `clima/web/` |
| Qué servicio corre dónde y cómo se publica | `sosgalapagos-datos` → `servidores/README.md` |
| El mapa o el informe de estudiantes en riesgo | `estudiantes-riesgo-nino` |

### Reglas que cruzan repositorios

- **No se copia código de `sosgalapagos` (AGPL-3.0, archivado) a ningún otro repositorio.** La AGPL obligaría a publicar el otro bajo AGPL.
- **Nada de un repositorio privado pasa a uno público.** Ni los datos personales de `estudiantes-riesgo-nino` ni la lógica de detección de estafas del bot (`src/analista.ts`).
- **Licencias.**
  - `sosgalapagos-datos` y `sosgalapagos-plataforma`: desde el 23-nov-2026, el código va bajo Apache 2.0 (con `NOTICE`) y lo propio que no es código, bajo CC BY 4.0, con crédito a «SOS Galápagos · Universidad San Francisco de Quito (USFQ) · Julián Maya <jamaya@usfq.edu.ec>». Cada archivo de código lleva su aviso de autoría. Del 22 al 23-nov-2026 tuvieron derechos reservados y CC BY-NC-ND 4.0.
  - Los datos de terceros conservan la licencia de su fuente.
  - `sosgalapagos` sigue siendo AGPL-3.0 y está archivado.
- **En `sosgalapagos-datos` y `sosgalapagos-plataforma` se trabaja en una rama con pull request**, sin `Co-Authored-By`.
- **Desplegar es un paso aparte y manual.** Subir a `main` no publica nada en `sosgalapagos.org`. No despliegues si no te lo piden, y avisa a las otras sesiones antes.
<!-- arbol-repos:fin -->

# Lecciones y decisiones

Registro corto de errores y decisiones, para no repetirlos. Lo más nuevo va arriba. Cada entrada dice qué pasó, por qué importa y qué se hace distinto.

## 2026-11-21 · Fase 1

- **Un service worker que sirve primero lo guardado esconde los cambios.** Al corregir el CSS, el navegador siguió mostrando el archivo viejo. *Qué se hace:* el código propio (`estaticos/mapa/`) va primero a la red; solo las librerías, el mapa base, la marca y las capas se sirven primero desde lo guardado. Al cambiar esa lista se sube `VERSION` en `plantillas/reportes/sw.js`.
- **En CSS, `display: flex` le gana al atributo `hidden`.** El panel Capas aparecía abierto aunque tenía `hidden`. *Qué se hace:* regla global `[hidden] { display: none !important; }`.
- **El mapa base de Protomaps trae tiendas y restaurantes.** Tapaban los reportes. *Qué se hace:* se quitan las capas `pois` del estilo (`estaticos/mapa/base.js`).
- **Django niega por defecto que la página se cargue en un marco.** Rompía la revisión de la vista de escritorio y difería de la cabecera `SAMEORIGIN` que ya pone Caddy. *Qué se hace:* `X_FRAME_OPTIONS = "SAMEORIGIN"`.
- **Debian 12 trae GDAL 3.6 y Django avisa que es viejo.** *Qué se hace:* la imagen usa Debian 13 (`python:3.12-slim-trixie`), igual que el servidor.
- **Con `container` (Apple) no hay nombres entre contenedores.** La web no encuentra a la base por nombre. *Qué se hace:* `despliegue/local.sh` lee la IP de la base con `container inspect` cada vez.
- **Las peticiones de Python a `sosgalapagos.org` sin `User-Agent` no traían el JSON de clima.** *Qué se hace:* en la Mac se pide con un `User-Agent` propio; en el servidor se lee el archivo directamente.
- **«Tres toques» son tres decisiones más el envío.** Foto, tipo y profundidad son un toque cada uno; la última pantalla confirma el lugar y envía. La gravedad se propone sola según la profundidad, y «peligro de vida» solo la elige la persona.
- **El desteñido no depende del servidor.** El GeoJSON lleva `visto` y `vence` en segundos; el teléfono calcula la edad cada minuto. Así el pin se destiñe aunque no haya señal.

## 2026-11-21 · Antes de la fase 1

- **Los nombres de paquetes del encargo no bastan: hay que mirar la versión y la fecha.** Django 6 no trae backend de tareas en base de datos (está en `django-tasks-db`, que aún no declara Django 6.1). `django-ninja-spatial` existe pero nació en mayo de 2026 y nadie lo usa. MapLibre 6 quitó el script clásico y exige WebGL2. *Qué se hace:* se arranca con Django 6.0, django-ninja con `geojson-pydantic` y MapLibre 5.24, y las versiones quedan fijas en `pyproject.toml` y en `estaticos/terceros/`.
- **El feed CAP del INAMHI se filtra por polígono.** Una alerta rotulada «Galápagos» traía el polígono en el continente. *Qué se hace:* se cruza el polígono con el archipiélago y se ignora el nombre del área.
- **El Postgres de producción no tiene PostGIS.** *Qué se hace:* contenedor y volumen nuevos para la plataforma; el Postgres de ResponseGrid no se toca.

- **El encargo describe el mapa deseado, no el que existe.** El encargo pedía replicar «base gris claro» y «pantalla completa en móvil». En producción la base por defecto es Calles a color y el mapa en el teléfono es una franja del 35 % del alto. *Qué se hace:* se mira siempre el sitio en producción antes de dar por cierto lo que dice un encargo, y la diferencia queda escrita en `visual-mapa.md`.
- **El manifiesto de capas tiene dos versiones.** `mapas-galapagos/datos/capas.json` (repo de datos) trae la base «Claro» por defecto. El que sirve la plataforma en `/capas/galapagos-2026/capas.json` no la trae y ordena los grupos distinto. *Qué se hace:* el mapa nuevo lee un solo manifiesto, generado en el repo de datos.
- **Se dice «refugio», nunca «albergue».** Es regla del repo de datos (`AGENTS.md`, `CONTRIBUIR.md`). El encargo decía «albergues». *Qué se hace:* «refugio» en toda la interfaz, el código y los datos.
- **El navegador de escritorio no se encoge a ancho de teléfono.** Cambiar el tamaño de la ventana no bajó de unos 2 000 px. *Qué se hace:* para capturas de teléfono se carga la página dentro de un marco de 390 px del mismo origen. Esto no reemplaza la prueba en un Android real de gama baja.
- **No se copia código de ResponseGrid.** Es AGPL-3.0 y este proyecto es Apache 2.0. *Qué se hace:* el visual se documenta en prosa (`visual-mapa.md`) y se programa desde ese documento, con otra librería de mapas.
- **WhatsApp va por el servidor OpenWA de la casa de Julián (decisión de Julián, 21-nov-2026).** Ya había un bot (`mayait/sosgalapagos-bot`, privado) que se conecta por su cuenta con Baileys y clasifica con un modelo de lenguaje. El encargo original pedía un número con la API oficial de Meta y lectura pasiva con OpenWA o WAHA. Julián decidió otra cosa: el bot **deja de conectarse directo a WhatsApp** y pasa a usar la API del servidor OpenWA del homeserver; de ahí extrae y procesa la información. *Qué se hace:* se reemplaza la capa de conexión del bot (`src/whatsapp.ts`) por un cliente de esa API, y el destino deja de ser ResponseGrid y pasa a ser la cola `MensajeEntrante` de la plataforma nueva.
- **Ese servidor tiene hoy dos sesiones, y son los números de Julián** («trabajo» y «personal»). No hay un número dedicado al proyecto. *Qué se hace:* el bot solo lee los grupos de una lista explícita y nunca los chats privados; queda por decidir desde qué número responde (ver el plan técnico).
- **El servidor de la casa pasa a ser una dependencia.** Si se cae o pierde internet, WhatsApp deja de entrar, igual que hoy ocurre con el puente de IERSE en la Mac. *Qué se hace:* la plataforma muestra en coordinación cuándo llegó el último mensaje, y el formulario web y la API siguen funcionando sin WhatsApp.
- **Un documento duplicado se descarta rápido.** Ese mismo día se escribió un `docs/ecosistema.md` en el repo de datos sin saber que otra sesión ya había fusionado el mismo contenido en `AGENTS.md`. *Qué se hace:* `git pull` y búsqueda antes de documentar algo transversal.

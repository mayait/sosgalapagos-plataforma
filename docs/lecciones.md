# Lecciones y decisiones

Registro corto de errores y decisiones, para no repetirlos. Lo más nuevo va arriba. Cada entrada dice qué pasó, por qué importa y qué se hace distinto.

## 2026-11-21 · Puesta en producción

- **Publicado el 21-nov-2026 a las 14:17 (hora de Galápagos) en `https://sosgalapagos.org/riesgos/`.** Comprobado desde fuera: mapa, 59 capas, lluvia, informes, relieve propio del 3D, y `/mapas`, `/clima` y la portada igual que antes. No se probó crear un reporte en producción, para no dejar un reporte de prueba en el mapa público.
- **Al subir las teselas desde la Mac con `tar` se colaron archivos `._*`** (metadatos de macOS), uno por tesela. No estorban, pero ocupan. *Qué se hace:* la próxima subida va con `COPYFILE_DISABLE=1 tar …` o con `rsync`.

- **El relieve de respaldo del 3D tiene agujas falsas.** En producción, con el relieve de terceros, salía un pico inexistente junto a Puerto Ayora. *Qué se hace:* el relieve propio se sube a una carpeta de la plataforma (`/srv/sosgalapagos-relieve3d`) y se sirve en `/riesgos/relieve3d/`. No se puso en la carpeta de `/mapas` porque su publicación borra lo que no reconoce y es de otro equipo.

- **El primer despliegue marcó fallo con todo arriba.** El guion comprueba el servicio desde dentro del contenedor como `localhost`, y `localhost` no estaba entre los nombres que Django acepta en producción: respondía 400. *Qué se hace:* `localhost` va en `ANFITRIONES`. Lo que no vi en la Mac: allí probé desde fuera del contenedor, con el nombre que sí estaba permitido.

- **Lo nuevo del sitio son los informes y mapas en PDF de la portada.** Los publica el repo de datos en `/descargas/` desde las 13:06. Su índice no se sirve por la web: la portada lo lee del disco. *Qué se hace:* el mapa monta esa carpeta en solo lectura y muestra la misma lista bajo «Cerca de aquí». Si el índice no existe (como en la Mac), la sección no aparece. Aquí solo se enlaza lo ya publicado; qué se publica lo decide Julián en el repo de datos.
- **Otra sesión despliega el sitio mientras tanto.** La ruta `/mapa/` que dejé fusionada en el `Caddyfile` ya estaba activa en el servidor (respondía 502) antes de que la plataforma estuviera arriba. *Qué se hace:* una ruta nueva en Caddy solo se fusiona cuando el servicio al que apunta ya responde, o se avisa a quien despliega.

- **La dirección es `/riesgos/`, no `/mapa/` (indicación de Julián).** `/mapa/` se parecía demasiado a `/mapas/`, que es el visor de capas. *Qué se hace:* todo vive bajo `/riesgos/`. Las entradas de abajo que dicen `/mapa/` son de antes del cambio.

- **El sitio actual ya usa `/api` y `/admin`.** El plan ponía la API nueva en `/api/`. *Qué se hace:* todo lo de la plataforma vive bajo `/mapa/` (API, administración, estáticos y fotos). Una sola ruta nueva en Caddy y ningún choque.
- **El despliegue del sitio borra los contenedores que no conoce** (`docker compose up --remove-orphans`). Si la plataforma compartiera su proyecto de Compose, el siguiente despliegue del sitio la borraría. *Qué se hace:* proyecto de Compose aparte (`sosgalapagos-plataforma`), unido a la red del sitio.
- **Reiniciar Caddy corta todo el sitio.** Y como el `Caddyfile` se monta como archivo suelto, un `git pull` no llega al contenedor. *Qué se hace:* se copia el archivo al contenedor, se valida y se recarga en caliente (`caddy reload`), sin reiniciar.
- **Las fotos las sirve Django, no Caddy.** Añadir un volumen a Caddy obligaba a recrearlo. Son pocas y pequeñas.
- **Probar la imagen en modo producción antes de subirla.** Se levantó en la Mac con `DEPURAR` apagado y gunicorn: las 12 rutas responden y el mapa base se sirve por trozos.

## 2026-11-21 · Fase 1

- **Al tocar un reporte con fotos se abría otra cosa (lo reportó Julián: «no veo las fotos»).** Tres causas juntas:
  - Encima del reporte había un punto de control del modelo, en el mismo lugar, y el toque abría ese punto, que no tiene fotos. *Qué se hace:* el toque busca en un cuadrito alrededor del dedo y, si ahí hay un reporte de campo, gana el reporte. Además los reportes de campo se dibujan encima de los demás puntos.
  - Las fotos iban al final de la ficha, bajo el título, los datos y el texto. *Qué se hace:* van primero, la primera en grande.
  - Al tocar una foto se abría el archivo en otra pestaña. *Qué se hace:* visor propio a pantalla completa, con pie de foto, contador, flechas y deslizamiento.
- **El botón Reportar ocupaba el mejor sitio de la hoja (indicación de Julián: «en segundo nivel»).** Era una barra roja de lado a lado sobre el contenido. *Qué se hace:* es un botón pequeño junto al asa. La hoja asomada baja de 138 a 96 px y deja ver más mapa.
- **Probar «se abre la ficha» no es probar «se abre la ficha correcta».** Mi prueba anterior comprobaba que aparecía una ficha, no de qué capa era. *Qué se hace:* la revisión comprueba el nombre de la capa y que el número de fotos mostradas sea el del reporte.

- **`/mapas` cambió y el mapa no sabía dibujar parte de lo nuevo (lo pidió revisar Julián).** Entre las 09:15 y las 11:13 el manifiesto pasó de 56 a 59 capas y estrenó formas de estilo. Lo que faltaba:
  - **Rangos numéricos** (`clasificar.rangos`, en «Población por manzana»): encender esa capa lanzaba un error.
  - **`fill: false`** (límite urbano): se dibujaba con relleno.
  - **Trazo discontinuo según el dato** (`estilo_si`, áreas por validar): salían con línea continua.
  - **Áreas dentro de una capa de líneas** (el agua empozada del flujo observado): sin relleno.
  - **Reportes de campo:** `/mapas` ahora marca con borde punteado la ubicación aproximada, usa un triángulo para el aviso sin foto y pinta los refugios en verde. Se adoptó el mismo significado, conservando el cuadrado.
  - **Borde oscuro** en los puntos que caen en susceptibilidad alta o media.
  - **Enlaces a un lugar** (`#ptoayora`, `#la-cascada`, `#lat,lon,zoom`): ahora también funcionan en `/mapa/`.
  *Qué se hace:* todo eso está corregido, y hay una orden que lo vigila: `manage.py revisar_capas` baja el manifiesto publicado y avisa de cualquier tipo de capa o clave de estilo que el mapa no conozca.
- **Revisar «que las capas se ven» no es encender tres.** Los fallos estaban en capas apagadas por defecto. *Qué se hace:* la revisión enciende las 59 capas una por una y recoge los errores del mapa.

- **Otro equipo actualiza los modelos mientras el mapa está en uso (aviso de Julián).** El 21-nov se publicaron varias versiones de `/mapas` en una mañana: reportes de campo por lotes, la susceptibilidad ajustada con lo observado y una capa nueva del flujo observado. El mapa pedía las capas sin versión, y el navegador, Cloudflare (10 min) y el service worker podían seguir mostrando un modelo viejo. *Qué se hace:*
  - Cada publicación de `/mapas` deja su versión en `version.txt`. El mapa la pega a todas las direcciones de capas, teselas y descargas (`?v=…`).
  - Con el mapa abierto, cada 2 minutos pregunta si hay publicación nueva. Si la hay, vuelve a dibujar lo encendido con los datos nuevos y avisa: «Capas y modelos actualizados».
  - Una capa nueva que venga encendida aparece sola, aunque la persona ya tuviera su elección guardada.
  - El panel Capas dice a qué hora se actualizaron las capas.
  - En la Mac, la copia local se guarda por versión; lo generado y aún no publicado (las teselas del 3D) sirve de respaldo.
- **No dar por fijo lo que publica otro equipo.** *Qué se hace:* antes de tocar algo que dependa de `/mapas`, se hace `git pull` en `sosgalapagos-datos` y se mira `version.txt` del sitio.

- **Los reportes de campo se confundían con los pines nuevos.** Los dos eran círculos rojos. *Qué se hace (lo pidió Julián):* las capas con `marcador: reporte` del manifiesto se dibujan como cuadrados redondeados con un iconito (cámara si trae fotos, casa si es un refugio, «!» si es un aviso sin foto), del color de su gravedad. Los pines de los reportes nuevos siguen siendo redondos. Regla para lo que venga: **redondo = reporte de la plataforma; cuadrado = reporte de campo de `/mapas`.**

- **La vista preferida es satélite con la capa de riesgo encima (indicación de Julián, con captura).** Se había aprobado la base gris, pero al verla en uso Julián mostró la que le gusta: foto de satélite, susceptibilidad en azules y quebradas. *Qué se hace:* el mapa abre en satélite (`MAPA_BASE_INICIAL`), con los nombres de calles en blanco encima de la foto. La base gris propia queda como opción y como respaldo sin conexión, porque el satélite son teselas de un tercero (Esri) que no se guardan en el teléfono. El mapa recuerda la base que cada persona elige.

- **Un globo con texto largo se sale de la pantalla del teléfono.** Al tocar un área afectada salía un globo más alto que el mapa, tapado por la leyenda. *Qué se hace:* ningún elemento de capa abre un globo; todos se leen en la hoja (teléfono) o en el panel (escritorio).
- **Un punto quedaba debajo de un área.** Las capas se apilaban en el orden del manifiesto y los reportes con fotos, que van primero, quedaban abajo. *Qué se hace:* abajo imágenes y polígonos, luego líneas y arriba puntos; dentro de cada tipo manda el manifiesto.
- **Revalidar no bastó: la primera carga tras un cambio seguía con el JavaScript viejo.** *Qué se hace:* los archivos propios llevan su versión en la URL (`?v=<fecha de modificación>`, etiqueta `{% propio %}`). Sin compilación los nombres no cambian, así que la versión es lo único que obliga al navegador a pedirlos de nuevo.

- **En el teléfono no se podía bajar en una ficha con fotos (lo reportó Julián).** La hoja medía siempre el 88 % de la pantalla y se movía con `transform`. A media altura, la mitad de abajo quedaba fuera de la pantalla: el contenido estaba ahí, pero el área que se desplazaba era más alta que lo visible. *Qué se hace:* la hoja mide exactamente lo que se ve (`height`, no `transform`). *Por qué no lo vi:* revisé que la ficha se abriera, no que se pudiera llegar al final. Toda revisión de la hoja incluye ahora desplazarse hasta el último elemento.

- **El riesgo modelado y las quebradas arrancan encendidos (indicación de Julián).** La primera versión abría con pocas capas para no tapar los reportes, y en el teléfono solo con los barrios. *Qué se hace:* arrancan encendidas las capas que `/mapas` marca como visibles en su manifiesto, sin lista propia. En el teléfono se respetan las que `/mapas` apaga por pesadas, salvo los grupos de riesgo de inundación y de quebradas, que salen siempre (`CAPAS_SIEMPRE_GRUPOS`).
- **Los puntos de salud y refugios se confunden con los pines.** Son círculos rojos con «+» muy parecidos a un reporte confirmado. *Qué se hace:* es la única capa visible de `/mapas` que aquí arranca apagada (`CAPAS_APAGADAS_AL_ABRIR`). Queda por decidir si se les cambia la forma para poder encenderlos por defecto.
- **La susceptibilidad pesa 2,3 MB comprimida.** Ahora se baja también en el teléfono. *Qué se hace:* se deja así por indicación; si la prueba en un teléfono de gama baja va lenta, la salida es servirla en teselas vectoriales.

- **El mar debe distinguirse de la tierra (indicación de Julián).** Con la base toda en gris, la costa casi no se leía. *Qué se hace:* la tierra sigue gris y el mar va en azul claro (`estaticos/mapa/base.js`).
- **El navegador también guarda JavaScript viejo por su cuenta.** Tras cambiar el color del mar, la página siguió usando el `base.js` anterior aunque el service worker ya iba primero a la red: la respuesta salía de la memoria del navegador. *Qué se hace:* el service worker pide el código propio con `cache: 'no-cache'`, que obliga a revalidar con el servidor.

- **El logotipo de la USFQ va una sola vez, abajo y muy sutil (indicación de Julián).** La primera versión lo ponía también en la cabecera del panel. *Qué se hace:* solo en la firma del pie, a 18 px de alto y tenue.
- **La vista 3D usa relieve propio.** Las teselas de cota del DTM de 1 m que publicaba `/mapas` solo existían en el zoom 16, y MapLibre necesita varios niveles. *Qué se hace:* el repo de datos genera una pirámide de cota de todo el archipiélago (`37_teselas_relieve3d.py`: DTM de la SGIAR en Santa Cruz y Copernicus en el resto; 47 MB). El mapa la busca en `/mapas/teselas/relieve3d/`; si aún no está publicada, usa Terrain Tiles (AWS) como respaldo. El relieve se pide solo al tocar el botón 3D.
- **Una sola fuente de cota por mapa.** MapLibre no mezcla dos fuentes de elevación, y una fuente que solo cubra Santa Cruz deja un muro en el borde. *Qué se hace:* la pirámide cubre todas las islas con el relieve ya fusionado.
- **El 3D sin sombreado no se nota.** Santa Cruz tiene pendientes suaves y el terreno se veía plano. *Qué se hace:* al activar el 3D se añade una capa de sombreado.
- **Las fotos de una capa llegan como texto.** MapLibre entrega las propiedades con listas (las `fotos` de los reportes de campo) como cadena JSON. *Qué se hace:* se convierten antes de usarlas (`estaticos/mapa/capas.js`).
- **Un globo con fotos no sirve en el teléfono.** *Qué se hace:* los elementos de una capa que traen fotos o un párrafo se abren en la hoja inferior, igual que un reporte.
- **Revisión de teléfono sin teléfono.** La ventana del navegador no siempre acepta un ancho de teléfono. *Qué se hace:* se carga el mapa en marcos de 390 y 360 px del mismo origen y se miden las cajas con un guion: así salieron la franja de lluvia desbordada, la atribución tapada y el asa de 22 px. No reemplaza la prueba en un teléfono real.

- **Las capas deben seguir siendo activables, desactivables y descargables, como en `/mapas` (indicación de Julián).** La primera versión del panel leía un manifiesto viejo (`mapas-galapagos/datos/capas.json`, 24 capas, del 1-nov) y no ofrecía descargas. `/mapas` publica otro, más completo (56 capas) y con su índice de descargas. *Qué se hace:* el panel lee `capas.json` y `descargas.json` de `/mapas`, muestra los enlaces de Shapefile y GeoJSON de cada capa, y trae «Apagar todas las capas» y «Volver a las capas iniciales». No hay lista de capas propia: lo que se publica en `/mapas` aparece aquí.
- **Hay tres manifiestos de capas distintos.** El de `mapas-galapagos/datos/` (entregable cerrado), el de la plataforma vieja (`/capas/galapagos-2026/`) y el de `/mapas`. El vigente es el de `/mapas`. *Qué se hace:* se usa solo ese.

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

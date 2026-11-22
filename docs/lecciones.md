# Lecciones y decisiones

Registro corto de errores y decisiones, para no repetirlos. Lo más nuevo va arriba. Cada entrada dice qué pasó, por qué importa y qué se hace distinto.

## 2026-11-21 · Puesta en producción

- **`/riesgos/` abre en calles (indicación de Julián).** Antes abría en satélite. *Qué se hace:* `MAPA_BASE_INICIAL = "calles"`. Quien ya eligió otra base la conserva, porque el mapa recuerda la elección de cada persona. De paso se corrigió que con calles o topográfico los nombres salían dos veces (los de la imagen y los del mapa propio encima).

- **Los informes en PDF van solo en la portada (indicación de Julián).** Los había puesto también bajo «Cerca de aquí» en el mapa al leer «pon todo lo nuevo». *Qué se hace:* se quitó la sección; el código quedó en `Archivo/informes-en-riesgos/`. Antes de repetir en el mapa algo que ya está en la portada, se pregunta.

- **El satélite no llega igual de cerca en todas las islas.** Al abrir el centro de acopio en San Cristóbal, el mapa mostraba teselas grises con «Map data not yet available». El proveedor responde con esa imagen en vez de un error, así que no se puede detectar. *Qué se hace:* el satélite se pide hasta el zoom 16 y de ahí se amplía. Lo vi por mirar el mapa en otra isla; todas mis pruebas anteriores eran en Puerto Ayora.

- **Un centro de acopio no es un reporte de paso (lo pidió Julián: «un corazón en la USFQ San Cristóbal»).** Faltaban tres cosas: nombre propio, varias fotos y un plazo que no lo borre a los tres días. *Qué se hace:* los avisos tienen `titulo` opcional y fotos adicionales; coordinación puede fijar el vencimiento; y hay una orden, `manage.py crear_aviso`, para crearlos confirmados y visibles. «Dónde donar o colaborar» pasa a pin rosa con corazón, el mismo rosa de los corazones de `/mapas`.
- **Fotos con caras: se publican solo con permiso.** De las cinco fotos del acopio, cuatro muestran personas reconocibles (voluntarias, guardias, un trabajador). *Qué se hace:* se publicó solo la que no muestra a nadie; las demás esperan a que Julián confirme que esas personas aceptan aparecer.

- **Los pines positivos sí existían: llegaron 20 minutos después de que los busqué.** A las 14:52 `/mapas` publicó la capa «Buenas noticias y ayuda del 21-nov», con un marcador nuevo, `corazon`. Mi mapa la dibujaba como un punto rosa cualquiera, y la orden `revisar_capas` no avisó porque miraba la clave `marcador` pero no su valor. *Qué se hace:* el mapa dibuja el corazón; `revisar_capas` comprueba también el valor de `marcador`. Queda la duda de si conviven bien con los pines «Algo bueno» que añadí antes: son dos caminos para lo mismo (uno curado por el equipo de datos, otro abierto a cualquiera).
- **Informe: la lluvia no se suma entre estaciones.** Se muestra la serie de una estación, tal como la publica `/clima`. Sumar o promediar varias sería un dato derivado, y las licencias de algunas fuentes no lo permiten. Tampoco hay dos ejes en un gráfico: lluvia y reportes van en dos gráficos apilados con el mismo eje de tiempo.
- **Un gráfico con ancho fijo se vuelve ilegible en el teléfono.** Con un lienzo de 720 px escalado, la letra de los ejes quedaba en 4 px. *Qué se hace:* el lienzo mide lo mismo que su hueco en pantalla y se vuelve a dibujar al cambiar el ancho.
- **Dar de baja `/mapas` es dar de baja su visor, no sus datos.** `/riesgos/` lee de `/mapas/` el manifiesto, las capas, las descargas y las teselas. El plan está en `plan-baja-mapas.md`; hoy no se cumple ninguno de sus cinco criterios.
- **Pulsación larga sin sorpresas.** Abre un aviso con «Reportar aquí» en vez de saltar al formulario: una pulsación sin querer no saca a nadie del mapa. En 3D el clic derecho gira el mapa, así que ahí no se ofrece.

- **El mapa no es solo de peligros (indicación de Julián: «pines positivos de cosas lindas, y otro de dónde donar o colaborar»).** Busqué esos pines ya creados y no los hallé en `/mapas`, en el repo de datos, en la plataforma anterior ni en `/riesgos/`. *Qué se hace:* el mapa de riesgos admite tres clases de aviso: un peligro, algo bueno y dónde donar o colaborar. Cada tipo de aviso tiene su `clase`.
  - **Algo bueno:** pin amarillo con corazón; vive 48 h.
  - **Dónde donar o colaborar:** pin negro con caja de regalo; vive 72 h y se renueva con «sigue ahí».
  - En esas dos clases no se pregunta profundidad ni si se puede pasar, y el segundo botón dice «Ya no está».
  - Siguen las mismas reglas: entran «por verificar», el texto se publica cuando coordinación lo revisa y se retiran solos.
- **Sigue sin usarse el verde en los pines.** Lo bueno va en amarillo, no en verde, para que nadie lo lea como «aquí es seguro».

- **Muchos puntos no decían qué eran (lo pidió Julián: un «mouseover chiquito y simple»).** Había que tocar cada punto para saberlo. *Qué se hace:* al pasar el ratón sale una pista de dos líneas: qué es y su clase («Punto de inundación · Prioridad media · SC-020»). Vale para los puntos y las líneas de las capas y para los pines de los reportes. Los códigos no encabezan la pista, porque no explican nada. Las áreas no dan pista: cubren casi todo el mapa. En el teléfono no hay ratón: ahí se toca el punto.
- **Cambiar solo el `#…` de la dirección no recarga la página.** Al probar, seguía corriendo el JavaScript anterior. *Qué se hace:* en las pruebas se navega a otra página y se vuelve.

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

## Baja del visor de `/mapas` (21-nov-2026)

- **`/riesgos/` es el único mapa; `/mapas/` redirige.** Decisión de Julián. Solo se redirige la página (`/`, `/index.html`) dentro del bloque de `/mapas` del Caddy; los datos se siguen sirviendo. *Qué se hace:* nunca tocar la carpeta `/srv/sosgalapagos-mapas` ni su ruta. Detalle en `docs/plan-baja-mapas.md`.
- **Lo que la gente guardó en un visor se hereda si se usa la misma clave.** `/mapas/` y `/riesgos/` son el mismo dominio, así que comparten `localStorage`. «Mis puntos» usa la clave y el formato del visor anterior. *Qué se hace:* antes de retirar una página que guarda algo en el navegador, mirar su clave y leerla desde la nueva.
- **OpenStreetMap rechaza teselas pedidas sin `Referer`** (403 «Access blocked»). Django pone por defecto `Referrer-Policy: same-origin` y el navegador no envía el origen a otros dominios. En producción no se notaba porque Caddy fija otra política; en local el mapa de calles salía bloqueado. *Qué se hace:* `SECURE_REFERRER_POLICY = "strict-origin-when-cross-origin"` en los ajustes, para no depender del proxy.
- **Una regla CSS añadida al final gana a la consulta de escritorio de más arriba.** El buscador salió a la izquierda en escritorio. *Qué se hace:* las variantes de escritorio de un bloque nuevo van en su propio `@media`, después del bloque.
- **La publicación de datos usa `rsync --delete`.** Al dejar de generar el `index.html` del visor, la siguiente publicación lo habría borrado del servidor. *Qué se hace:* `--exclude /index.html` en `publicar_mapas.sh` del repo de datos: ni se sube ni se borra.


## Línea del tiempo (21-nov-2026)

- **La página `/riesgos/informe/` se llama «Línea del tiempo»** (indicación de Julián). Es vertical: la lluvia de cada hora va a un lado del eje y los reportes al otro.
- **El tiempo vacío no ocupa sitio.** Los días sin reportes y con menos de 5 mm se juntan en una fila («9 días sin reportes · del 3 al 11 nov»); las horas con menos de 1 mm y sin reportes van al resumen del día. Así la página abre con todo el evento y semanas de sol no la alargan. Los umbrales (`CALMA_MM`, `HORA_MM` en `informe.js`) son preliminares.
- **Para moverse rápido hay un navegador fijo arriba:** un día por columna, lluvia hacia arriba y reportes hacia abajo, y botones de salto (hoy, último reporte, día más lluvioso, inicio). Un toque lleva al día. La escala va hasta el mayor valor real, dicho en la leyenda: con un tope «redondo» (500 mm para 236) las barras quedaban enanas.
- **En la línea del tiempo lo relevante son los reportes, no la lluvia** (corrección de Julián el mismo día). Se quitó la columna de lluvia, su cifra y el selector de estación. La lluvia queda solo como hito («Llovió X mm este día») los días de 50 mm o más (`HITO_MM`, preliminar), con la estación de la isla. Los días sin reportes ni hito se juntan en una fila. En el mapa, el acceso se llama **«Ver como lista»**.
- **La línea del tiempo se filtra por zonas grandes, no por barrio** (indicación de Julián): Santa Cruz (Puerto Ayora), Santa Cruz parte alta, San Cristóbal (Puerto Baquerizo), San Cristóbal parte alta e Isabela. Se asignan por coordenadas en `informe.js` (`zonaGrande`): parte alta de Santa Cruz al norte de la latitud −0,718; parte alta de San Cristóbal al este de la longitud −89,585. Son cortes aproximados y preliminares.

## Edificios con volumen y color en 3D (22-nov-2026)

- **Una capa de polígonos puede levantarse en la vista 3D.** Si el manifiesto de `/mapas` le pone `"extrusion": {"altura": "altura_m", "auto_3d": true}`, `capas.js` la dibuja como volumen: cada polígono sube hasta su altura y toma el color de su clase (`clasificar`). Fuera del 3D se ve plana, como siempre. Con `auto_3d`, la capa se enciende sola al entrar en 3D y se apaga al salir, sin guardarse como elección de la persona; si la toca, pasa a ser suya.
- **Para qué nació:** los edificios de la zona afectada del 21-nov, pintados por la gravedad aparente de donde están y con la altura estimada (petición de Julián). La capa y sus datos viven en `sosgalapagos-datos`.
- **Dos cajas en el mismo sitio parpadean.** Esos edificios también están en el mapa base, que los dibuja en gris. Para que no se peleen, el volumen de la capa se dibuja con una copia de los polígonos crecida medio metro desde su centro (`crecida()`), y los edificios del mapa base sin altura conocida bajan de 4 m a un piso (`SOS.ALTURA_PISO`, 3 m). Así la caja de color envuelve a la gris.
- **La altura es una estimación**, el promedio de los edificios de su tamaño en una muestra: sirve para leer el conjunto, no un edificio.

## Fase 2: WhatsApp, puntos, app y avisos (22-nov-2026)

- **El formulario dejaba enviar sin lugar.** Si el teléfono no daba la ubicación, el pin quedaba en el centro por defecto del mapa y el reporte salía ahí, sin avisar. *Qué se hace:* no se envía sin un origen del lugar (teléfono, foto, mapa o a mano); el botón «Estoy aquí» dice qué pasó (sin permiso, GPS apagado, poco preciso) y cómo arreglarlo en iPhone y en Android.
- **El asistente de WhatsApp vive en la plataforma (`entradas/`), no en `sosgalapagos-bot`.** El plan decía reescribir el bot; ese bot está hecho para pedidos y voluntarios de ResponseGrid y no sirve aquí. Un módulo pequeño junto a las reglas del reporte evita un segundo servicio y una segunda base. `sosgalapagos-bot` queda sin tocar.
- **Antes del modelo va un filtro de reglas.** Lo pidió Julián («algo como regex»). Lo que no lo pasa no se guarda ni sale del servidor: es la privacidad de los chats, además del costo.
- **Capa de modelos que no depende del proveedor: Pydantic AI.** Se descartó LiteLLM por el paquete comprometido de marzo de 2026. El prefijo de Gemini en la versión 2 es `google:`, no `google-gla:`.
- **Las pruebas del flujo destaparon dos reglas flojas:** «se inundó» no se reconocía, y al responder «¿qué teléfono?» una frase con «se inundó» cambiaba el tipo del aviso. *Qué se hace:* mientras la persona responde a una pregunta, el tipo ya dicho no cambia.
- **Un daño en infraestructura pública no es una inundación:** tipo aparte, con 14 días de plazo.
- **Los puntos son un gracias, no un premio.** 10 por aviso, 5 más con foto, 2 por confirmar. Solo se muestra el nombre o apodo que la persona eligió; coordinación puede ocultar uno impropio. Un «nombre» con forma de teléfono o correo no se guarda.
- **Avisos del navegador (Web Push):** en iPhone solo llegan a la app instalada. Solo se avisa de peligros confirmados, a quien lo pidió.

||||||| d68eddb
- **Dos despliegues a la vez tumbaron `/riesgos/` unos minutos** (22-nov, 07:00 UTC): otra sesión corría `desplegar.sh` al mismo tiempo y Docker dejó contenedores a medio recrear. Se levantó con `docker compose up -d`; no se perdió ningún dato. *Qué se hace:* antes de desplegar, avisar a las otras sesiones (`ListAgents`) y mirar que no haya otro despliegue en curso.
- **El formato del webhook de OpenWA se averiguó anotando solo la estructura** (campos y tipos, sin contenido) en modo ensayo. La ubicación de WhatsApp sí trae coordenadas en el webhook, aunque la base de OpenWA no las guarde.
- **La llave «ANTHROPIC DEV» no tenía saldo.** Se usó «CLAUDE_API_KEY». *Qué se hace:* probar cada llave con una llamada mínima antes de configurarla.


## Una sola app para todo el sitio (22-nov-2026)

- **Los botones «Instalar» y «Avisos» no funcionaban en el teléfono.** Tres causas: en iPhone el permiso de avisos se pedía después de esperar al service worker, y Safari solo muestra la pregunta si se pide dentro del mismo toque; «Instalar» en iPhone mostraba una nota pequeña al fondo del panel, que nadie veía; y la portada tenía otro manifiesto (el de ResponseGrid), o sea, otra app. *Qué se hace:* el permiso es lo primero que se pide en el toque; los mensajes salen en una ventana centrada; al suscribirse llega un aviso de prueba, para saber que funciona.
- **El componente vive en `/riesgos/app.js`** (`plantillas/reportes/app.js`) y no depende del mapa: cualquier página del sitio lo usa con `<div data-sos-app></div>` y la etiqueta del script. Lo usan la portada, `/riesgos/` y `/clima/`.
- **Un solo manifiesto, con alcance `/`**: portada, riesgos y clima se abren dentro de la misma app instalada. El identificador sigue siendo `/riesgos/`, para que quien ya la instaló no tenga dos.
- **La suscripción a los avisos no pide la cookie del formulario** (se llama también desde la portada y desde clima), pero solo se acepta desde páginas del propio sitio (cabecera `Origin`).

## Clima en Django (22-nov-2026)

- **Migrar copiando la base, no portando primero los recolectores.** El recolector anterior sigue recogiendo; Django copia su base cada 5 minutos. Así todo el dato está en PostgreSQL desde el primer día sin tocar lo frágil. Plan por etapas en `docs/plan-clima.md`.
- **Lo caro del clima anterior no es recoger, es exportar.** Cada fuente tarda segundos; los 2,5 minutos de CPU por corrida son de rehacer toda la historia cada vez. En Django los resúmenes por hora se mantienen al día solo para lo que cambió.
- **Sin guardar lo pronosticado no se puede mejorar un pronóstico.** Al guardarlo y verificarlo salió que todos los modelos globales se quedan cortos por 35–45 mm al día en este evento.
- **Una API gratuita puede devolver datos falsos a propósito.** Windy Point Forecast, en su versión de prueba, mezcla y altera los datos, y lo dice en un campo `warning` de la respuesta. *Qué se hace:* leer la respuesta entera de una fuente nueva antes de usarla, no solo los números.
- **Cupos pequeños se administran contando.** Stormglass da 10 llamadas al día por llave: cada llamada deja una corrida en la base y antes de llamar se cuentan las del día.
- **Un boletín en imagen se detecta por su huella y lo lee el modelo.** El resumen se guarda con el enlace al original y una marca de «revisado por una persona». En la primera corrida, los boletines que ya existían se marcaron como avisados para no mandar avisos de documentos viejos.
- **`get_or_create` y no `create` + capturar el error** para la clave única de un aviso: dentro de una transacción, el error deja la transacción rota.
- **El relevo del clima se hizo sin reescribir los recolectores**: corren tal cual dentro de Django, sobre vistas de PostgreSQL con la forma de las tablas de SQLite. Reescribir 4 200 líneas habría sido el mayor riesgo; lo caro (exportar) sí se rehízo nativo. *Qué se hace:* para migrar un sistema que funciona, separar lo que cuesta de lo que solo es frágil, y rehacer primero lo que cuesta.
- **Antes de cambiar quién escribe un archivo, comparar los dos resultados valor por valor.** `clima_panel --comparar` dio cero diferencias en 238 000 valores; eso, no una opinión, autorizó el relevo.
- **`set -e` con `grep -c` corta el guion cuando la cuenta es cero** (grep devuelve 1). Pasó en mitad del relevo: los timers viejos ya estaban detenidos y el despliegue no corrió. Se terminó a mano en un minuto. *Qué se hace:* `grep -c … || true`, y los pasos de un relevo se ordenan para que un corte deje lo viejo funcionando, no un hueco.
- **Una página puede rechazar a un cliente por su lista de cifrados TLS.** Weather Underground daba 403 al Python de la imagen de contenedor y 200 al de Debian, con el mismo código y la misma IP. *Qué se hace:* si una fuente funciona fuera del contenedor y no dentro, probar con `ssl.create_default_context().set_ciphers("DEFAULT")`.


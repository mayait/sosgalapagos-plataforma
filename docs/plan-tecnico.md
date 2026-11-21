# Plan técnico: mapa único de reportes de riesgo

*Aprobado por Julián Maya el 21-nov-2026. Fase 1 en curso.*

**Decisiones de Julián (21-nov-2026):** se aprueban las propuestas 1 a 3 y 6 de la sección 10. La interfaz usa «MORE HUMANS» de forma sutil. El bot de WhatsApp recibe y responde desde la sesión «trabajo». El enlace de un solo uso queda para más adelante.

**Qué se construye:** un mapa único en `sosgalapagos.org` donde la gente reporta lugares de riesgo con fecha, y donde los reportes se retiran solos. Los reportes entran por formulario web, API y WhatsApp. `/mapas` y `/clima` siguen funcionando igual.

**Estado:** fase 1 construida y probada en local. El visual está en [`visual-mapa.md`](visual-mapa.md). Quedan abiertas las decisiones 7, 8 y 9 de la [sección 10](#10-decisiones-que-necesito-de-julián), que no bloquean hasta la fase 3.

> **Hoy hay una emergencia en curso.** El 21-nov `/clima` marca «muy alto» en La Cascada y la portada lleva un comunicado de inundación. Nada de este plan toca producción hasta que Julián lo apruebe de forma explícita, y el primer despliegue no reemplaza ninguna ruta existente.

## 1. Qué cambió frente al encargo

Verifiqué cada decisión por defecto contra las fuentes actuales. Cinco cambian:

| Decisión del encargo | Qué encontré | Propuesta |
|---|---|---|
| Django 6 con tareas en base de datos (`django-tasks`) | El núcleo de Django 6 solo trae backends de prueba. El backend de base de datos está en el paquete `django-tasks-db` 0.13, que declara Django 5.2 y 6.0, no 6.1 | **Django 6.0.x** con `django-tasks-db`. Se sube a 6.1 cuando el paquete lo declare |
| API con `django-ninja-spatial` | Existe, pero nació en mayo de 2026, tiene dos versiones del mismo día, ningún uso visible, no declara Django 6 y deja fuera `Feature` y `FeatureCollection` | **django-ninja 1.8 con `geojson-pydantic`** para los esquemas GeoJSON. Es menos cambio que pasar a Django REST Framework |
| MapLibre GL JS sin compilación | La versión 6 quitó el script clásico y exige WebGL2. Eso deja fuera teléfonos viejos | **MapLibre 5.24**, que conserva el script clásico y WebGL1. Los archivos se sirven desde el propio sitio, no desde un CDN |
| WhatsApp con la API oficial de Meta y WAHA | Julián decidió el 21-nov usar el servidor OpenWA del homeserver, con `sosgalapagos-bot` adaptado a esa API | Ver la [sección 7](#7-whatsapp) |
| Lugares seguros: «albergues» | La regla del proyecto es decir «refugio», nunca «albergue» | **«Refugio»** en interfaz, código y datos |

Lo demás se confirma:

- **Mapa base:** el extracto PMTiles de Galápagos hasta zoom 15 pesa **5 MB**. Cabe guardado en el teléfono. Sale de la compilación diaria de Protomaps y exige atribución a OpenStreetMap.
- **Feed CAP del INAMHI:** está publicando y cubre Galápagos. La última alerta es del 17-nov. Una alerta rotulada «Galápagos» traía el polígono en el continente, así que se filtra por polígono y no por el nombre del área.
- **Open311:** la especificación solo conoce los estados `open` y `closed` y exige XML. Los cuatro estados del reporte van como campo adicional, y la API responde solo JSON. Queda declarado en la documentación como desviación.

## 2. Arquitectura

```
Cloudflare ─► Caddy (el que ya existe)
                ├─ /mapas/  /clima/  /estudios/  /usfq/     sin cambios
                ├─ /        /e/…   /backend/                ResponseGrid, hasta la fase 4
                └─ /riesgos/   /api/                           plataforma nueva (Django)
                                  │
                    ┌─────────────┼──────────────┐
                    ▼             ▼              ▼
                 web (Django)  trabajador     reloj
                 gunicorn      db_worker      encola tareas cada minuto
                    └─────────────┼──────────────┘
                                  ▼
                        PostGIS (contenedor y volumen propios)

  /srv/sosgalapagos-clima/datos/estado.json ──lectura──► ajuste por clima
  feed CAP del INAMHI ──cada 10 min──► advertencias oficiales
  homeserver (OpenWA) ──► sosgalapagos-bot ──► /api/interno/mensajes
```

- **Una sola aplicación Django** sirve páginas, API y administración. Sin Redis ni Celery.
- **PostGIS va en un contenedor nuevo con su propio volumen.** El Postgres actual de ResponseGrid no tiene PostGIS y no se toca.
- **Los reportes vivos salen como un solo GeoJSON**, sin servidor de teselas. El navegador lo vuelve a pedir cada 4 s mientras la pestaña está visible; si no cambió, el servidor responde «sin cambios» y no se transfiere nada.
- **El vencimiento no depende de ninguna tarea.** La consulta de reportes vivos filtra por `vence_en` posterior a la hora actual, así que un reporte vencido desaparece aunque el trabajador esté caído. La tarea periódica solo hace el trámite: marcarlo cerrado y pasarlo al archivo.
- **Todo el JavaScript y las tipografías se sirven desde el sitio.** Sin CDN, para que la app instalada funcione sin señal.

## 3. Estructura del repositorio

Repositorio `mayait/sosgalapagos-plataforma`. Apache 2.0 para el código y CC BY 4.0 para los datos, con los mismos archivos de licencia que el repo de datos.

```
sosgalapagos-plataforma/
├── AGENTS.md  CLAUDE.md  README.md  LICENSE  LICENCIA-DATOS.md  NOTICE
├── manage.py  pyproject.toml  uv.lock
├── plataforma/              configuración de Django (ajustes, rutas, wsgi)
├── reportes/                modelos, reglas de vida, formulario, ficha, mapa
│   ├── modelos.py  reglas.py  tareas.py  vistas.py  fotos.py
│   └── pruebas/             vencimiento, duplicados, confirmaciones
├── zonas/                   diccionario de lugares y carga desde geodatos
├── api/                     Open311, GeoJSON, llaves, límites de frecuencia
├── coordinacion/            cola de verificación, fusión, tramos, exportación
├── entradas/                MensajeEntrante y cola (WhatsApp y otros canales)
├── clima/                   lectura de estado.json y ajuste del plazo
├── alertas/                 feed CAP del INAMHI
├── plantillas/              HTML con HTMX y Alpine
├── estaticos/
│   ├── mapa/                módulos propios del mapa (capas, pines, panel)
│   ├── terceros/            MapLibre, pmtiles, HTMX, Alpine (versiones fijas)
│   ├── base/                galapagos.pmtiles, glifos e iconos
│   └── app/                 manifiesto de instalación y service worker
├── despliegue/              Dockerfile, fragmento de compose y de Caddy
├── docs/                    este plan, visual-mapa.md, lecciones.md
└── Archivo/                 lo que se descarte (nunca se borra)
```

## 4. Modelo de datos

Los seis modelos del encargo, más los campos que hacen falta para cumplir sus reglas. Los añadidos van marcados con ＋.

**TipoRiesgo** · `codigo`, `nombre`, `icono`, `plazo_horas`, `orden`, `activo`. Editable en el admin.

| Código | Nombre | Plazo |
|---|---|---|
| `agua_via` | Agua en la vía | 6 h |
| `quebrada` | Quebrada crecida | 6 h |
| `via_cortada` | Vía cortada | 24 h |
| `vivienda` | Vivienda anegada | 24 h |
| `cable` | Cable caído | 24 h |
| `deslizamiento` | Deslizamiento | 72 h |

**Reporte**

| Campo | Detalle |
|---|---|
| `tipo` | Referencia a TipoRiesgo |
| `gravedad` | Pasar con cuidado · no pasar · peligro de vida |
| `profundidad` | Tobillo · rodilla · cintura · puerta de auto · sin dato |
| `punto` | Punto, obligatorio |
| `tramo` | Línea, opcional y solo para coordinadores |
| `visto_en`, `vence_en` | `vence_en` se calcula; nunca lo escribe el usuario |
| `estado` | Por verificar · confirmado · bajando · cerrado |
| `fuente` | Vecino · coordinador · institución · WhatsApp |
| `foto`, `nota`, `zona` | La nota tiene un máximo de 280 caracteres |
| ＋ `cerrado_en`, `motivo_cierre` | Venció · dos «ya bajó» · coordinador. El issue 80 pide cuánto duró el agua |
| ＋ `origen_agua` | Cañada que se desborda · calle que se encharca · alcantarillado. Opcional, lo llena coordinación; lo pide el issue 80 |
| ＋ `fusionado_en` | Reporte al que se fusionó como duplicado |
| ＋ `creado_por_llave` | Llave de API que lo creó, si aplica |
| ＋ `precision_m` | Precisión que informó el GPS |

**Confirmacion** · `reporte`, `tipo` (sigue ahí · ya bajó), `fecha`, `huella`.

**Zona** · `nombre`, `tipo` (barrio, sector, callejón, vía, referencia), `isla`, `geometria`, `fuente`, más una tabla de **alias** con los nombres locales (＋).

**LlaveApi** · `institucion`, `llave` (solo se guarda su resumen criptográfico), `permisos`, `activa`, ＋ `ultimo_uso`.

**MensajeEntrante** · `canal`, `texto`, `medios`, `candidato` (JSON), `estado_cola`, ＋ `grupo`, `remitente_hash`, `recibido_en`, `reporte` (cuando se publica).

**AdvertenciaOficial** (＋, para el feed CAP) · `identificador`, `emisor`, `severidad`, `titulo`, `vigente_desde`, `vence_en`, `poligono`.

### Privacidad en el modelo

- **Huella del dispositivo:** un identificador aleatorio que se crea en el teléfono y se guarda cifrado con una clave del servidor. No se toma ninguna huella del navegador.
- **Teléfonos:** nunca en claro. Solo un resumen con clave, que sirve para reconocer al mismo remitente sin poder recuperar el número.
- **Fotos:** se lee la ubicación, se vuelve a codificar la imagen sin metadatos y se descarta el original.
- **Nota y foto de un vecino no son públicas hasta que un coordinador las ve.** El pin sí aparece al instante, marcado «por verificar». Así un nombre, una cédula o la cara de un menor no llegan al mapa sin revisión. *Es una propuesta; ver la decisión 6.*

## 5. Reglas de vida del reporte

Todas viven en `reportes/reglas.py` como funciones puras, con pruebas.

1. **Plazo:** `vence_en = visto_en + plazo del tipo`.
2. **Sigue ahí:** renueva el plazo desde ese momento.
3. **Ya bajó:** con la primera el estado pasa a «bajando». Con la segunda, desde otro dispositivo, se cierra.
4. **Duplicado:** un reporte nuevo del mismo tipo a menos de 50 m de uno vivo se guarda como confirmación «sigue ahí» del existente. Si trae foto, queda adjunta al original.
5. **Ajuste por clima** (fase 3, umbrales preliminares y editables):
   - 3 horas sin lluvia en la zona: el plazo restante se reduce a la mitad, una sola vez por periodo seco.
   - Lluvia fuerte: el plazo se renueva.
   - La lluvia sale de `inundacion.zonas[].R` en `estado.json`. Solo hay cuatro zonas de clima (La Cascada, parte alta de Santa Cruz, San Cristóbal e Isabela), así que cada reporte usa la zona de clima que lo contiene.
   - Si `estado.json` tiene más de 20 minutos, no se ajusta nada.
6. **Cierre:** un reporte cerrado nunca se borra. Queda en el archivo con fecha, hora, lugar, profundidad y duración.
7. **El mapa nunca dice «zona segura».** Donde no hay reportes dice «sin reportes activos».

## 6. Rutas

Hasta la fase 4 todo lo nuevo vive bajo `/riesgos/` y `/api/`, para no chocar con ResponseGrid.

| Ruta | Qué es | Fase |
|---|---|---|
| `/riesgos/` | Mapa (será `/` en la fase 4) | 1 |
| `/riesgos/reportar/` | Formulario de tres pasos | 1 |
| `/riesgos/r/<id>/` | Ficha del reporte, con «sigue ahí» y «ya bajó» | 1 |
| `/riesgos/cerca/` | Fragmento HTMX de la hoja inferior | 1 |
| `/api/reportes/vivos.geojson` | Reportes vivos | 1 |
| `/api/v2/services.json` | Open311: tipos | 2 |
| `/api/v2/requests.json` | Open311: crear y consultar | 2 |
| `/api/v2/requests/<id>.json` | Open311: un reporte | 2 |
| `/api/docs` | Documentación OpenAPI | 2 |
| `/api/interno/mensajes` | Entrada del bot de WhatsApp, con llave | 2 |
| `/riesgos/e/<token>/` | Enlace de un solo uso con el punto ya puesto | 2 |
| `/coordinacion/…` | Cola, fusión, tramos, lista y exportación (con cuenta) | 2 |
| `/admin/` | Administración de Django | 1 |
| `/api/archivo.geojson`, `/api/archivo.csv` | Archivo del evento | 3 |
| `/api/advertencias.geojson` | Advertencias oficiales vigentes | 3 |

- **Lectura pública** con límite por dirección IP. **Escritura por API** solo con llave de institución.
- **El formulario web no pide llave.** Lleva límite por dispositivo y por IP.
- **Por comprobar antes de desplegar:** que la web actual no use ya la ruta `/api/`. Si la usa, la API nueva arranca en `/riesgos/api/`.

## 7. WhatsApp

Decisión de Julián del 21-nov: se usa el servidor OpenWA del homeserver, y `sosgalapagos-bot` pasa a leer de esa API.

**Qué encontré en ese servidor:** responde en su dirección pública y tiene dos sesiones conectadas, «trabajo» y «personal». Las dos son números de Julián. No hay un número del proyecto.

**Qué cambia en `sosgalapagos-bot`:**

| Parte | Hoy | Después |
|---|---|---|
| Conexión (`whatsapp.ts`) | Baileys, sesión propia con QR | Cliente de la API de OpenWA: recibe mensajes por webhook y descarga los medios |
| Destino (`responsegrid.ts`) | API de ResponseGrid | `POST /api/interno/mensajes` de la plataforma nueva |
| Extracción (`analista.ts`) | Clasifica pedidos y ofertas de ayuda | Extrae candidatos de riesgo: tipo, lugar, hora y foto |
| Ubicación (`lugares.ts`) | Lista propia | Diccionario de zonas de la plataforma |
| Moderación, tareas, difusión | Comandos en grupos | Se archivan; la verificación pasa a la pantalla de coordinación |

**Reglas que no cambian:**

- El bot **nunca publica solo**. Todo candidato entra a la cola de verificación.
- Lee **solo los grupos de una lista explícita** y **nunca chats privados**. Esto pesa más ahora, porque la sesión es una cuenta personal.
- El texto de los mensajes se borra a los 7 días. Lo que se publica va sin nombres.
- Antes de leer un grupo se fija el aviso en ese grupo. El borrador del aviso se entrega con la fase 3.

**Riesgos nuevos:**

- **El homeserver es una dependencia.** Si se apaga o pierde internet, WhatsApp deja de entrar. El formulario y la API siguen. Coordinación verá la hora del último mensaje recibido.
- **Bloqueo del número.** OpenWA no es la API oficial; WhatsApp puede restringir la cuenta. Leer tiene menos riesgo que escribir, pero no encontré ninguna fuente que lo mida. Si el bot responde desde «trabajo» o «personal», el riesgo recae sobre el número de Julián.
- **Hay dos proyectos llamados OpenWA** con licencias distintas. Falta confirmar cuál corre en el homeserver.

Lo que ya no aplica: el precio de los mensajes de Meta y la exención para organizaciones sin fines de lucro. Lo verifiqué igual, por si se retoma: desde octubre de 2026 Meta cobra los mensajes de servicio después de los primeros 1 000 al mes, y no pude confirmar que una universidad califique para la exención.

## 8. Mapa y teléfono

- **Base:** `galapagos.pmtiles` (5 MB) con el estilo claro de Protomaps ajustado a gris. Calles, satélite y topográfico siguen siendo las teselas externas de hoy y solo se cargan si se eligen.
- **Capas:** las mismas de `/mapas`. El panel lee su `capas.json` y su `descargas.json`, así que toda capa se puede encender, apagar y descargar en Shapefile y GeoJSON. Cada capa se baja al encenderla y va debajo de los pines.
- **Pines:** una fuente GeoJSON con clusters. Color por estado, icono por tipo y tamaño por gravedad.
- **Desteñido por edad:** la opacidad depende de qué fracción del plazo ya pasó. El teléfono la recalcula cada minuto, sin pedir datos.
- **Fichas de tiempo:** «ahora» muestra los vivos; «24 h» y «todo el evento» añaden los cerrados en gris.
- **Instalable:** manifiesto de aplicación y service worker. Guarda la base, la interfaz y la última respuesta de reportes vivos, con su hora bien visible.
- **Reportes sin señal:** se guardan en el teléfono y se envían cuando vuelve la conexión. Conservan su `visto_en` original.
- **Foto:** se reduce en el teléfono a unos 1 600 px antes de subir.
- **Prueba en Android de gama baja:** es la primera tarea de la fase 1, con un prototipo mínimo (base, 200 pines y una capa pesada). No tengo acceso a un teléfono físico: **necesito que alguien del equipo haga esa prueba** con un enlace que yo preparo. Si no rinde, lo reporto antes de seguir.
- **Fondo blanco, sin modo oscuro.** Aviso fijo en todas las pantallas: «Información ciudadana preliminar, no oficial. Emergencias: 911».

## 9. Despliegue

**Nada de esto se ejecuta sin aprobación explícita.** El primer despliegue solo añade; no reemplaza ninguna ruta.

- **Servicios nuevos** en el compose existente: `postgis`, `plataforma`, `plataforma-trabajador` y `plataforma-reloj`. Volúmenes nuevos para la base y las fotos.
- **Caddy:** dos bloques nuevos, `/riesgos/*` y `/api/*`, antes del bloque final que manda todo a la web actual. `/mapas`, `/clima`, `/estudios` y los sitios privados no se tocan.
- **Dónde vive la configuración:** el Caddy y el compose de todo el servidor están hoy en `mayait/sosgalapagos`, en `deploy/sosgalapagos/`. Hasta la fase 4 los cambios van allí, con pull request. En la fase 4 esa carpeta se copia al repo nuevo y la vieja pasa a `Archivo/`.
- **Clima:** el contenedor monta `/srv/sosgalapagos-clima` en solo lectura. No hace falta ninguna petición por red.
- **Respaldo:** la base nueva se suma al `backup.sh` diario. Las fotos se respaldan aparte.
- **Capacidad:** el servidor tiene 4 vCPU y 8 GB. Los cuatro servicios nuevos caben, pero **mido la memoria libre antes de proponer la fecha** del primer despliegue.
- **Bloque de repositorios:** el «árbol de repositorios» de los cinco `AGENTS.md` pasa a tener seis. Se actualiza en todos a la vez.

## 10. Decisiones que necesito de Julián

**Bloquean la fase 1:**

1. **Stack ajustado.** ¿Apruebas Django 6.0, django-ninja con `geojson-pydantic` y MapLibre 5.24, en lugar de lo que decía el encargo? *Recomiendo que sí.*
2. **Base gris y pantalla completa en el teléfono.** Hoy producción usa Calles a color y una franja del 35 %. ¿Confirmas que quieres lo que dice el encargo y no lo que hay? *Recomiendo lo del encargo.*
3. **Crear el repositorio `mayait/sosgalapagos-plataforma` en GitHub, público.** Hoy solo existe como carpeta local.

**Bloquean la fase 2:**

4. **Número de WhatsApp.** ¿El bot lee y responde desde «trabajo», o se añade al OpenWA una tercera sesión con un SIM del proyecto? *Recomiendo el SIM dedicado para responder, y «trabajo» solo para leer mientras llega.*
5. **Modo activo.** El encargo pedía un número con la API oficial que saluda, pide ubicación y foto y devuelve un enlace de un solo uso. ¿Eso también sale por OpenWA, o se descarta?
6. **Nota y foto de vecinos ocultas hasta que coordinación las vea.** Es más seguro, pero la foto tarda en aparecer. *Recomiendo que sí.*

**Pueden esperar a la fase 3 o 4:**

7. **Responsable del tratamiento de datos.** El bot actual nombra a Human Centric SAS BIC; el sitio nuevo es de USFQ Galápagos. ¿Quién figura en el aviso de privacidad?
8. **Comunicado de la portada.** Hoy la portada lleva un comunicado rojo de la emergencia. Al retirar ResponseGrid, ¿pasa a la franja superior del mapa nuevo?
9. **Bot actual.** Sus funciones de moderación por WhatsApp, tareas de voluntarios y difusión dejan de tener destino. ¿Se archivan todas?

## 11. Fases

| Fase | Entrega | Listo cuando |
|---|---|---|
| **0** (antes de programar) | Este plan aprobado. Prototipo de rendimiento probado en un Android de gama baja | Julián aprueba, y el prototipo rinde o hay decisión sobre qué hacer |
| **1** | Mapa con el visual replicado, modelo de datos, formulario y vencimiento | Un reporte hecho desde el teléfono aparece en menos de 5 s, se destiñe y desaparece solo al vencer |
| **2** | API Open311, llaves, cola de verificación, coordinación y WhatsApp por OpenWA | Una institución crea y consulta con su llave, y un mensaje de WhatsApp con ubicación termina publicado |
| **3** | Ajuste por clima, lectura de grupos, feed CAP y archivo | El plazo cambia con la lluvia medida y el archivo se exporta como piden los issues 80, 14, 52 y 64 |
| **4** | Retiro de ResponseGrid | `/` sirve el mapa nuevo y las rutas viejas redirigen |

Al cerrar cada fase entrego un texto breve: qué se hizo, cómo probarlo y qué quedó pendiente.

**Pruebas automáticas desde la fase 1:** vencimiento, renovación, cierre por dos «ya bajó» de dispositivos distintos, duplicados a 50 m y, desde la fase 2, permisos de la API.

## 12. Lo que no pude verificar

- Rendimiento real de MapLibre en un Android de 2 GB. No hay mediciones públicas; se resuelve con la prueba de la fase 0.
- Compatibilidad de `django-tasks-db` con Django 6.1. Por eso se arranca en 6.0.
- La tarifa de Meta para Ecuador sale de tarifarios de proveedores, no del archivo oficial.
- Qué proyecto OpenWA corre en el homeserver, y su documentación de webhooks. Lo reviso al empezar la fase 2.
- Nombres locales de callejones y pasajes: las capas de geodatos traen 31 barrios, todos de Santa Cruz. San Cristóbal e Isabela no tienen barrios cargados. El diccionario arranca incompleto y se completa a mano en el admin.

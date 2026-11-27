# SOS Galápagos · Plataforma de reportes de riesgo

Un mapa único donde la gente reporta **lugares de riesgo o peligro con fecha**, y donde los reportes **se retiran solos** a medida que pasa la emergencia. Sirve a vecinos que buscan por dónde moverse y a equipos de alerta que planifican.

- **Responsable:** Julián Maya, Universidad San Francisco de Quito (USFQ) · jamaya@usfq.edu.ec. Coordinación: USFQ Galápagos.
- **Estado:** fase 1 de 4. **Publicado en https://sosgalapagos.org/riesgos/** desde el 21-nov-2026; cómo, en [`despliegue/servidor.md`](despliegue/servidor.md).
- **Datos del clima para bajar o reproducir** (agentes de IA incluidos): todo en [`clima_galapagos_todo.zip`](https://sosgalapagos.org/clima/datos/descargas/clima_galapagos_todo.zip), que se rehace cada noche (`clima/descargas.py`). Formato, trampas y un script sin dependencias que reproduce el nivel de lluvia: [`sosgalapagos-datos/clima/PARA-AGENTES.md`](https://github.com/mayait/sosgalapagos-datos/blob/main/clima/PARA-AGENTES.md).
- **Repositorios hermanos:** [`sosgalapagos-datos`](https://github.com/mayait/sosgalapagos-datos) (capas de riesgo y clima) y [`sosgalapagos`](https://github.com/mayait/sosgalapagos) (la plataforma actual, que este proyecto reemplazará).

> ⚠️ **Información ciudadana preliminar, no oficial.** Los reportes los hace la comunidad. Emergencias: 911.

## Qué hace hoy (fase 1)

- **Mapa** a pantalla completa en el teléfono y con panel lateral en el escritorio. Abre en calles con la capa de riesgo encima; sin señal usa una base gris propia de 5 MB.
- **Reportar** sin cuenta: foto (de la cámara o de la galería), qué pasa, hasta dónde llega el agua y dónde es. Con una pulsación larga en el mapa se reporta en ese punto.
- **Línea del tiempo** (`/riesgos/informe/`, en el menú del sitio): todos los reportes en orden, hora por hora. Un navegador lleva a cualquier día y los días sin reportes se juntan en una fila. La lluvia no se dibuja: solo deja una nota («Llovió X mm») los días de lluvia fuerte. Filtros por isla, zona, clase y fechas.
- **Descargar capas** (`/riesgos/descargas/`): todas las capas en Shapefile y GeoJSON.
- **Tres clases de aviso:** un peligro, algo bueno (pin amarillo con corazón) y dónde donar o colaborar (pin negro con caja de regalo).
- **Los reportes vencen solos.** Cada tipo tiene su plazo (de 6 a 72 horas). El pin se destiñe con la edad y desaparece al vencer.
- **«Sigue ahí»** renueva el plazo. **Dos «ya bajó»** de teléfonos distintos cierran el reporte.
- **Duplicados:** un reporte del mismo tipo a menos de 50 m de uno vivo cuenta como confirmación.
- **Capas de riesgo:** las que publica el repo de datos bajo `/mapas/…`, en un solo panel. Este es el único mapa del sitio: `/mapas/` redirige aquí desde el 21-nov-2026. El riesgo modelado y las quebradas arrancan encendidos. Cada una se enciende, se apaga y se descarga en Shapefile y GeoJSON, y se baja solo al encenderla.
- **WhatsApp:** un filtro de reglas separa lo que es para el mapa; un modelo de lenguaje (Anthropic o Gemini, se cambia con una variable) saca los datos; el asistente pregunta lo que falte y responde con el enlace. Ver `docs/whatsapp.md`.
- **Ayúdanos a ubicar** (`/riesgos/ubicar/`, con su apartado en la línea del tiempo): las fotos que llegan de los grupos de WhatsApp sin un lugar seguro. Cualquiera marca dónde fue; pasa al mapa cuando dos personas coinciden a menos de 100 m o cuando la ubica coordinación. Las sube cada hora la Mac de coordinación, ya limpias (`despliegue/ingesta/`).
- **Puntos:** publicar suma. Tabla en `/riesgos/puntos/`, solo con el nombre o apodo que cada persona elige.
- **App y avisos:** el mapa se instala en el teléfono y avisa de los peligros confirmados a quien lo pida.
- **Buscador y «Mis puntos»:** la lupa busca calles, barrios, lugares y coordenadas; los puntos propios se guardan solo en el navegador.
- **Capas siempre al día:** si otro equipo publica un modelo nuevo en `/mapas`, el mapa abierto lo recoge en un par de minutos y avisa.
- **Reportes de campo con fotos:** la capa de reportes ciudadanos que publica `/mapas` se abre con su texto y sus fotos.
- **Vista 3D** a pedido: relieve propio (DTM de 1 m de la SGIAR en Santa Cruz y Copernicus en el resto) y edificios con altura. Las capas que lo piden (`extrusion` en el manifiesto) se levantan con su propia altura y el color de su clase: así se ven los edificios de la zona afectada del 21-nov, pintados por gravedad.
- **Lluvia:** franja con el nivel preliminar de la zona, tomado de `/clima`.
- **Instalable** como app. Sin señal guarda los reportes nuevos y los envía al volver la conexión.

Lo que falta está en [`docs/plan-tecnico.md`](docs/plan-tecnico.md): API Open311, coordinación y WhatsApp (fase 2); ajuste por clima, advertencias oficiales y archivo (fase 3); reemplazo de la portada (fase 4).

## Arranque local

En la Mac se usa `container` (Apple). Las capas se traen de lo que publica `sosgalapagos.org/mapas/` y se guarda una copia en `.copia-mapas/`.

```bash
# 1. Imágenes (una vez)
container build -t sosg-postgis -f despliegue/postgis/Dockerfile despliegue/postgis
container build -t sosg-plataforma -f despliegue/Dockerfile .

# 2. Base de datos
container run -d --name sosg-bd -e POSTGRES_USER=plataforma -e POSTGRES_PASSWORD=plataforma -e POSTGRES_DB=plataforma sosg-postgis

# 3. Tablas, zonas y reportes de demostración
despliegue/local.sh migrate
despliegue/local.sh cargar_zonas
despliegue/local.sh sembrar_demo

# 4. Servidor: http://localhost:8000/riesgos/
despliegue/local.sh servidor
```

| Orden | Qué hace |
|---|---|
| `despliegue/local.sh pruebas` | Corre las pruebas |
| `despliegue/local.sh revisar_capas` | Avisa si `/mapas` publica algo que el mapa todavía no sabe dibujar |
| `despliegue/local.sh createsuperuser` | Crea la cuenta para entrar a `/riesgos/admin/` |
| `despliegue/local.sh sembrar_demo --cantidad 200` | Añade 200 reportes al azar, para probar el rendimiento en un teléfono |
| `despliegue/local.sh db_worker` | Trabajador de tareas en segundo plano |
| `despliegue/local.sh reloj` | Encola las tareas periódicas cada minuto |
| `container logs sosg-web` | Registro del servidor |

## Qué hay en el repositorio

```
plataforma/      ajustes y rutas de Django
reportes/        modelos, reglas de vida (reglas.py), formulario, ficha y pruebas
zonas/           diccionario de barrios y sectores, cargado desde geodatos
api/             salida GeoJSON de reportes y llaves de instituciones
entradas/        mensajes que llegan por WhatsApp y esperan verificación
plantillas/      HTML (plantillas de Django con HTMX y Alpine)
estaticos/       mapa/ (código propio), terceros/ (librerías), base/ (mapa base), marca/
despliegue/      Dockerfile, entorno local y fragmentos para el servidor
docs/            plan técnico, visual del mapa, lecciones y capturas
Archivo/         lo que se descarta (nunca se borra)
```

## Licencias

**© 2026 Universidad San Francisco de Quito (USFQ) · SOS Galápagos. Autor: Julián Maya (jamaya@usfq.edu.ec).**

| Qué | Licencia |
|---|---|
| Código | [Apache 2.0](LICENSE): se puede usar, copiar, modificar y redistribuir dando crédito. El aviso de autoría de cada archivo y el [`NOTICE`](NOTICE) se conservan |
| Datos, modelos y textos propios | [CC BY 4.0](LICENCIA-DATOS.md): se pueden copiar, adaptar y usar, también con fines comerciales, dando crédito |
| Datos de terceros (IERSE, GSC, FCD, INAMHI…) | La licencia de cada fuente, publicada con su permiso: [`LICENCIA-DATOS.md`](LICENCIA-DATOS.md) |

Todo uso da crédito a **SOS Galápagos · Universidad San Francisco de Quito (USFQ) · Julián Maya <jamaya@usfq.edu.ec>**. Las librerías, las tipografías, el mapa base (OpenStreetMap, ODbL) y los logotipos de la USFQ conservan sus propias condiciones; el detalle está en [`NOTICE`](NOTICE). Historia: hasta el 22-nov-2026, Apache 2.0 y CC BY 4.0; del 22 al 23-nov-2026, derechos reservados y CC BY-NC-ND 4.0; desde el 23-nov-2026, de nuevo Apache 2.0 y CC BY 4.0 (`Archivo/licencias-anteriores/`).

El análisis y el código se prepararon con asistencia de agentes de inteligencia artificial.

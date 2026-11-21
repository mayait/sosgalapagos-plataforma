# SOS Galápagos · Plataforma de reportes de riesgo

Un mapa único donde la gente reporta **lugares de riesgo o peligro con fecha**, y donde los reportes **se retiran solos** a medida que pasa la emergencia. Sirve a vecinos que buscan por dónde moverse y a equipos de alerta que planifican.

- **Responsable:** Julián Maya, Universidad San Francisco de Quito (USFQ) · jamaya@usfq.edu.ec. Coordinación: USFQ Galápagos.
- **Estado:** fase 1 de 4, en desarrollo. **Todavía no está publicado.**
- **Repositorios hermanos:** [`sosgalapagos-datos`](https://github.com/mayait/sosgalapagos-datos) (capas de riesgo y clima) y [`sosgalapagos`](https://github.com/mayait/sosgalapagos) (la plataforma actual, que este proyecto reemplazará).

> ⚠️ **Información ciudadana preliminar, no oficial.** Los reportes los hace la comunidad. Emergencias: 911.

## Qué hace hoy (fase 1)

- **Mapa** a pantalla completa en el teléfono y con panel lateral en el escritorio. Base gris propia de 5 MB que funciona sin señal.
- **Reportar** sin cuenta: foto, qué pasa, hasta dónde llega el agua y dónde es.
- **Los reportes vencen solos.** Cada tipo tiene su plazo (de 6 a 72 horas). El pin se destiñe con la edad y desaparece al vencer.
- **«Sigue ahí»** renueva el plazo. **Dos «ya bajó»** de teléfonos distintos cierran el reporte.
- **Duplicados:** un reporte del mismo tipo a menos de 50 m de uno vivo cuenta como confirmación.
- **Capas de riesgo:** las mismas de `/mapas`, en un solo panel. Cada una se enciende, se apaga y se descarga en Shapefile y GeoJSON, y se baja solo al encenderla.
- **Reportes de campo con fotos:** la capa de reportes ciudadanos que publica `/mapas` se abre con su texto y sus fotos.
- **Vista 3D** a pedido: relieve del terreno y edificios con altura.
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

# 4. Servidor: http://localhost:8000/mapa/
despliegue/local.sh servidor
```

| Orden | Qué hace |
|---|---|
| `despliegue/local.sh pruebas` | Corre las pruebas |
| `despliegue/local.sh createsuperuser` | Crea la cuenta para entrar a `/admin/` |
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

**© 2026 Universidad San Francisco de Quito (USFQ).** Código bajo [Apache 2.0](LICENSE), con el aviso [`NOTICE`](NOTICE). Reportes y textos bajo [CC BY 4.0](LICENCIA-CC-BY-4.0.txt). Las librerías, las tipografías, el mapa base (OpenStreetMap, ODbL) y los logotipos de la USFQ conservan sus propias condiciones; el detalle está en `NOTICE`.

El análisis y el código se prepararon con asistencia de agentes de inteligencia artificial.

# Visual del mapa: qué se replica de ResponseGrid y qué cambia

*Revisado el 21-nov-2026 sobre el sitio en producción y el código de `mayait/sosgalapagos` (commit `2c81d04`).*

Este documento describe **cómo se ve y cómo se comporta** el mapa de `sosgalapagos.org/e/galapagos-2026`, que es el que le gusta a la gente, y fija qué se rehace en el mapa nuevo. Es una descripción de diseño. **No se copia código**: ResponseGrid es AGPL-3.0 y este proyecto es Apache 2.0. Todo se escribe de nuevo, con otra librería (MapLibre GL JS en lugar de Leaflet) y sin leer el código viejo mientras se programa.

## 1. Cómo es hoy

Capturas en [`capturas/`](capturas/):

| Archivo | Qué muestra |
|---|---|
| `01-escritorio-mapa-y-panel.jpg` | Escritorio: mapa fijo a la izquierda, contenido a la derecha |
| `02-escritorio-panel-capas-abierto.jpg` | Escritorio con el panel Capas abierto |
| `03-movil-390-cerrado-y-capas.png` | Teléfono (390 px): mapa arriba y panel Capas abierto |
| `04-mapas-visor-actual.jpg` | `/mapas`, el visor de capas que se conserva |
| `05-clima-actual.jpg` | `/clima`, de donde sale la franja de lluvia |
| `10-nuevo-movil-mapa.jpg` | **Mapa nuevo** en el teléfono (fase 1, en local) |
| `11-nuevo-escritorio-mapa.png` | **Mapa nuevo** en el escritorio, con la lista de lo que hay cerca |
| `12-nuevo-escritorio-capas-y-ficha.png` | **Mapa nuevo** con el panel Capas y la ficha de un reporte |
| `14-nuevo-movil-fotos-3d-formulario.jpg` | **Mapa nuevo** en teléfono: reporte de campo con fotos, vista 3D y formulario a 360 px |
| `16-nuevo-3d-relieve-propio.jpg` | **Mapa nuevo:** vista 3D con el relieve propio (DTM de la SGIAR y Copernicus) |
| `15-nuevo-escritorio-3d-y-fotos.jpg` | **Mapa nuevo:** vista 3D de Santa Cruz y fotos de un reporte de campo |
| `13-nuevo-capas-con-descargas.jpg` | **Mapa nuevo:** panel Capas con las descargas de cada capa, como en `/mapas` |

### Vista inicial y disposición

- **Vista inicial:** centro de Puerto Ayora, latitud −0,7435 y longitud −90,3145, zoom 16 (nivel de calles). No se encuadra a los puntos: siempre abre ahí.
- **Escritorio (1 024 px o más):** el mapa ocupa el 58 % del ancho, pegado bajo la barra negra de 52 px y con toda la altura restante. Queda fijo mientras la columna derecha se desplaza.
- **Teléfono:** el mapa es una franja pegada arriba, del 35 % del alto de la pantalla (entre 220 y 350 px; en un teléfono de 390 × 760 mide 264 px). El contenido corre por debajo. **No es pantalla completa.**
- **Rueda del ratón:** no hace zoom, para que la página se pueda desplazar. En el teléfono el zoom es con dos dedos.

### Mapa base

- En producción el mapa base por defecto es **Calles** (teselas de OpenStreetMap, a color). El selector ofrece Calles, Satélite y Topográfico. **No hay opción gris claro en la plataforma.**
- La base gris claro («Claro», Esri Light Gray) sí existe en el manifiesto de `mapas-galapagos/datos/capas.json` del repo de datos, donde es la opción por defecto.

### Pines

- Pin clásico en forma de gota, de 25 × 41 px, con sombra. El color indica el estado:

  | Color | Estado hoy |
  |---|---|
  | Verde | Operativo |
  | Amarillo | Saturado |
  | Naranja | En pausa |
  | Azul | Cerrado |
  | Rojo | Petición de ayuda |

- **Clusters:** los pines cercanos se agrupan en un círculo con el número de puntos (radio de agrupación de 60 px). Al acercarse se separan.
- **Leyenda de pines:** una píldora blanca abajo a la izquierda, con un punto de color y el nombre de cada estado.
- **Globo al tocar:** nombre en negrita, tipo, lugar y un enlace para avisar de un problema.
- **Botón de ubicación:** círculo blanco de 40 px abajo a la derecha. Centra el mapa en la posición del teléfono.
- **Carga de puntos:** se pide solo lo que cae en la vista más un margen del 35 %, con una espera de 0,4 s tras mover el mapa.

### Panel Capas

- Cerrado es un botón blanco pequeño, **Capas**, arriba a la derecha. Siempre arranca cerrado.
- Abierto es una tarjeta blanca, casi opaca, con esquinas redondeadas y sombra, de hasta 320 px de ancho, con barra de desplazamiento propia. No deja que los gestos pasen al mapa.
- De arriba abajo trae:
  1. **Ir a:** píldoras con Santa Cruz, Puerto Ayora, San Cristóbal e Isabela.
  2. **Mapa base:** selector de un solo botón activo.
  3. **Grupos de capas:** título en mayúsculas pequeñas y un interruptor por capa, con la fuente debajo en gris.
  4. Con la capa encendida aparecen su descripción en cursiva y su **leyenda** (cuadro, línea o punto de color con su texto).
  5. Si la capa solo se ve de cerca, un aviso: «acércate hasta el zoom N».
  6. Botón para **subir un GeoJSON propio**, que se dibuja en naranja discontinuo y no se guarda.
- Grupos en producción: Puntos clave, Emergencia en curso, Parque Nacional y zona agrícola, Zonas inundables, Quebradas y drenaje, Zonas pobladas, Vías y evacuación, Relieve.

### Capas

- Se describen en un **manifiesto** (`capas.json`): grupos, capas, estilo, clasificación por una propiedad, leyenda, zoom mínimo y si arrancan encendidas.
- **Se cargan solo al encenderse.** Las que arrancan encendidas se bajan al abrir.
- **En el teléfono arrancan menos capas** que en el escritorio: se apagan el Parque Nacional, la susceptibilidad, los cauces adicionales y los nombres de vías.
- Las capas van **debajo de los pines**, en el orden del manifiesto.
- Los **rótulos** de barrios y calles solo se ven desde el zoom 15.
- El relieve se mezcla multiplicando colores en el escritorio. En pantallas táctiles se pinta con opacidad normal, porque esa mezcla congelaba Safari en iPhone.

### Colores e interfaz

- Sistema USFQ «WE WANT MORE»: rojo `#E11B22`, negro y blanco. Títulos en Zalando Sans Expanded y texto en Helvetica Neue.
- Líneas de separación gris `#E5E5E5`, texto secundario `#666666`, tarjetas con esquinas de 16 px.
- Los colores de estado (verde, amarillo, naranja, rojo) son señales funcionales y no cambian con la marca.

## 2. Qué se replica en el mapa nuevo

| Elemento | Cómo queda |
|---|---|
| Vista inicial | Puerto Ayora, −0,7435 / −90,3145, zoom 16 |
| Panel Capas | Un solo panel arriba a la derecha, cerrado al abrir, con Ir a, mapa base, interruptores por grupo y leyendas |
| Capas | Leídas del manifiesto, debajo de los pines y cargadas solo al encenderse |
| Menos capas en el teléfono | Igual que hoy, con una marca por capa en el manifiesto |
| Pines por estado y clusters | Color por estado del reporte, agrupados con el número dentro |
| Leyenda de pines | Píldora blanca abajo a la izquierda |
| Botón de ubicación | Círculo blanco abajo a la derecha |
| Rótulos | Barrios y calles solo de cerca |
| Escritorio | Mapa fijo y panel lateral que se desplaza |
| Marca | Rojo USFQ, negro y blanco, misma tipografía |

## 3. Qué cambia, y por qué

| Cambio | Motivo |
|---|---|
| **Teléfono a pantalla completa**, con hoja inferior deslizable | Lo pide el encargo. Hoy es una franja del 35 % |
| **Base gris claro por defecto** | Lo pide el encargo. Hoy la base es Calles a color. Con la base gris los pines y las zonas de riesgo resaltan más |
| **Base propia en PMTiles** en lugar de teselas de terceros | Funciona con conexión lenta y se puede guardar en el teléfono |
| **Los pines se destiñen con la edad** | Un reporte viejo no debe pesar igual que uno reciente |
| **Pin con icono del tipo de riesgo** | Hoy el pin solo dice el estado. El nuevo dice además qué es (agua en la vía, cable caído…) |
| **Colores de pin con otro significado** | Los estados cambian: por verificar, confirmado, bajando y cerrado |
| **Franja de lluvia y fichas de tiempo** (ahora, 24 h, todo el evento) | Son nuevas; no existen hoy |
| **Botón grande Reportar** | Es la acción principal del producto nuevo |
| Sin botón de subir GeoJSON al inicio | Se usa poco en la portada. Sigue disponible en `/mapas` |
| **Descargas por capa y botones «Apagar todas» y «Volver a las iniciales»** | Son los principios de `/mapas`, que se mantienen: toda capa se enciende, se apaga y se descarga. El panel lee el manifiesto y el índice de descargas de `/mapas` |
| Fondo blanco en todo, sin modo oscuro | Lo pide el encargo. La barra superior negra de hoy desaparece |

### Colores de estado propuestos

| Estado | Color | Nota |
|---|---|---|
| Por verificar | Gris `#6B7280`, borde discontinuo | Todavía no lo vio un coordinador |
| Confirmado | Rojo USFQ `#E11B22` | Peligro vigente |
| Bajando | Ámbar `#D97706` | Alguien avisó que ya bajó; falta la segunda confirmación |
| Cerrado | No se dibuja en «ahora». En «24 h» y «todo el evento» va en gris claro | Queda en el archivo |

La gravedad se marca con el tamaño y un anillo: «peligro de vida» lleva anillo negro. El color no depende solo del tono: cada estado tiene además un icono o un borde distinto, para quien no distingue rojo de ámbar.

**No se usa verde en los reportes.** El mapa nunca dice «zona segura». El verde queda reservado para la capa de lugares seguros (refugios, puntos de encuentro y terreno alto).

## 4. Puntos por confirmar con Julián

1. **Base gris claro y pantalla completa en el teléfono** no son lo que hay hoy en producción (hoy: Calles a color y franja del 35 %). Este documento asume que el encargo describe lo que se quiere, no lo que existe.
2. **«Refugio», no «albergue».** El encargo dice «albergues», pero la regla del proyecto (`AGENTS.md` y `CONTRIBUIR.md` del repo de datos) es decir siempre «refugio». Este documento usa «refugio».
3. **Colores de estado:** la tabla de arriba es una propuesta.

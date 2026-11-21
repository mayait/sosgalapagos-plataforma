# Plan para dar de baja el visor de `/mapas`

*Revisado el 21-nov-2026 sobre `/mapas` (versión `ef10236`, 60 capas) y `/riesgos/` en producción.*

**Conclusión: todavía no es buen momento.** Hoy `/riesgos/` ya muestra todas las capas de `/mapas` y permite descargarlas, pero al visor de `/mapas` le quedan cinco herramientas que `/riesgos/` no tiene, hay una inundación en curso y el equipo de datos publica en `/mapas` varias veces al día. La baja se puede hacer en cuanto se cumplan los cinco criterios de la [sección 3](#3-cuándo-es-buen-momento).

Una precisión que cambia todo el plan: **lo que se da de baja es el visor, no los datos.** `/riesgos/` lee de `/mapas/` el manifiesto, las capas, las descargas, las teselas y las fotos. Esas direcciones tienen que seguir existiendo.

## Estado y recomendación (21-nov-2026, tarde)

**Recomendación: quedarse solo con `/riesgos/`.** Mantener dos visores ya costó trabajo doble el mismo día: tres manifiestos distintos, un marcador nuevo (`corazon`) que cada visor dibuja a su manera, y mejoras que el equipo de datos hace en un visor que va a desaparecer. Cada día que conviven, la diferencia crece.

Lo que no conviene es hacerlo de golpe hoy. Hay una advertencia del INAMHI vigente hasta el 24-nov, y el visor de `/mapas` tiene herramientas que usan los equipos técnicos y que `/riesgos/` aún no tiene.

| Criterio | Estado |
|---|---|
| 1. Paridad de herramientas | **0 de 5.** Faltan buscador, punto de análisis, mis puntos, descarga de imagen y exposición por isla |
| 2. Probado en teléfonos reales | **Pendiente.** Solo simulación en escritorio |
| 3. Siete días estables | **Día 1.** En producción desde el 21-nov, 14:17 |
| 4. Acuerdo con el equipo de datos | **Sin hablar.** Siguen mejorando su visor (hoy: versión para teléfono, enlaces a lugares, corazones) |
| 5. Fuera de la fase aguda | **No.** Advertencia n.º 89 del INAMHI vigente hasta el 24-nov |

Avances desde la mañana que acercan la baja: las descargas de capas ya están en `/riesgos/descargas/` y en la portada; los enlaces a lugares son los mismos; `/riesgos/` dibuja las 60 capas y se actualiza solo con cada publicación.

**Camino corto que propongo:**

1. **Hoy:** avisar al equipo de datos de que el visor único será `/riesgos/` y que dejen de invertir en el suyo (criterio 4). Es lo que más trabajo ahorra.
2. **Esta semana:** construir en `/riesgos/` el buscador, el punto de análisis y la descarga de imagen. Julián decide si «Mis puntos» y la tabla de exposición se hacen o se abandonan.
3. **Cuando pase la advertencia y con una prueba en teléfono real:** redirección temporal de `/mapas/` a `/riesgos/` (paso 3 de este plan). Fecha más temprana razonable: la semana del 30-nov.

## 1. Qué hay bajo `/mapas` y qué pasa con cada cosa

| Dirección | Qué es | Quién la usa | Qué pasa |
|---|---|---|---|
| `/mapas/` (`index.html`) | El visor Leaflet | Personas | **Se da de baja**: redirige a `/riesgos/` |
| `/mapas/capas.json` | Manifiesto de grupos, capas y estilos | `/riesgos/` | Se queda |
| `/mapas/descargas.json` | Índice de descargas | `/riesgos/` | Se queda |
| `/mapas/version.txt` | Versión de cada publicación | `/riesgos/` | Se queda |
| `/mapas/datos/…` | Capas en GeoJSON, imágenes de relieve y fotos de reportes | `/riesgos/`, QGIS de terceros | Se queda |
| `/mapas/descargas/…` | Shapefile y GeoJSON en zip | Enlaces de descarga, la portada | Se queda |
| `/mapas/teselas/…` | Teselas del DTM | `/riesgos/` | Se queda |

El repo de datos sigue publicando igual (`servidores/publicar.sh mapas`). No hay que cambiar su flujo.

## 2. Qué tiene el visor de `/mapas` y qué le falta a `/riesgos/`

| Función del visor de `/mapas` | En `/riesgos/` | Falta |
|---|---|---|
| Encender y apagar capas, con leyendas | Sí | — |
| Descargar cada capa y todas juntas | Sí, en el panel y en `/riesgos/descargas/` | — |
| Mapas base (calles, satélite, topográfico) | Sí, más la base gris propia | — |
| Reportes ciudadanos con fotos | Sí, con visor de fotos | — |
| Buenas noticias y ayuda (corazones) | Sí | — |
| Dónde estoy | Sí | — |
| Enlaces a un lugar (`#ptoayora`, `#lat,lon,zoom`) | Sí, con los mismos nombres | — |
| Saltar a una isla o al archipiélago | Sí | — |
| **Buscador** de calle, barrio, lugar o coordenadas | No | **Sí** |
| **Punto de análisis** (A, B, C): riesgo, cota y cuenca en un punto, con resumen para copiar | No | **Sí** |
| **Mis puntos**: guardados en el navegador y exportables a GeoJSON | No | **Sí** |
| **Descargar imagen** del mapa con su leyenda y **modo captura** | No | **Sí** |
| **Exposición estimada por isla** (tabla) | No | **Sí** |
| Leyenda flotante de las capas encendidas | Solo dentro del panel Capas | Parcial |
| Cota del terreno bajo el cursor | No (hay vista 3D) | Parcial |

Lo que `/riesgos/` tiene y `/mapas` no: reportar, vencimiento de los avisos, informe con línea del tiempo y lluvia, vista 3D, pista al pasar el ratón, actualización en vivo de las capas y uso sin señal.

Las cinco funciones en negrita son las que usan los equipos técnicos. Sin ellas, dar de baja el visor les quita herramientas de trabajo.

## 3. Cuándo es buen momento

Se cumplen los cinco:

1. **Paridad:** `/riesgos/` tiene buscador, punto de análisis, mis puntos, descarga de imagen y la tabla de exposición. O Julián decide por escrito cuáles se abandonan.
2. **Probado en teléfonos reales**, incluido un Android de gama baja, con las capas de riesgo encendidas. Hoy todas las pruebas son en un navegador de escritorio.
3. **Estabilidad:** siete días seguidos de `/riesgos/` en producción sin incidentes que obliguen a volver atrás.
4. **Acuerdo con el equipo de datos:** saben que su visor desaparece, que sus publicaciones siguen igual y que los cambios de visualización se piden en `sosgalapagos-plataforma`.
5. **Fuera de la fase aguda.** No se cambia la dirección que la gente ya conoce durante una inundación ni mientras se publican reportes cada hora.

**Estado al 21-nov-2026:** 0 de 5. El criterio 5 por sí solo descarta hacerlo hoy.

## 4. Pasos

Cada paso se puede deshacer y ninguno borra nada.

**Paso 0 · Convivencia (ya en marcha).** Los dos visores funcionan. La portada enlaza `/riesgos/` y la página de descargas.

**Paso 1 · Paridad.** Se construyen en `/riesgos/` las cinco funciones que faltan, en este orden: buscador, punto de análisis, descarga de imagen, mis puntos y exposición por isla. El manifiesto ya trae la configuración del buscador (`buscar`).

**Paso 2 · Aviso (7 días).** El visor de `/mapas` muestra una franja: «Este visor se muda a sosgalapagos.org/riesgos», con un botón para ir. Es un cambio en `geodatos/web/index.html`, del repo de datos.

**Paso 3 · Redirección temporal.** En el `Caddyfile` del sitio, dentro del bloque de `/mapas`:

```
	@visor path / /index.html
	redir @visor /riesgos/ 302
```

- Solo cambia la página del visor. Todo lo demás de `/mapas/…` se sigue sirviendo.
- La redirección es temporal (302) para poder volver atrás sin que los navegadores la recuerden.
- El navegador conserva lo que va tras `#`, así que `/mapas/#la-cascada` llega a `/riesgos/#la-cascada`. Los enlaces de los informes en PDF siguen funcionando.
- El visor anterior queda accesible en `/mapas/visor-anterior/` durante la transición. No se borra.

**Paso 4 · Actualizar lo que apunta a `/mapas`.**

- Portada (`portada-galapagos.ts`): se quita la tarjeta «Mapas y capas».
- Repo de datos: `README.md`, `CITATION.cff`, `servidores/README.md` y el bloque del árbol de repositorios de los `AGENTS.md`.
- Enlaces internos de `/riesgos/` («las capas de riesgo» en la firma).
- `/clima`, si enlaza al visor.

**Paso 5 · Redirección definitiva (30 días después).** El 302 pasa a 301. El visor anterior se mueve a una carpeta `Archivo` del servidor.

## 5. Cómo volver atrás

- **Pasos 2 a 4:** se revierte el commit correspondiente y se recarga Caddy en caliente (`despliegue/servidor.md`, sección 2). El visor de `/mapas` vuelve en segundos.
- **Paso 5:** un 301 lo recuerdan los navegadores. Por eso va al final y tras 30 días sin problemas.

## 6. Riesgos

| Riesgo | Qué se hace |
|---|---|
| Alguien da de baja la carpeta entera de `/mapas` y rompe `/riesgos/` | Este documento y una nota en `servidores/README.md`: `/mapas/` sigue siendo la publicación de datos |
| Enlaces impresos o compartidos a `/mapas/#…` | La redirección conserva el `#`; los nombres de lugar son los mismos |
| El equipo de datos sigue mejorando un visor que va a desaparecer | Criterio 4: avisarles antes del paso 1 |
| `/riesgos/` va lento en teléfonos con todas las capas | Criterio 2; si pasa, la susceptibilidad se sirve en teselas vectoriales antes de seguir |
| Un técnico pierde sus «Mis puntos» guardados en el navegador de `/mapas` | Están guardados por dirección. Antes del paso 3, el aviso del paso 2 les pide exportarlos a GeoJSON |

## 7. Quién hace qué

| Tarea | Repositorio | Quién decide |
|---|---|---|
| Funciones que faltan (paso 1) | `sosgalapagos-plataforma` | Julián |
| Franja de aviso en el visor (paso 2) | `sosgalapagos-datos` | Equipo de datos |
| Redirección en Caddy (pasos 3 y 5) | `sosgalapagos` | Julián, con aprobación explícita |
| Enlaces y documentación (paso 4) | Los tres | Cada equipo en su repo |

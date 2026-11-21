# Baja del visor de `/mapas`

**Hecho el 21-nov-2026.** `/riesgos/` es el único mapa de `sosgalapagos.org`. Quien entra a `/mapas/` llega a `/riesgos/`.

Julián lo decidió ese día: mantener dos visores ya costaba trabajo doble, y lo que el visor de `/mapas` tenía de más o se llevó a `/riesgos/` o no hacía falta. Se hizo sin esperar a los cinco criterios de la sección 3 (ver «Lo que queda abierto»).

Una precisión que no cambia: **se dio de baja el visor, no los datos.** `/riesgos/` lee de `/mapas/` el manifiesto, las capas, las descargas, las teselas y las fotos. Esas direcciones siguen existiendo y no se pueden retirar.

## Qué se hizo

| Paso | Dónde | Estado |
|---|---|---|
| Buscador (lupa junto a «Capas») y «Mis puntos» en `/riesgos/` | `sosgalapagos-plataforma`, `estaticos/mapa/buscar.js` | Hecho, en producción |
| Enlaces bajo la firma: lluvia en vivo, descarga de capas y repositorio | `plantillas/parciales/firma.html` | Hecho |
| Redirección 302 de `/mapas`, `/mapas/` y `/mapas/index.html` a `/riesgos/` | `sosgalapagos`, `deploy/sosgalapagos/Caddyfile` | Hecho, en producción |
| Portada: botón del encabezado y pie a `/riesgos/`; se quita la tarjeta «Mapas y capas» | `sosgalapagos`, `portada-galapagos.ts` | Hecho, en producción |
| El visor sale del repo de datos y deja de generarse | `sosgalapagos-datos`: `Archivo/visor-mapas/`, `10_publicar_web.py` | Hecho |
| Documentación y árbol de repositorios (ahora seis) | Los seis `AGENTS.md` | Hecho |

## Qué pasó con cada función del visor

| Función | Decisión |
|---|---|
| Capas, leyendas, mapas base, descargas, enlaces a lugares | Ya estaban en `/riesgos/` |
| Buscador de calle, barrio, lugar o coordenadas | Llevado a `/riesgos/` |
| «Mis puntos» | Llevado a `/riesgos/`. Usa la misma clave del navegador (`sosgalapagos-mapas-mis-puntos-v1`) y el mismo formato: como las dos direcciones son del mismo dominio, nadie perdió lo que tenía guardado |
| Punto de análisis (riesgo, cota y cuenca en un punto) | No se lleva: quien lo necesite descarga las capas |
| Descargar imagen con leyenda y modo captura | No se lleva |
| Tabla de exposición por isla | Irá como PDF en las descargas de la portada (pendiente, equipo de datos) |
| Cota bajo el cursor | No se lleva: está la vista 3D |

## Cómo volver atrás

En el `Caddyfile` del sitio se quitan las dos líneas `@visor` / `redir @visor /riesgos/ 302` del bloque de `/mapas`, se cambia `redir /mapas /riesgos/ 302` por `redir /mapas /mapas/ permanent` y se recarga Caddy en caliente (`despliegue/servidor.md`, sección 2). El `index.html` del visor sigue en el servidor (`/srv/sosgalapagos-mapas/`): la publicación de datos ya no lo sube ni lo borra. Su fuente está en `Archivo/visor-mapas/` del repo de datos. La redirección es temporal (302) a propósito.

## Lo que queda abierto

- **Probar en teléfonos reales**, incluido un Android de gama baja. Todas las pruebas son en un navegador de escritorio a 360 y 390 px.
- **Avisar al equipo de datos**: sus publicaciones siguen igual (`servidores/publicar.sh mapas`), pero los cambios de visualización ahora se piden en `sosgalapagos-plataforma`.
- **Tabla de exposición por isla** en PDF.
- **Pasar el 302 a 301** cuando lleve unas semanas sin problemas (un 301 lo recuerdan los navegadores).
- `/clima/` enlazaba al visor para la capa de refugios. El enlace ya apunta a `/riesgos/` en el repo de datos; llega al servidor con el próximo `servidores/publicar.sh clima`. Mientras tanto la redirección lo cubre.

---

*Lo que sigue es el plan original, tal como se escribió la mañana del 21-nov-2026. Se conserva como registro.*

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
| Mis puntos: guardados en el navegador y exportables a GeoJSON | No | No se hace (decisión de Julián) |
| **Descargar imagen** del mapa con su leyenda y **modo captura** | No | **Sí** |
| Exposición estimada por isla (tabla) | No | No se hace (decisión de Julián) |
| Leyenda flotante de las capas encendidas | Solo dentro del panel Capas | Parcial |
| Cota del terreno bajo el cursor | No (hay vista 3D) | Parcial |

Lo que `/riesgos/` tiene y `/mapas` no: reportar, vencimiento de los avisos, informe con línea del tiempo y lluvia, vista 3D, pista al pasar el ratón, actualización en vivo de las capas y uso sin señal.

Las tres funciones en negrita son las que usan los equipos técnicos y hay que llevar a `/riesgos/`. «Mis puntos» y la tabla de exposición se quedan fuera por decisión de Julián: quien tenga puntos guardados en `/mapas` debe exportarlos antes de la baja.

## 3. Cuándo es buen momento

Se cumplen los cinco:

1. **Paridad:** `/riesgos/` tiene buscador, punto de análisis y descarga de imagen. «Mis puntos» y la tabla de exposición por isla no se llevan a `/riesgos/` (decisión de Julián, 21-nov-2026).
2. **Probado en teléfonos reales**, incluido un Android de gama baja, con las capas de riesgo encendidas. Hoy todas las pruebas son en un navegador de escritorio.
3. **Estabilidad:** siete días seguidos de `/riesgos/` en producción sin incidentes que obliguen a volver atrás.
4. **Acuerdo con el equipo de datos:** saben que su visor desaparece, que sus publicaciones siguen igual y que los cambios de visualización se piden en `sosgalapagos-plataforma`.
5. **Fuera de la fase aguda.** No se cambia la dirección que la gente ya conoce durante una inundación ni mientras se publican reportes cada hora.

**Estado al 21-nov-2026:** 0 de 5. El criterio 5 por sí solo descarta hacerlo hoy.

## 4. Pasos

Cada paso se puede deshacer y ninguno borra nada.

**Paso 0 · Convivencia (ya en marcha).** Los dos visores funcionan. La portada enlaza `/riesgos/` y la página de descargas.

**Paso 1 · Paridad.** Se construyen en `/riesgos/` las tres funciones que faltan, en este orden: buscador, punto de análisis y descarga de imagen. Antes de la baja, la tabla de exposición por isla debe quedar en algún sitio (un informe en PDF de la portada, por ejemplo) o darse por retirada. El manifiesto ya trae la configuración del buscador (`buscar`).

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

# Recolector anterior, corriendo dentro de Django

Estos módulos vienen de `sosgalapagos-datos/clima/recolector/` (22-nov-2026) y se dejan **casi sin tocar**: son los que recogen cada fuente, con sus conversiones de unidades y de horas ya probadas en producción. No se reescribieron para no arriesgar esas conversiones en plena temporada de lluvias.

Lo que cambió es dónde escriben. Reciben una conexión de `clima/compat.py`, que habla con PostgreSQL a través de tres vistas (`obs`, `estaciones`, `corridas`) con la misma forma que las tablas de la base SQLite original. Las crea la migración `0007`.

| Archivo | Cambios respecto del original |
|---|---|
| `recolector.py` | `http_json` acepta una respuesta vacía (204) como «nada nuevo» |
| `danadas.py` | Reescrito: lee los sensores dañados del admin (`EstacionDanada`), no de un JSON |
| `fuentes_extra.py`, `pronostico.py`, `mareas.py`, `estacionalidad.py` | Ninguno |

Quien los llama: `clima/fuentes.py` (recoger) y `clima/panel.py` (mareas, pronóstico y estacionalidad del panel).

Al mejorar una fuente, lo natural es sacarla de aquí a un módulo propio que escriba directo con los modelos de Django. Hasta entonces, **un arreglo de una fuente se hace aquí**, no en el repo de datos.

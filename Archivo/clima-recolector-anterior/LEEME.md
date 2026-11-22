# Recolector de clima anterior (archivado el 22-nov-2026)

Aquí queda, sin uso, el código con que se hizo el relevo del clima a esta aplicación:

- `recolector.py`, `fuentes_extra.py`, `pronostico.py`, `mareas.py`, `estacionalidad.py`: el recolector
  original (escrito para SQLite, en `sosgalapagos-datos/clima/recolector/`), tal como corrió dentro de
  Django durante unas horas.
- `compat.py`: la conexión que traducía sus consultas de SQLite a PostgreSQL.
- `sincronizar.py` y `clima_sincronizar.py`: la copia de la base SQLite a PostgreSQL.

**Nada de esto se importa ni se ejecuta.** Lo reemplazan los módulos nativos de `clima/`:
`clima/fuentes/` (un módulo por fuente), `clima/senal.py`, `clima/mareas.py`, `clima/estacionalidad.py`,
`clima/descargas.py` y `clima/satelite/`. Se conserva solo como referencia de cómo era
(regla del proyecto: lo que se descarta se mueve a `Archivo`, no se borra).

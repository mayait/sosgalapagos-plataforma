# Instrucciones para agentes y colaboradores

Plataforma de reportes de riesgo de SOS Galápagos: un mapa único donde la gente reporta lugares de peligro con fecha, y donde los reportes se retiran solos. Lee primero [`README.md`](README.md) y [`docs/plan-tecnico.md`](docs/plan-tecnico.md).

**Estás en:** `sosgalapagos-plataforma`, el sexto repositorio de SOS Galápagos. El árbol de los otros cinco está en el `AGENTS.md` de [`sosgalapagos-datos`](https://github.com/mayait/sosgalapagos-datos/blob/main/AGENTS.md).

## Reglas duras

1. **No se toca producción ni el servidor sin aprobación explícita de Julián.** Subir a `main` no publica nada.
2. **Nunca se borran archivos, datos ni contenedores.** Lo que se descarta se mueve a `Archivo/`. Un reporte cerrado tampoco se borra: queda en el archivo.
3. **No se rompen `/mapas` ni `/clima`.** Este proyecto solo lee lo que publican.
4. **No se copia código de ResponseGrid** (`mayait/sosgalapagos`, AGPL-3.0). Este proyecto es Apache 2.0. El visual se rehace desde [`docs/visual-mapa.md`](docs/visual-mapa.md).
5. **Privacidad:**
   - Ningún dato personal público. Nunca nombres de menores ni cédulas.
   - Las fotos se guardan sin metadatos (`reportes/fotos.py`).
   - Los teléfonos nunca en claro: solo un resumen con clave.
   - La foto y la nota de un vecino no se publican hasta que coordinación las revise.
6. **El mapa nunca dice «zona segura».** Donde no hay reportes dice «sin reportes activos». Hay una prueba que lo vigila.
7. **Se dice «refugio», nunca «albergue».**
8. **Repositorio público.** Sin secretos, sin endpoints de las fuentes de clima y nada de los repositorios privados.
9. **Se trabaja en ramas con pull request.**

## Convenciones

- **Idioma:** español en el código, los comentarios, los commits y los textos visibles. Los nombres que exige Django (`models.py`, `admin.py`, `migrations/`) se quedan como están.
- **Commits:** `tipo(ámbito): descripción`, sin líneas `Co-Authored-By`. Los agentes de Julián usan `Julian Maya <1101119+mayait@users.noreply.github.com>`.
- **Reglas de vida del reporte:** toda la lógica está en `reportes/reglas.py`, con pruebas en `reportes/pruebas/`. Las vistas y la API solo llaman. Un cambio de regla lleva su prueba.
- **Umbrales:** en `plataforma/ajustes.py`, marcados como preliminares.
- **Sin paso de compilación.** El JavaScript va tal cual en `estaticos/mapa/`. Las librerías de terceros están en `estaticos/terceros/` con versión fija; no se cargan desde un CDN.
- **Marca:** sistema USFQ «WE WANT MORE». Solo rojo `#E11B22`, negro y blanco; fondo blanco y sin modo oscuro. El ámbar y el gris de los pines son señales del mapa, no de marca. La firma «MORE HUMANS, MORE DRAGONS.» va discreta, al pie.
- **Horas:** en la base, UTC. En pantalla, hora de Galápagos (UTC−6).
- **En la Mac no hay Docker:** se usa `container` (Apple). Ver `despliegue/local.sh`.
- **Lecciones:** los errores y las decisiones se anotan en [`docs/lecciones.md`](docs/lecciones.md).

## Mapa rápido

| Quiero… | Voy a… |
|---|---|
| Cambiar un plazo, un duplicado o una confirmación | `reportes/reglas.py` y `plataforma/ajustes.py` |
| Cambiar un tipo de riesgo | El admin (`/admin/`), no el código |
| Tocar el formulario | `plantillas/reportes/reportar.html` y `estaticos/mapa/reportar.js` |
| Tocar los pines o el desteñido | `estaticos/mapa/mapa.js` |
| Tocar el panel Capas | `estaticos/mapa/capas.js`. Las capas y sus estilos vienen del manifiesto del repo de datos |
| Cambiar el mapa base | `estaticos/mapa/base.js` |
| Ver qué falta | [`docs/plan-tecnico.md`](docs/plan-tecnico.md), sección de fases |

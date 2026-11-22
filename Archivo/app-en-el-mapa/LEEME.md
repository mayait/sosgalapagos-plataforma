# Botones «Instalar» y «Avisos» dentro del mapa (retirado el 22-nov-2026)

Primera versión, que solo funcionaba dentro de `/riesgos/` y dependía de la configuración del mapa. Se reemplazó por `plantillas/reportes/app.js`, un componente que sirve en todo el sitio (portada, riesgos y clima). Fallaba en iPhone porque pedía el permiso de avisos después de esperar al service worker, y Safari solo lo concede si se pide en el mismo toque.

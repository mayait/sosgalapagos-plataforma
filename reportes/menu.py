# SOS Galápagos · © 2026 Universidad San Francisco de Quito (USFQ) · Autor: Julián Maya <jamaya@usfq.edu.ec>
# Todos los derechos reservados. Usar, copiar, modificar o derivar de este código requiere permiso escrito del autor (ver LICENSE).
"""El menú del sitio: los destinos y el aviso general, en un solo lugar.

De aquí salen los enlaces de respaldo que pinta el servidor (parciales/menu.html) y la lista que
usa el componente /riesgos/app.js para pintar la barra y el panel en cualquier página del sitio.
El panel de /clima/ (repositorio de datos) lleva una copia de los enlaces de respaldo: si cambia
un destino aquí, cámbielo también allí.
"""

# (nombre, ruta, en la barra del escritorio). Los que no van en la barra quedan en «Más».
DESTINOS = [
    ("Inicio", "/", True),
    ("Mapa de riesgos", "/riesgos/", True),
    ("Línea del tiempo", "/riesgos/informe/", True),
    ("Clima", "/clima/", True),
    ("Lluvia y viento", "/riesgos/mapa-del-tiempo/", True),
    ("Descargar capas", "/riesgos/descargas/", True),
    ("Puntos", "/riesgos/puntos/", False),
]

# Aviso general, igual en todas las páginas. El corto cabe en la línea del teléfono; el largo va
# en el escritorio y al pie del panel del menú.
AVISO_TITULO = "Información de apoyo de SOS Galápagos (USFQ), no oficial."
AVISO_RESTO = "Las alertas las da el COE y el pronóstico oficial es del INAMHI."


def destinos():
    return [{"nombre": n, "ruta": r, "barra": b} for n, r, b in DESTINOS]

# SOS Galápagos · © 2026 Universidad San Francisco de Quito (USFQ) · Autor: Julián Maya <jamaya@usfq.edu.ec>
# Licencia Apache 2.0 (ver LICENSE y NOTICE): puede reutilizarse dando crédito.
"""Contenido fijo de la portada: enlaces oficiales, grupos de WhatsApp, apoyo ante violencia y referencias.

Lo que cambia cada día (aviso, situación, organizaciones) se edita en el admin (portada/models.py).
Aquí solo va lo estable. Regla: nada de contactos personales, solo instituciones.
"""
from reportes import menu

# Registro de damnificados del GAD Municipal de Santa Cruz (sitio oficial) y formulario del COE.
REGISTRO_GAD = "https://www.gadsantacruz.gob.ec/registro-damnificados/"
FORMULARIO_COE = "https://docs.google.com/forms/d/e/1FAIpQLSe-wb4SGX8Z0IxRUCjMUBgY3XFLGGc-wwmfPux6aTaGxxOCzQ/viewform"

# Accesos grandes de la portada. Los nombres son los del menú del sitio (reportes/menu.py).
_NOMBRE = {ruta: nombre for nombre, ruta, _ in menu.DESTINOS}
ACCESOS = [
    {"nombre": _NOMBRE["/riesgos/"], "ruta": "/riesgos/", "texto": "Peligros, refugios y dónde ayudar", "icono": "marca", "principal": True},
    {"nombre": "Reportar", "ruta": "/riesgos/reportar/", "texto": "Un peligro, con foto y sin cuenta", "icono": "camara", "principal": True},
    {"nombre": _NOMBRE["/clima/"], "ruta": "/clima/", "texto": "La lluvia en vivo", "icono": "agua"},
    {"nombre": _NOMBRE["/riesgos/mapa-del-tiempo/"], "ruta": "/riesgos/mapa-del-tiempo/", "texto": "Lo que viene en los modelos", "icono": "quebrada"},
    {"nombre": _NOMBRE["/riesgos/informe/"], "ruta": "/riesgos/informe/", "texto": "Todo lo que ha pasado, en orden", "icono": "documento"},
]

# Tarjetas de «Mapas y clima». Sin sellos de «no oficial» en cada una: el aviso general va en el menú.
CONSULTA = [
    {"titulo": _NOMBRE["/riesgos/"], "ruta": "/riesgos/",
     "resumen": "Lugares de peligro, buenas noticias y dónde ayudar, según la comunidad, sobre las capas de riesgo. Cada aviso se retira solo con el tiempo.",
     "contenido": ["Reportar un peligro con foto, sin cuenta", "Fotos de cada reporte y vista en 3D", "Capas de riesgo, quebradas y vías",
                   "Buscador de calles y barrios"]},
    {"titulo": _NOMBRE["/riesgos/informe/"], "ruta": "/riesgos/informe/",
     "resumen": "Todo lo que ha pasado, en orden, desde el inicio de la emergencia: reportes, avisos, comunicados oficiales y el historial de la primera semana.",
     "contenido": ["Cada reporte con su hora, su lugar y sus fotos", "Salta a cualquier día", "Filtros por zona, tipo y fechas"]},
    {"titulo": "Clima en vivo", "ruta": "/clima/",
     "resumen": "Lluvia y temperatura de las estaciones de Santa Cruz, San Cristóbal e Isabela. Se actualiza cada 5 minutos.",
     "contenido": ["Lluvia acumulada en 24 h por estación", "Boletines oficiales del INAMHI y del INOCAR", "Nivel de lluvia peligrosa por zona (estimación preliminar)"]},
    {"titulo": _NOMBRE["/riesgos/mapa-del-tiempo/"], "ruta": "/riesgos/mapa-del-tiempo/",
     "resumen": "Mapa animado de la lluvia y el viento que esperan los modelos para los próximos días.",
     "contenido": ["Lluvia cada 3 horas y en 24 horas", "Viento sobre las islas", "Son modelos: pueden fallar en lugar y hora"]},
    {"titulo": _NOMBRE["/riesgos/descargas/"], "ruta": "/riesgos/descargas/",
     "resumen": "Todas las capas geográficas de la emergencia, una por una o en un solo archivo. Los modelos son estimaciones propias.",
     "contenido": ["Shapefile y GeoJSON, en WGS 84 (EPSG:4326)", "Riesgo de inundación, quebradas, vías y población", "Cada archivo trae su fuente y su licencia"]},
]

GRUPOS_WHATSAPP = [
    {"nombre": "Comunidad de brigadas de Santa Cruz", "url": "https://chat.whatsapp.com/Ietg8wTqjCWC1X2osW7AYM",
     "descripcion": "Una comunidad con un grupo por brigada. Entra y únete a la que puedas apoyar:",
     "grupos": ["Comida La Cascada", "Comida El Bosque", "Miramar", "Ropa La Cascada", "Ropa Divino Niño", "Limpieza y recolección de escombros"],
     "boton": "Entrar a la comunidad"},
    {"nombre": "Grupo Autorganizado", "url": "https://chat.whatsapp.com/H5WXxdgRy1K1fYNF9nFq5j", "boton": "Unirme por WhatsApp"},
    {"nombre": "Grupo Brigadas USFQ", "url": "https://chat.whatsapp.com/ISfiKu9iCdNEaBIfgQicg3", "boton": "Unirme por WhatsApp"},
]

# El QR de cada grupo (estaticos/portada/qr/) lo genera despliegue/generar_qr.py.
for _i, _g in enumerate(GRUPOS_WHATSAPP, start=1):
    _g["qr"] = f"portada/qr/grupo-{_i}.svg"

# Apoyo ante violencia de género: el WhatsApp institucional de Magma Galápagos.
APOYO_VIOLENCIA = {
    "organizacion": "Magma Galápagos",
    "whatsapp": "https://wa.me/593991033741",
    "instagram": "https://www.instagram.com/magma.gps/",
}

REFERENCIAS = [
    {"autores": "Rosado, V., Bravo, G., Vaca, V., Menoscal, M., Garces, D., Larreta, E. y Mulas, M.", "anio": 2025,
     "titulo": "Morphometric watershed prioritization for sustainable agriculture and water management on Santa Cruz Island, Galápagos",
     "revista": "Environmental and Sustainability Indicators", "detalle": "27, 100843", "doi": "10.1016/j.indic.2025.100843",
     "nota": "Delimita y prioriza las 24 subcuencas de Santa Cruz a partir de su morfometría."},
]

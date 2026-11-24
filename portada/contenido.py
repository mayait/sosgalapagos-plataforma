# SOS Galápagos · © 2026 Universidad San Francisco de Quito (USFQ) · Autor: Julián Maya <jamaya@usfq.edu.ec>
# Licencia Apache 2.0 (ver LICENSE y NOTICE): puede reutilizarse dando crédito.
"""Contenido fijo de la portada: los enlaces de «Más», los grupos de WhatsApp y el apoyo ante violencia.

Lo que cambia cada día (aviso, situación, organizaciones) se edita en el admin (portada/models.py).
Aquí solo va lo estable. Regla: nada de contactos personales, solo instituciones.

Ya no están el registro de damnificados del GAD ni el formulario del COE: los dos enlaces se
rompieron y no hay otros (23-nov-2026). Las referencias científicas pasaron a /riesgos/descargas/.
"""
from reportes import menu

# «Más»: píldoras a lo que no cabe en la portada. Los nombres son los del menú del sitio (reportes/menu.py).
_NOMBRE = {ruta: nombre for nombre, ruta, _ in menu.DESTINOS}
MAS = [
    {"nombre": "Clima completo", "ruta": "/clima/"},
    {"nombre": _NOMBRE["/riesgos/informe/"], "ruta": "/riesgos/informe/"},
    {"nombre": _NOMBRE["/riesgos/mapa-del-tiempo/"], "ruta": "/riesgos/mapa-del-tiempo/"},
    {"nombre": _NOMBRE["/riesgos/descargas/"], "ruta": "/riesgos/descargas/"},
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

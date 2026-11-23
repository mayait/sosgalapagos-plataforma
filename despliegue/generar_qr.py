# SOS Galápagos · © 2026 Universidad San Francisco de Quito (USFQ) · Autor: Julián Maya <jamaya@usfq.edu.ec>
# Licencia Apache 2.0 (ver LICENSE y NOTICE): puede reutilizarse dando crédito.
"""Genera los códigos QR de la portada (grupos de WhatsApp y apoyo ante violencia) en estaticos/portada/qr/.

Se corre a mano cuando cambia un enlace de portada/contenido.py. Necesita «segno», que no va en
requisitos.txt porque el servidor no lo usa:  pip install segno && python despliegue/generar_qr.py
"""
import sys
from pathlib import Path

import segno

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
from portada import contenido  # noqa: E402

SALIDA = RAIZ / "estaticos" / "portada" / "qr"
SALIDA.mkdir(parents=True, exist_ok=True)
enlaces = {f"grupo-{i}": g["url"] for i, g in enumerate(contenido.GRUPOS_WHATSAPP, start=1)}
enlaces["apoyo-violencia"] = contenido.APOYO_VIOLENCIA["whatsapp"]
for nombre, url in enlaces.items():
    segno.make(url, error="m").save(SALIDA / f"{nombre}.svg", scale=4, border=0, dark="#000000", light=None, xmldecl=False, svgns=True)
    print(SALIDA / f"{nombre}.svg")

# SOS Galápagos · © 2026 Universidad San Francisco de Quito (USFQ) · Autor: Julián Maya <jamaya@usfq.edu.ec>
# Licencia Apache 2.0 (ver LICENSE y NOTICE): puede reutilizarse dando crédito.
"""Genera los iconos de la app instalable (pin blanco sobre rojo USFQ). Se corre una vez."""
from PIL import Image, ImageDraw

for lado in (192, 512):
    img = Image.new("RGB", (lado, lado), "#e11b22")
    d = ImageDraw.Draw(img)
    c, r = lado / 2, lado * 0.19
    arriba = lado * 0.40
    d.ellipse([c - r, arriba - r, c + r, arriba + r], fill="white")
    d.polygon([(c - r * 0.92, arriba + r * 0.4), (c + r * 0.92, arriba + r * 0.4), (c, lado * 0.80)], fill="white")
    d.ellipse([c - r * 0.42, arriba - r * 0.42, c + r * 0.42, arriba + r * 0.42], fill="#e11b22")
    img.save(f"estaticos/app/icono-{lado}.png")

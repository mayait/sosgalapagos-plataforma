# SOS Galápagos · © 2026 Universidad San Francisco de Quito (USFQ) · Autor: Julián Maya <jamaya@usfq.edu.ec>
# Licencia Apache 2.0 (ver LICENSE y NOTICE): puede reutilizarse dando crédito.
"""Genera estaticos/portada/islas.json: el contorno de las islas para la animación de la portada.

Sale de la capa de islas del IGM que está en el repositorio de datos (geodatos/capas/igm/islas.geojson),
la misma del reel del clima (clima/reel/islas.py). Aquí se simplifica más, porque el mapa de la
portada mide entre 330 y 600 px de ancho y el archivo se baja con la página.

Se corre a mano, solo si esa capa cambia. No necesita paquetes:

    python3 -I despliegue/generar_islas.py ~/dev/sosgalapagos-datos/geodatos/capas/igm/islas.geojson
"""
import json
import sys
from pathlib import Path

SALIDA = Path(__file__).resolve().parent.parent / "estaticos" / "portada" / "islas.json"
TOLERANCIA = 0.0025   # grados (≈ 280 m): menos de un píxel con todo el archipiélago en 600 px
AREA_MINIMA = 4e-5    # grados² (≈ 0,5 km²): los islotes más chicos no se verían


def _distancia(p, a, b):
    """Distancia de p a la recta que pasa por a y b (al punto a, si a y b coinciden)."""
    dx, dy = b[0] - a[0], b[1] - a[1]
    largo = (dx * dx + dy * dy) ** 0.5
    if not largo:
        return ((p[0] - a[0]) ** 2 + (p[1] - a[1]) ** 2) ** 0.5
    return abs(dy * p[0] - dx * p[1] + b[0] * a[1] - b[1] * a[0]) / largo


def simplificar(linea, tolerancia=TOLERANCIA):
    """Douglas-Peucker, sin recursión (hay anillos de miles de puntos)."""
    conservar = [False] * len(linea)
    conservar[0] = conservar[-1] = True
    pila = [(0, len(linea) - 1)]
    while pila:
        a, b = pila.pop()
        lejos, cual = 0.0, None
        for i in range(a + 1, b):
            d = _distancia(linea[i], linea[a], linea[b])
            if d > lejos:
                lejos, cual = d, i
        if cual is not None and lejos > tolerancia:
            conservar[cual] = True
            pila += [(a, cual), (cual, b)]
    return [p for p, si in zip(linea, conservar) if si]


def area(anillo):
    return abs(sum(a[0] * b[1] - b[0] * a[1] for a, b in zip(anillo, anillo[1:]))) / 2


def anillo_simple(anillo):
    """Un anillo cerrado se parte en dos mitades para que el primer punto no quede fijo en una recta."""
    mitad = len(anillo) // 2
    puntos = simplificar(anillo[: mitad + 1])[:-1] + simplificar(anillo[mitad:])
    return [[round(x, 4), round(y, 4)] for x, y in puntos]


def main(origen):
    capa = json.loads(Path(origen).read_text(encoding="utf-8"))
    islas = []
    for f in capa["features"]:
        exterior = f["geometry"]["coordinates"][0]   # todas son polígonos; los huecos (lagunas) no se dibujan
        if area(exterior) < AREA_MINIMA:
            continue
        anillo = anillo_simple(exterior)
        if len(anillo) >= 4:
            islas.append({"type": "Feature", "properties": {}, "geometry": {"type": "Polygon", "coordinates": [anillo]}})
    SALIDA.write_text(json.dumps({"type": "FeatureCollection", "fuente": "IGM", "features": islas}, separators=(",", ":")) + "\n", encoding="utf-8")
    print(f"{SALIDA}: {len(islas)} islas, {SALIDA.stat().st_size / 1024:.0f} kB")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit("uso: python3 -I despliegue/generar_islas.py RUTA/islas.geojson")
    main(sys.argv[1])

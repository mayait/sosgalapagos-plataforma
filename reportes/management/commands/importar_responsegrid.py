# SOS Galápagos · © 2026 Universidad San Francisco de Quito (USFQ) · Autor: Julián Maya <jamaya@usfq.edu.ec>
# Licencia Apache 2.0 (ver LICENSE y NOTICE): puede reutilizarse dando crédito.
"""Importa el historial de la plataforma de coordinación anterior (ResponseGrid, 1 al 4 de noviembre de 2026).

Uso: python manage.py importar_responsegrid <archivo.json> [--simular]

El archivo es la exportación de las necesidades y los puntos públicos de ResponseGrid. Trae datos
reales: no se guarda en ningún repositorio.

Qué hace con cada cosa:
- Entra como reporte cerrado, de la fuente «Coordinación anterior», con su fecha original. No sale
  en el mapa (ver ReporteQuerySet.del_mapa); sí en la línea del tiempo y en su ficha.
- Se puede volver a correr sin duplicar: cada reporte guarda el id original en `id_externo`.
- Privacidad:
  - los pedidos sensibles (`sensibilidad = approximate`) se redondean a unos 500 m y van solo con su título;
  - de las descripciones se quitan teléfonos, correos, enlaces y las frases de contacto
    («Contacto: …», «llamar…», «teléfono…»), y las marcas de la plataforma anterior («Publicado en WhatsApp…», «Vence…»);
  - las entregas, los transportes y los servicios los ofrecían muchas veces personas con su nombre:
    van sin título propio, con el nombre del tipo;
  - la dirección y la referencia no se importan: basta el punto y la zona;
  - no se importan los pedidos rechazados ni los puntos ocultos.
- Todo entra con el contenido visible, porque ya estaba publicado.
"""
import json
import re
from datetime import datetime, timedelta

from django.contrib.gis.geos import Point
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from reportes.models import Estado, Fuente, MotivoCierre, Reporte, TipoRiesgo
from zonas.models import zona_de

PREFIJO = "responsegrid"
REDONDEO = 0.005  # grados: unos 550 m en Galápagos
PLAZO = timedelta(hours=72)

# Tipo de punto de ResponseGrid → código del tipo de aviso (migración 0013).
TIPO_DE_PUNTO = {
    "venue": "refugio",
    "collection_point": "acopio",
    "collection_and_delivery": "acopio",
    "delivery_point": "entrega",
    "transport": "transporte",
    "supplier": "servicio",
}
# Estos los ofrecían a menudo personas con nombre propio: van con el nombre del tipo.
SIN_TITULO_PROPIO = {"delivery_point", "transport", "supplier"}
NOMBRE_DEL_TIPO = {
    "refugio": "Refugio o alojamiento", "acopio": "Centro de acopio", "entrega": "Entrega de ayuda",
    "transporte": "Transporte solidario", "servicio": "Servicio para familias afectadas", "pedido_ayuda": "Pedido de ayuda",
}

MARCAS = [
    re.compile(r"Publicado en WhatsApp:[^.]*\.\s*", re.I),
    re.compile(r"Vence:[^()]*\([^)]*\)\.?\s*", re.I),
    re.compile(r"Ya pasó\.\s*", re.I),
]
FRASE_DE_CONTACTO = re.compile(r"contacto|llam[aeo]|tel[eé]fono|celular|whats|google maps|wa\.me|@|https?://", re.I)
CORREO = re.compile(r"\S+@\S+")
ENLACE = re.compile(r"https?://\S+|www\.\S+", re.I)
TELEFONO = re.compile(r"\+?\d[\d\s().-]{5,}\d")
FECHA_ISO = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def sin_telefonos(texto):
    """Quita los números de 7 o más cifras (teléfonos, cédulas), salvo las fechas ISO."""
    def cambiar(m):
        cifras = re.sub(r"\D", "", m.group())
        return m.group() if len(cifras) < 7 or FECHA_ISO.match(m.group().strip()) else ""
    return TELEFONO.sub(cambiar, texto)


def limpiar(texto, largo=280):
    """Texto público sin teléfonos, correos, enlaces ni frases de contacto."""
    texto = (texto or "").strip()
    for marca in MARCAS:
        texto = marca.sub("", texto)
    frases = [f for f in re.split(r"(?<=[.!?])\s+", texto) if f and not FRASE_DE_CONTACTO.search(f)]
    texto = " ".join(frases)
    texto = sin_telefonos(ENLACE.sub("", CORREO.sub("", texto)))
    texto = re.sub(r"\s+([.,;:])", r"\1", re.sub(r"\s{2,}", " ", texto)).strip(" ,;:-—")
    return texto if len(texto) <= largo else texto[: largo - 1].rstrip() + "…"


def titulo_limpio(texto):
    texto = re.sub(r"\s{2,}", " ", sin_telefonos(ENLACE.sub("", CORREO.sub("", texto or "")))).strip(" ,;:-—")
    return texto if len(texto) <= 80 else texto[:79].rstrip() + "…"


def fecha(texto):
    if not texto:
        return None
    f = datetime.fromisoformat(texto.replace("Z", "+00:00"))
    if f.tzinfo is None:
        raise ValueError("fecha sin zona horaria")
    return f


def redondear(valor):
    return round(round(valor / REDONDEO) * REDONDEO, 6)


def tipo_de(codigo):
    """El tipo por su código o, si coordinación lo creó con otro código, por su nombre."""
    tipo = TipoRiesgo.objects.filter(codigo=codigo).first() or TipoRiesgo.objects.filter(nombre__iexact=NOMBRE_DEL_TIPO[codigo]).first()
    if not tipo:
        raise CommandError(f"Falta el tipo de aviso «{codigo}». Corre las migraciones (reportes 0013).")
    return tipo


def de_necesidad(n):
    """Campos de un reporte a partir de un pedido de ayuda. None si no se importa."""
    if n.get("estado") == "rejected":
        return None
    aproximado = n.get("sensibilidad") != "public"
    lon, lat = float(n["lon"]), float(n["lat"])
    if aproximado:
        lon, lat = redondear(lon), redondear(lat)
        nota = "Pedido con la ubicación aproximada (unos 500 m) para cuidar a quien lo hizo."
    else:
        nota = limpiar(n.get("descripcion"))
        items = [i for i in (n.get("items") or []) if isinstance(i, dict) and i.get("nombre")]
        if items:
            lista = "Se pedía: " + ", ".join(titulo_limpio(i["nombre"]).lower() for i in items) + "."
            if len(nota) + len(lista) + 1 <= 280:
                nota = f"{nota} {lista}".strip()
    creado = fecha(n["creado"])
    vence = fecha(n.get("vence")) or creado + PLAZO
    return {"id_externo": f"{PREFIJO}:necesidad:{n['id']}", "codigo": "pedido_ayuda", "titulo": titulo_limpio(n.get("titulo")),
            "nota": nota, "lon": lon, "lat": lat, "visto_en": creado, "vence_en": max(vence, creado)}


def de_punto(p):
    """Campos de un reporte a partir de un punto público (refugio, acopio, entrega…). None si no se importa."""
    if p.get("estado") == "hidden" or p.get("tipo") not in TIPO_DE_PUNTO:
        return None
    creado = fecha(p["creado"])
    return {"id_externo": f"{PREFIJO}:punto:{p['id']}", "codigo": TIPO_DE_PUNTO[p["tipo"]],
            "titulo": "" if p["tipo"] in SIN_TITULO_PROPIO else titulo_limpio(p.get("nombre")),
            "nota": limpiar(p.get("descripcion")), "lon": float(p["lon"]), "lat": float(p["lat"]), "visto_en": creado, "vence_en": creado + PLAZO}


def importar(datos):
    """Crea o actualiza los reportes del historial. Devuelve (creados, actualizados, omitidos)."""
    filas = [de_necesidad(n) for n in datos.get("necesidades") or []] + [de_punto(p) for p in datos.get("puntos") or []]
    omitidos = sum(1 for f in filas if f is None)
    creados = actualizados = 0
    tipos = {}
    for f in filter(None, filas):
        tipo = tipos.get(f["codigo"]) or tipos.setdefault(f["codigo"], tipo_de(f["codigo"]))
        punto = Point(f["lon"], f["lat"], srid=4326)
        campos = {
            "tipo": tipo, "titulo": f["titulo"], "nota": f["nota"], "punto": punto, "zona": zona_de(punto),
            "visto_en": f["visto_en"], "vence_en": f["vence_en"], "cerrado_en": f["vence_en"],
            "estado": Estado.CERRADO, "motivo_cierre": MotivoCierre.HISTORIAL, "fuente": Fuente.ANTERIOR,
            "contenido_visible": True, "contacto": "",
        }
        reporte = Reporte.objects.filter(id_externo=f["id_externo"]).first()
        if reporte:
            for campo, valor in campos.items():
                setattr(reporte, campo, valor)
            reporte.save()
            actualizados += 1
        else:
            Reporte(id_externo=f["id_externo"], **campos).save()
            creados += 1
    return creados, actualizados, omitidos


class Command(BaseCommand):
    help = "Importa el historial de ResponseGrid (necesidades y puntos) como reportes cerrados que solo salen en la línea del tiempo."

    def add_arguments(self, parser):
        parser.add_argument("archivo")
        parser.add_argument("--simular", action="store_true", help="Lo hace todo y lo deshace al final.")

    def handle(self, archivo, simular=False, **opciones):
        try:
            with open(archivo, encoding="utf-8") as f:
                datos = json.load(f)
        except (OSError, ValueError) as e:
            raise CommandError(f"No se pudo leer {archivo}: {e}")
        with transaction.atomic():
            creados, actualizados, omitidos = importar(datos)
            if simular:
                transaction.set_rollback(True)
        self.stdout.write(f"{'Simulación: ' if simular else ''}{creados} creados, {actualizados} actualizados, {omitidos} sin importar "
                          "(pedidos rechazados y puntos ocultos).")

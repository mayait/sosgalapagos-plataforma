# SOS Galápagos · © 2026 Universidad San Francisco de Quito (USFQ) · Autor: Julián Maya <jamaya@usfq.edu.ec>
# Licencia Apache 2.0 (ver LICENSE y NOTICE): puede reutilizarse dando crédito.
"""Lo que publican las instituciones: el pronóstico del INAMHI por isla y los boletines oficiales.

Los boletines (advertencia del INAMHI, oleaje del INOCAR, ERFEN) son PDF o imágenes sin texto.
Se detecta que hay uno nuevo por la huella del archivo y un modelo de lenguaje lo lee: saca
la vigencia, el nivel y lo que dice de Galápagos. El resumen nunca reemplaza al documento:
siempre se guarda y se muestra el enlace al original.

Endpoints, en variables de entorno (nunca en el repositorio):
  CLIMA_INAMHI_PRONOSTICO_URL, CLIMA_INAMHI_LLUVIA_HORAS_URL, CLIMA_INAMHI_ADVERTENCIA_URL,
  CLIMA_INOCAR_OLEAJE_RSS, CLIMA_ERFEN_URL
"""
import hashlib
import json
import logging
import re
import time
from datetime import datetime, timezone

from django.conf import settings
from pydantic import BaseModel, Field

from .consultas import GALAPAGOS
from .mar import _bajar, _corrida
from .models import Boletin, PronosticoOficial

registro = logging.getLogger(__name__)
ISLAS = {"santa cruz": "santa-cruz", "san cristóbal": "san-cristobal", "san cristobal": "san-cristobal", "isabela": "isabela"}


# ── Pronóstico del INAMHI por isla ───────────────────────────────────────────
def actualizar_pronostico_inamhi():
    """Guarda el pronóstico del día y la lluvia esperada hora a hora de las tres islas. Devuelve cuántas guardó."""
    if not settings.CLIMA_INAMHI_PRONOSTICO_URL:
        return 0
    t0, ahora, guardadas = time.monotonic(), datetime.now(timezone.utc), 0
    try:
        dia = json.loads(_bajar(settings.CLIMA_INAMHI_PRONOSTICO_URL))
        horas = {}
        if settings.CLIMA_INAMHI_LLUVIA_HORAS_URL:
            try:
                for clave, c in (json.loads(_bajar(settings.CLIMA_INAMHI_LLUVIA_HORAS_URL)).get("ciudades") or {}).items():
                    isla = ISLAS.get(clave.split("|")[0].strip().lower())
                    if isla and c.get("ok"):
                        horas[isla] = c.get("horas") or []
            except Exception:
                pass  # el pronóstico del día vale aunque falle el de las horas
        for item in dia.get("items") or []:
            isla = ISLAS.get((item.get("locality_name") or "").strip().lower())
            if not isla:
                continue
            numero = lambda v: float(v) if v not in (None, "") else None  # noqa: E731
            PronosticoOficial.objects.update_or_create(
                isla=isla, fecha=item["date"][:10],
                defaults={"obtenido": ahora, "minima_c": numero(item.get("min_temperature")), "maxima_c": numero(item.get("max_temperature")),
                          "periodos": [{"periodo": p.get("period_name"), "condicion": p.get("condition_name")} for p in item.get("periods") or []],
                          "lluvia_horas": horas.get(isla, [])},
            )
            guardadas += 1
        _corrida("inamhi_pronostico", t0, bool(guardadas), guardadas)
    except Exception as e:
        _corrida("inamhi_pronostico", t0, False, error=type(e).__name__)
    return guardadas


# ── Boletines: leer un documento con el modelo de lenguaje ───────────────────
class Extraido(BaseModel):
    """Lo que dice un boletín oficial."""

    numero: str | None = Field(default=None, description="Número del boletín o advertencia, tal como aparece (por ejemplo «89» o «013-2026»).")
    titulo: str | None = Field(default=None, description="Título oficial, corto.")
    emitido: str | None = Field(default=None, description="Fecha y hora de emisión en ISO 8601 con zona. La hora continental de Ecuador es -05:00.")
    vigente_desde: str | None = Field(default=None, description="Inicio de la vigencia, ISO 8601 con zona (-05:00 si es hora de Ecuador continental).")
    vigente_hasta: str | None = Field(default=None, description="Fin de la vigencia, ISO 8601 con zona.")
    afecta_galapagos: bool = Field(description="True solo si el documento nombra a Galápagos, la región Insular o alguna de sus islas como zona afectada.")
    nivel_galapagos: str | None = Field(default=None, description="Nivel que el documento da para Galápagos, en una a tres palabras tal como lo nombra la leyenda (por ejemplo «muy alto», «alto», «medio», «moderado a agitado»). Si hay varios, el más alto. None si no lo da.")
    fenomeno: str | None = Field(default=None, description="Fenómeno: lluvias, tormentas, oleaje, aguaje, El Niño…")
    ola_min_m: float | None = Field(default=None, description="Altura mínima de ola prevista para Galápagos, en metros, si el documento la da.")
    ola_max_m: float | None = Field(default=None, description="Altura máxima de ola prevista para Galápagos, en metros.")
    periodo_s: float | None = Field(default=None, description="Período de las olas en segundos, si lo da.")
    resumen: str = Field(description="Qué dice el documento sobre Galápagos, en 1 a 3 frases claras, máximo 400 caracteres. Si no dice nada de Galápagos, una frase de qué trata. Sin inventar nada.")


INSTRUCCIONES = """Lees un boletín oficial de Ecuador (del INAMHI o del INOCAR) y rellenas el esquema.
- Copia fechas, números y niveles tal como aparecen. No inventes ni deduzcas nada que no esté en el documento.
- Si un dato no está, déjalo vacío.
- «afecta_galapagos» es True solo si el documento nombra a Galápagos, la región Insular o sus islas entre las zonas afectadas o en su pronóstico.
- En los mapas, mira la leyenda de colores y qué color cubre las islas Galápagos (al oeste, separadas del continente).
- Las horas son de Ecuador continental (UTC-5), salvo que el documento diga otra cosa.
- El resumen es para vecinos de Galápagos: claro, sin siglas sin explicar, y sin recomendaciones propias."""


def _fecha(texto):
    try:
        f = datetime.fromisoformat((texto or "").replace("Z", "+00:00"))
        return f if f.tzinfo else f.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def leer_documento(contenido, tipo_mime, que_es):
    """Pasa el documento (PDF o imagen) al modelo configurado y devuelve un Extraido, o None si no hay modelo o falla."""
    if not settings.IA_MODELO:
        return None
    try:
        from pydantic_ai import Agent, BinaryContent

        agente = Agent(settings.IA_MODELO, output_type=Extraido, instructions=INSTRUCCIONES, retries=1)
        return agente.run_sync([f"Documento: {que_es}. Hoy es {datetime.now(GALAPAGOS):%Y-%m-%d}.", BinaryContent(data=contenido, media_type=tipo_mime)],
                               model_settings={"timeout": 90}).output
    except Exception:
        registro.exception("No se pudo leer el boletín con el modelo")
        return None


def registrar(fuente, tipo, contenido, tipo_mime, enlace, que_es, titulo=""):
    """Guarda un boletín si su documento es nuevo. Devuelve el Boletin creado o None."""
    huella = hashlib.sha256(contenido).hexdigest()
    if Boletin.objects.filter(huella=huella).exists():
        return None
    e = leer_documento(contenido, tipo_mime, que_es)
    campos = {"titulo": titulo[:200], "enlace": enlace}
    if e:
        campos.update(
            numero=(e.numero or "")[:30], titulo=(e.titulo or titulo)[:200], emitido=_fecha(e.emitido), vigente_desde=_fecha(e.vigente_desde),
            vigente_hasta=_fecha(e.vigente_hasta), afecta_galapagos=e.afecta_galapagos, nivel=(e.nivel_galapagos or "")[:80], resumen=e.resumen[:600],
            datos={k: v for k, v in {"fenomeno": e.fenomeno, "ola_min_m": e.ola_min_m, "ola_max_m": e.ola_max_m, "periodo_s": e.periodo_s}.items() if v is not None},
            extraido_con=str(settings.IA_MODELO)[:60],
        )
    return Boletin.objects.create(fuente=fuente, tipo=tipo, huella=huella, **campos)


MIME = {".pdf": "application/pdf", ".png": "image/png", ".webp": "image/webp", ".jpg": "image/jpeg", ".jpeg": "image/jpeg"}


def revisar_boletines():
    """Mira si hay boletines nuevos en cada fuente. Devuelve la lista de los que encontró."""
    nuevos = []
    fijos = [
        ("inamhi", "advertencia", settings.CLIMA_INAMHI_ADVERTENCIA_URL, "advertencia meteorológica del INAMHI (mapa de Ecuador con niveles por color y tabla de vigencia)"),
        ("inocar", "erfen", settings.CLIMA_ERFEN_URL, "boletín del comité ERFEN sobre El Niño (INOCAR)"),
    ]
    for fuente, tipo, url, que_es in fijos:
        if not url:
            continue
        t0 = time.monotonic()
        try:
            b = registrar(fuente, tipo, _bajar(url, espera=60), "application/pdf", url, que_es)
            _corrida(f"boletin_{tipo}", t0, True, 1 if b else 0)
            if b:
                nuevos.append(b)
        except Exception as e:
            _corrida(f"boletin_{tipo}", t0, False, error=type(e).__name__)
    if settings.CLIMA_INOCAR_OLEAJE_RSS:
        t0 = time.monotonic()
        try:
            rss = _bajar(settings.CLIMA_INOCAR_OLEAJE_RSS).decode("utf-8", "replace")
            # Solo el más reciente: los anteriores ya vencieron.
            for item in re.findall(r"<item>(.*?)</item>", rss, re.S)[:1]:
                titulo = re.sub(r"<!\[CDATA\[|\]\]>", "", (re.findall(r"<title>(.*?)</title>", item, re.S) or [""])[0]).strip()
                imagen = (re.findall(r'src="([^"]+\.(?:png|webp|jpe?g))"', item, re.I) or [None])[0]
                if not imagen:
                    continue
                extension = "." + imagen.rsplit(".", 1)[-1].lower()
                b = registrar("inocar", "oleaje", _bajar(imagen, espera=60), MIME.get(extension, "image/png"), imagen,
                              "boletín de oleaje del INOCAR (tabla por zona de la costa y de Galápagos con altura de ola, período y estado del mar)", titulo)
                if b:
                    nuevos.append(b)
            _corrida("boletin_oleaje", t0, True, len([b for b in nuevos if b.tipo == "oleaje"]))
        except Exception as e:
            _corrida("boletin_oleaje", t0, False, error=type(e).__name__)
    return nuevos


def vigentes(ahora=None):
    """Boletines que siguen vigentes (o sin fecha de fin y recientes), para mostrar."""
    from datetime import timedelta

    ahora = ahora or datetime.now(timezone.utc)
    salida = []
    for b in Boletin.objects.filter(visto_en__gte=ahora - timedelta(days=20)):
        if b.vigente_hasta and b.vigente_hasta < ahora:
            continue
        if not b.vigente_hasta and b.visto_en < ahora - timedelta(days=5 if b.tipo != "erfen" else 16):
            continue
        salida.append({"fuente": b.fuente.upper(), "tipo": b.tipo, "numero": b.numero, "titulo": b.titulo, "emitido": b.emitido, "vigente_desde": b.vigente_desde,
                       "vigente_hasta": b.vigente_hasta, "afecta_galapagos": b.afecta_galapagos, "nivel": b.nivel, "resumen": b.resumen, "datos": b.datos,
                       "enlace": b.enlace, "leido_por_modelo": bool(b.extraido_con), "revisado": b.revisado})
    return salida

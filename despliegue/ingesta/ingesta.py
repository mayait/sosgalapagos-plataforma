#!/usr/bin/env python3
# SOS Galápagos · entrada horaria desde los grupos de WhatsApp.
# © 2026 Universidad San Francisco de Quito (USFQ) · SOS Galápagos · Julián Maya <jamaya@usfq.edu.ec>
# Licencia Apache 2.0 (ver LICENSE y NOTICE en la raíz del repositorio): puede reutilizarse dando crédito.
"""Lee los grupos de WhatsApp de la emergencia, clasifica cada mensaje y sube a la plataforma lo que sirve.

Corre en la Mac de coordinación, cada hora (Orca la lanza). Dos pasos:

1. descargar: llama a wa_export.py (repo home-server-docs, scripts/openwa/) con la llave de SOLO
   LECTURA de OpenWA. Deja los mensajes y adjuntos en la carpeta de siempre
   (~/Downloads/WhatsApp lluvias 2027). Es incremental y nunca borra nada de la carpeta.
2. procesar: lee de la carpeta los grupos de la configuración (nunca chats privados), junta los
   mensajes de una misma persona en ráfagas (foto + texto + ubicación), los clasifica con Jev
   (TypeSafe) y sube cada elemento ya limpio a POST /riesgos/api/ingesta/whatsapp:
   - con ubicación segura (ubicación compartida, enlace de mapa o coordenadas) → al mapa;
   - foto o aviso relevante sin ubicación segura → a «Ayúdanos a ubicar»;
   - ruido → se descarta (se cuenta).

Privacidad (decisión de Julián): al servidor solo llega la foto o un fotograma, la hora y el texto
sin nombres ni teléfonos. Nunca el grupo, el remitente, el video ni la carpeta. Una foto con una
persona identificable en primer plano, un menor o un documento va a revisión de coordinación. Si
algo falla al revisar una foto, también va a revisión: nunca se publica sin revisar.

El registro de lo ya procesado vive en la carpeta (registro_ingesta.jsonl): ahí queda de qué chat
y archivo salió cada elemento, para que coordinación encuentre el original. El servidor, además,
no acepta dos veces el mismo `id_origen`.

Solo usa la biblioteca estándar de Python 3.9+ y ffmpeg (fotogramas de los videos y fotos sin
metadatos). Configuración en variables de entorno o en ~/.config/sosgalapagos/ingesta.env:
    INGESTA_SERVIDOR=https://sosgalapagos.org
    INGESTA_LLAVE=…          la misma que INGESTA_LLAVE en el servidor
    TYPESAFE_API_KEY=…       Jev
    OPENWA_API_KEY=…         llave de SOLO LECTURA de OpenWA (para descargar)
    INGESTA_GRUPOS=…         JSON con los grupos (formato de wa_export.py; ver LEEME.md)
    INGESTA_CARPETA=…        por defecto ~/Downloads/WhatsApp lluvias 2027
    WA_EXPORT=…              ruta a wa_export.py
En la Mac de Julián, las llaves que falten se piden a ~/.config/sosgalapagos/secreto.sh.

Uso:
    ingesta.py horario [--ensayo]       descargar y procesar (lo que corre cada hora)
    ingesta.py descargar
    ingesta.py procesar [--ensayo] [--desde 48h] [--limite 50]
"""
import argparse
import base64
import datetime
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
import uuid
from pathlib import Path
from zoneinfo import ZoneInfo

CARPETA_POR_DEFECTO = Path.home() / "Downloads" / "WhatsApp lluvias 2027"
REGISTRO = "registro_ingesta.jsonl"
SECRETO_SH = Path.home() / ".config" / "sosgalapagos" / "secreto.sh"
RAFAGA_S = 300           # mensajes de la misma persona con menos de 5 min entre sí van juntos
MADURA_S = 300           # una ráfaga con un mensaje de hace menos de 5 min espera a la próxima corrida
INTENTOS_MAXIMOS = 3     # lo que falla se reintenta en las corridas siguientes, hasta 3 veces
TIPOS_PROCESADOS = {"text", "chat", "image", "video", "location"}

# Umbrales del clasificador (PRELIMINARES: se ajustan mirando casos reales).
UMBRAL = {
    "relevante": 0.5,      # el texto o la foto muestran algo de la emergencia en un lugar
    "persona": 0.35,       # persona identificable en primer plano → revisión
    "menor": 0.2,          # un menor, aunque sea de lejos → revisión
    "documento": 0.4,      # documento, cédula, pantalla o placa legible → revisión
    "nombre": 0.5,         # una palabra con mayúscula es el nombre de una persona → se oculta
    "quedan_nombres": 0.4, # después de limpiar todavía parece haber nombres → el texto no se publica
}

TIPOS_POR_DEFECTO = [  # si el servidor no responde; los de verdad se piden a /riesgos/api/ingesta/tipos
    {"codigo": "agua_via", "nombre": "Agua en la vía"}, {"codigo": "quebrada", "nombre": "Quebrada crecida"},
    {"codigo": "vivienda", "nombre": "Vivienda anegada"}, {"codigo": "via_cortada", "nombre": "Vía cortada"},
    {"codigo": "deslizamiento", "nombre": "Deslizamiento"}, {"codigo": "cable", "nombre": "Cable caído"},
    {"codigo": "dano_infraestructura", "nombre": "Daño en infraestructura"}, {"codigo": "algo_bueno", "nombre": "Algo bueno"},
    {"codigo": "donar_colaborar", "nombre": "Dónde donar o colaborar"},
]


def aviso(*partes):
    print(*partes, file=sys.stderr, flush=True)


# ── Configuración ────────────────────────────────────────────────────────────
def configuracion():
    archivo = Path(os.environ.get("INGESTA_ENV", Path.home() / ".config" / "sosgalapagos" / "ingesta.env"))
    valores = {}
    if archivo.exists():
        for linea in archivo.read_text().splitlines():
            if "=" in linea and not linea.strip().startswith("#"):
                k, v = linea.split("=", 1)
                valores[k.strip()] = v.strip().strip('"').strip("'")
    valores.update({k: v for k, v in os.environ.items() if k.startswith(("INGESTA_", "TYPESAFE_", "OPENWA_", "WA_EXPORT"))})
    valores.setdefault("INGESTA_SERVIDOR", "https://sosgalapagos.org")
    valores.setdefault("INGESTA_CARPETA", str(CARPETA_POR_DEFECTO))
    valores.setdefault("OPENWA_URL", "https://openwa.casa.julianmaya.com")
    valores.setdefault("TYPESAFE_URL", "https://api.typesafe.ai/v1/systemone")
    valores.setdefault("TYPESAFE_MODELO", "jev-latest")
    # En la Mac de Julián las llaves están en el Llavero; nunca se escriben en un archivo.
    for variable, cuenta in (("TYPESAFE_API_KEY", "jev"), ("OPENWA_API_KEY", "openwa-lectura"), ("INGESTA_LLAVE", "plataforma-ingesta")):
        if not valores.get(variable) and SECRETO_SH.exists():
            try:
                valores[variable] = subprocess.run([str(SECRETO_SH), cuenta], capture_output=True, text=True, timeout=20).stdout.strip()
            except Exception:
                pass
    return valores


def leer_grupos(ruta):
    """El JSON de los grupos, con la forma que usa wa_export.py: {"since", "tz", "sessions": {nombre: {"subdir", "chats"}}}."""
    if not ruta or not Path(ruta).exists():
        raise SystemExit(f"No encuentro el archivo de grupos ({ruta or 'INGESTA_GRUPOS vacío'}). Ver despliegue/ingesta/LEEME.md")
    grupos = json.loads(Path(ruta).read_text())
    if not isinstance(grupos.get("sessions"), dict):
        raise SystemExit("El archivo de grupos no tiene «sessions» (formato de wa_export.py)")
    return grupos


def nombre_seguro(s):
    """El mismo nombre de carpeta que pone wa_export.py."""
    s = re.sub(r"[^\w\s().,+&-]", "", s, flags=re.UNICODE)
    return re.sub(r"[/:\\\s]+", " ", s).strip(" .-")[:80] or "sin nombre"


def carpetas_de_grupos(grupos, carpeta):
    """Las carpetas de chat que se procesan: solo las de la configuración y solo si son grupos (@g.us)."""
    salida = []
    for _sesion, cfg in grupos["sessions"].items():
        raiz = carpeta / cfg["subdir"] if cfg.get("subdir") else carpeta
        if cfg.get("chats") == "all":
            candidatas = [d for d in sorted(raiz.iterdir()) if (d / "mensajes.json").exists()] if raiz.exists() else []
        else:
            candidatas = [raiz / (c.get("name") or nombre_seguro(c.get("match") or c.get("id") or "")) for c in cfg.get("chats", [])]
        for d in candidatas:
            mensajes = d / "mensajes.json"
            if not mensajes.exists():
                continue
            try:
                primero = next(iter(json.loads(mensajes.read_text())), None)
            except ValueError:
                continue
            if primero and str(primero.get("chatId", "")).endswith("@g.us"):  # nunca un chat privado
                salida.append(d)
    return salida


# ── 1. Descargar (wa_export.py) ──────────────────────────────────────────────
def _instantanea(carpeta):
    """{ruta de mensajes.json: (mensajes, texto de mensajes.txt)} de lo que ya está en la carpeta."""
    foto = {}
    for archivo in carpeta.rglob("mensajes.json"):
        try:
            txt = archivo.with_name("mensajes.txt")
            foto[archivo] = (json.loads(archivo.read_text()), txt.read_text() if txt.exists() else "")
        except ValueError:
            pass
    return foto


def descargar(cfg, grupos_ruta, carpeta, desde=None):
    """Descarga incremental con wa_export.py. No borra nada: si wa_export reescribe un mensajes.json
    con menos mensajes de los que había, se vuelven a unir y el mensajes.txt anterior se guarda aparte."""
    script = cfg.get("WA_EXPORT") or str(Path.home() / "dev" / "home-server-docs" / "scripts" / "openwa" / "wa_export.py")
    if not Path(script).exists():
        raise SystemExit(f"No encuentro wa_export.py en {script}. Define WA_EXPORT (ver LEEME.md)")
    if not cfg.get("OPENWA_API_KEY"):
        raise SystemExit("Falta OPENWA_API_KEY (la de solo lectura)")
    carpeta.mkdir(parents=True, exist_ok=True)
    antes = _instantanea(carpeta)
    # wa_export reescribe mensajes.json con lo que encuentra desde --since: se le pide desde el mensaje
    # más antiguo que ya está en la carpeta, para que nunca deje fuera lo que ya se había bajado.
    marcas = [m["timestamp"] for mensajes, _ in antes.values() for m in mensajes if m.get("timestamp")]
    if desde is None and marcas:
        desde = datetime.datetime.fromtimestamp(min(marcas), datetime.timezone.utc).isoformat(timespec="seconds")
    orden = [sys.executable, script, "--config", str(grupos_ruta), "--out", str(carpeta), "--url", cfg["OPENWA_URL"]]
    if desde:
        orden += ["--since", desde]
    entorno = {**os.environ, "OPENWA_API_KEY": cfg["OPENWA_API_KEY"]}
    hecho = subprocess.run(orden, env=entorno, capture_output=True, text=True, timeout=3000)
    if hecho.returncode:
        aviso("wa_export.py falló:", (hecho.stderr or hecho.stdout)[-800:])
    _no_perder_nada(antes)
    return hecho.returncode == 0


def _no_perder_nada(antes):
    sello = datetime.datetime.now().strftime("%Y%m%d-%H%M")
    for archivo, (viejos, txt_viejo) in antes.items():
        try:
            nuevos = json.loads(archivo.read_text()) if archivo.exists() else []
        except ValueError:
            nuevos = []
        ids = {m.get("id") for m in nuevos}
        perdidos = [m for m in viejos if m.get("id") not in ids]
        if not perdidos:
            continue
        unidos = sorted(nuevos + perdidos, key=lambda m: (m.get("timestamp") or 0, m.get("createdAt") or ""))
        archivo.write_text(json.dumps(unidos, ensure_ascii=False, indent=1))
        if txt_viejo:
            archivo.with_name(f"mensajes.anterior-{sello}.txt").write_text(txt_viejo)
        aviso(f"{archivo.parent.name}: se recuperaron {len(perdidos)} mensajes que wa_export dejó fuera")


# ── 2. Leer la carpeta ───────────────────────────────────────────────────────
LINEA_UBICACION = re.compile(r"^\[(\d{4}-\d\d-\d\d \d\d:\d\d:\d\d)\][^\n]*?\blat=(-?\d+(?:\.\d+)?), lon=(-?\d+(?:\.\d+)?)")


def ubicaciones_del_txt(carpeta_chat):
    """En mensajes.json no quedan las coordenadas de una ubicación compartida; wa_export las escribe en mensajes.txt."""
    txt = carpeta_chat / "mensajes.txt"
    salida = {}
    if txt.exists():
        for linea in txt.read_text(errors="replace").splitlines():
            m = LINEA_UBICACION.match(linea)
            if m:
                salida[m.group(1)] = (float(m.group(2)), float(m.group(3)))
    return salida


def archivo_de(carpeta_chat, m):
    """El adjunto de un mensaje: wa_export lo nombra HHMMSS_tipo_<8 primeros del id>…"""
    if m.get("type") not in ("image", "video"):
        return None
    for a in sorted(carpeta_chat.glob(f"*_{m['type']}_{m['id'][:8]}*")):
        if a.is_file() and not a.name.endswith(".part") and a.stat().st_size > 0:
            return a
    return None


def autor_de(m):
    return m.get("author") or m.get("from") or ""


def rafagas(mensajes, ahora):
    """Junta los mensajes de una misma persona separados por menos de RAFAGA_S. Deja fuera las que aún pueden crecer."""
    por_autor = {}
    for m in sorted(mensajes, key=lambda m: m.get("timestamp") or 0):
        lista = por_autor.setdefault(autor_de(m), [])
        if lista and m["timestamp"] - lista[-1][-1]["timestamp"] <= RAFAGA_S:
            lista[-1].append(m)
        else:
            lista.append([m])
    todas = [r for lista in por_autor.values() for r in lista]
    return sorted((r for r in todas if ahora - r[-1]["timestamp"] >= MADURA_S), key=lambda r: r[0]["timestamp"])


# ── Lugar ────────────────────────────────────────────────────────────────────
ENLACE_MAPA = re.compile(r"https?://(maps\.app\.goo\.gl|goo\.gl/maps|(www\.)?google\.[a-z.]+/maps|maps\.google\.[a-z.]+|maps\.apple\.com|waze\.com)/\S*", re.I)
PARES = [
    re.compile(r"!3d(-?\d{1,2}\.\d+)!4d(-?\d{1,3}\.\d+)"),
    re.compile(r"[?&](?:q|query|ll|sll|daddr|destination|center)=(?:loc:)?(-?\d{1,2}\.\d+)(?:,|%2C)\s*(-?\d{1,3}\.\d+)", re.I),
    re.compile(r"@(-?\d{1,2}\.\d+),(-?\d{1,3}\.\d+)"),
    re.compile(r"/(?:place|search|dir)/(-?\d{1,2}\.\d+),\s*(-?\d{1,3}\.\d+)"),
]
COORDENADAS = re.compile(r"(?<![\d.])(-?[0-2]\.\d{3,})\s*[,; ]\s*(-?(?:8[89]|9[0-2])\.\d{3,})(?![\d.])")


def en_galapagos(lat, lon):
    return lat is not None and lon is not None and -2 <= lat <= 2 and -92.5 <= lon <= -88.5


def _par(texto):
    for patron in PARES:
        m = patron.search(texto)
        if m and en_galapagos(float(m.group(1)), float(m.group(2))):
            return float(m.group(1)), float(m.group(2))
    return None


def _seguir(url, tope=4):
    """Sigue un enlace corto de mapas (solo de servicios de mapas conocidos) hasta su dirección final."""
    class SinSeguir(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, *a, **k):
            return None

    abridor = urllib.request.build_opener(SinSeguir)
    for _ in range(tope):
        if not ENLACE_MAPA.match(url):
            return url
        try:
            with abridor.open(urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (compatible; sosgalapagos)"}), timeout=8) as r:
                return r.geturl()
        except urllib.error.HTTPError as e:
            if e.code in (301, 302, 303, 307, 308) and e.headers.get("Location"):
                url = e.headers["Location"]
                continue
            return url
        except Exception:
            return url
    return url


def lugar_del_texto(texto, seguir=_seguir):
    """(lat, lon) seguro sacado del texto: un enlace de mapa o coordenadas en Galápagos. None si no hay."""
    m = ENLACE_MAPA.search(texto or "")
    if m:
        url = m.group(0).rstrip(").,;")
        par = _par(urllib.parse.unquote(url))
        if not par and urllib.parse.urlparse(url).hostname in ("maps.app.goo.gl", "goo.gl"):
            par = _par(urllib.parse.unquote(seguir(url)))
        if par:
            return par
    m = COORDENADAS.search(texto or "")
    if m and en_galapagos(float(m.group(1)), float(m.group(2))):
        return float(m.group(1)), float(m.group(2))
    return None


# ── Texto: sin nombres ni teléfonos ──────────────────────────────────────────
NUMERO = re.compile(r"\+?\d(?:[\s.\-]?\d){6,}")
MENCION = re.compile(r"@[\w.+-]+")
URL = re.compile(r"https?://\S+|www\.\S+", re.I)
CORREO = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+")
CANDIDATO = re.compile(r"\b[A-ZÁÉÍÓÚÑ][a-záéíóúñü]{2,}(?:\s+(?:de\s+(?:la\s+|los\s+)?)?[A-ZÁÉÍÓÚÑ][a-záéíóúñü]{2,})*\b")
OCULTO = "[nombre oculto]"


def _sin_tildes(t):
    return "".join(c for c in unicodedata.normalize("NFD", t) if unicodedata.category(c) != "Mn").lower()


def nombres_conocidos(carpeta, chats):
    """Lo que se sabe que es un nombre: los contactos que anotó wa_export (remitentes.json) y los nombres de los grupos."""
    nombres = set()
    archivo = carpeta / "remitentes.json"
    if archivo.exists():
        try:
            for valor in json.loads(archivo.read_text()).values():
                limpio = re.sub(r"\(.*?\)|[+\d]", " ", str(valor)).strip()
                if limpio and not limpio.isdigit():
                    nombres.add(limpio)
                    nombres.update(p for p in limpio.split() if len(p) >= 3)
        except ValueError:
            pass
    nombres.update(c.name for c in chats)
    return {n for n in nombres if len(n) >= 3}


def limpiar_texto(texto, conocidos=()):
    """Primera limpieza, sin modelo: teléfonos, menciones, enlaces, correos y los nombres que ya se conocen."""
    t = CORREO.sub(" ", texto or "")
    t = URL.sub(" ", t)
    t = MENCION.sub(" ", t)
    t = NUMERO.sub("[número oculto]", t)
    for nombre in sorted(conocidos, key=len, reverse=True):
        t = re.sub(rf"(?<![\wáéíóúñ]){re.escape(nombre)}(?![\wáéíóúñ])", OCULTO, t, flags=re.I)
    t = re.sub(rf"(?:{re.escape(OCULTO)}[\s,y]*)+", OCULTO + " ", t)
    return re.sub(r"[ \t]+", " ", re.sub(r"\s*\n\s*", "\n", t)).strip()[:600]


# ── Clasificador ─────────────────────────────────────────────────────────────
class ErrorClasificador(Exception):
    pass


class Jev:
    """Cliente mínimo de la API System One de TypeSafe (Jev). Formato comprobado el 26-nov-2026:
    POST {url} con «Authorization: Bearer», cuerpo {model, state, questions, assets?}; respuesta
    {model, answers: {id: {type, noul | choice, confidence, probabilities}}, usage}. Las imágenes
    van en «assets» (base64) con la cabecera TypeSafe-Danger-Zone-Images: true."""

    def __init__(self, llave, url, modelo):
        self.llave, self.url, self.modelo, self.version = llave, url, modelo, ""

    def preguntar(self, estado, preguntas, imagenes=None):
        cuerpo = {"model": self.modelo, "state": estado, "questions": preguntas}
        cabeceras = {"Authorization": f"Bearer {self.llave}", "Content-Type": "application/json", "User-Agent": "sosgalapagos-ingesta"}
        if imagenes:
            cuerpo["assets"] = {ref: {"type": "image", "format": "jpg", "data_base64": base64.b64encode(datos).decode()} for ref, datos in imagenes.items()}
            cabeceras["TypeSafe-Danger-Zone-Images"] = "true"
        datos = json.dumps(cuerpo).encode()
        for intento in range(4):
            try:
                with urllib.request.urlopen(urllib.request.Request(self.url, data=datos, headers=cabeceras), timeout=120) as r:
                    respuesta = json.load(r)
                self.version = respuesta.get("model", self.version)
                return respuesta["answers"]
            except urllib.error.HTTPError as e:
                if e.code in (429, 529) or e.code >= 500:
                    time.sleep(float(e.headers.get("Retry-After") or 3 * (intento + 1)))
                    continue
                raise ErrorClasificador(f"Jev respondió {e.code}")
            except (urllib.error.URLError, TimeoutError, ConnectionError, KeyError, ValueError) as e:
                time.sleep(3 * (intento + 1))
                ultimo = e
        raise ErrorClasificador(f"Jev no responde ({type(locals().get('ultimo', '')).__name__})")


CONTEXTO = ("Mensajes de grupos de WhatsApp de vecinos y voluntarios durante la emergencia por lluvias e inundaciones "
            "en las islas Galápagos (Ecuador), en noviembre de 2026.")
P_RELEVANTE = ("¿El mensaje informa de algo concreto que pasa o pasó en un lugar de Galápagos durante la emergencia: agua en la vía, "
               "quebrada o cañada crecida, casa anegada, vía cortada, deslizamiento, daño, cable caído, un refugio, un centro de acopio, "
               "dónde ayudar o una buena noticia de un lugar? Responde no si es un saludo, una conversación, una pregunta, una cadena "
               "reenviada, publicidad, un pronóstico general, una noticia de otro lugar o coordinación interna del grupo.")
P_NOMBRE = "En `texto`, ¿«{}» es el nombre o el apodo de una persona (no un lugar, una calle, un barrio, una institución ni una palabra común)?"
P_QUEDAN = "¿`texto` todavía nombra a una persona concreta por su nombre o apellido? «[nombre oculto]» no cuenta: ya está oculto."
P_MUESTRA = ("¿La foto `foto` muestra una situación de la emergencia en un lugar: agua acumulada o corriendo, inundación, quebrada crecida, "
             "lodo, vía dañada o cortada, deslizamiento, árbol o cable caído, daños, o un sitio de ayuda o acopio?")
P_PERSONA = "¿En `foto` aparece al menos una persona identificable: con la cara visible y lo bastante grande o nítida como para reconocerla?"
P_MENOR = "¿En `foto` aparece un niño, una niña o un adolescente, aunque sea de lejos o de espaldas?"
P_DOCUMENTO = "¿En `foto` se ve un documento, una cédula, una pantalla o un papel con nombres o números legibles, o una placa de vehículo legible?"


def _p(respuestas, clave):
    r = respuestas.get(clave) or {}
    return float(r["noul"]) if "noul" in r else None


class ClasificadorJev:
    nombre = "jev"

    def __init__(self, jev, tipos):
        self.jev, self.tipos = jev, tipos

    def _tipo_pregunta(self, sujeto):
        criterios = {t["codigo"]: t["nombre"] for t in self.tipos}
        return {"type": "choice", "instructions": f"¿Qué tipo de aviso describe {sujeto}?", "criteria": criterios}

    def texto(self, texto, tiene_foto):
        """{relevante, tipo, texto (sin nombres), retenido}. Dos pasos: quita los nombres probables y comprueba que no queden."""
        candidatos = list(dict.fromkeys(m.group(0) for m in CANDIDATO.finditer(texto)))[:40]
        preguntas = {"relevante": {"type": "noul", "instructions": P_RELEVANTE}, "tipo": self._tipo_pregunta("el mensaje")}
        for i, c in enumerate(candidatos):
            preguntas[f"n{i}"] = {"type": "noul", "instructions": P_NOMBRE.format(c)}
        r = self.jev.preguntar({"contexto": CONTEXTO, "texto": texto, "trae_foto": tiene_foto}, preguntas)
        limpio = texto
        for i, c in enumerate(candidatos):
            if (_p(r, f"n{i}") or 0) >= UMBRAL["nombre"]:
                limpio = re.sub(rf"(?<![\wáéíóúñ]){re.escape(c)}(?![\wáéíóúñ])", OCULTO, limpio)
        quedan = _p(self.jev.preguntar({"texto": limpio}, {"quedan": {"type": "noul", "instructions": P_QUEDAN}}), "quedan")
        retenido = quedan is None or quedan >= UMBRAL["quedan_nombres"]
        return {"relevante": _p(r, "relevante") or 0.0, "tipo": (r.get("tipo") or {}).get("choice"),
                "texto": "" if retenido else limpio, "retenido": retenido, "quedan": quedan}

    def foto(self, jpeg, texto):
        """{muestra, persona, menor, documento, tipo, revisar, motivo}. Si algo falla, revisar=True."""
        ref = "foto-" + uuid.uuid4().hex
        preguntas = {"muestra": {"type": "noul", "instructions": P_MUESTRA}, "persona": {"type": "noul", "instructions": P_PERSONA},
                     "menor": {"type": "noul", "instructions": P_MENOR}, "documento": {"type": "noul", "instructions": P_DOCUMENTO},
                     "tipo": self._tipo_pregunta("la foto `foto` junto con su texto")}
        try:
            r = self.jev.preguntar({"contexto": CONTEXTO, "foto": ref, "texto": texto or ""}, preguntas, {ref: jpeg})
        except ErrorClasificador as e:
            return {"revisar": True, "motivo": f"no se pudo revisar la foto ({e})", "muestra": None}
        salida = {k: _p(r, k) for k in ("muestra", "persona", "menor", "documento")}
        salida["tipo"] = (r.get("tipo") or {}).get("choice")
        motivos = [nombre for clave, nombre in (("persona", "persona identificable"), ("menor", "posible menor"), ("documento", "documento o datos legibles"))
                   if salida[clave] is None or salida[clave] >= UMBRAL[clave]]
        salida["revisar"], salida["motivo"] = bool(motivos), ", ".join(motivos)
        return salida


class ClasificadorReglas:
    """Respaldo sin modelo: decide la relevancia con palabras clave y manda TODAS las fotos a revisión.
    El texto no se publica (sin modelo no se puede comprobar que no lleve nombres)."""

    nombre = "reglas"
    TEMA = re.compile(r"inund|anegad|desbord|quebrada|canada|encanada|correntada|derrumbe|deslave|deslizamiento|via (cerrada|cortada)|"
                      r"no se puede pasar|cable caido|acopio|refugio|donacion|agua (en|hasta|por|llega|entra|sube)")

    def texto(self, texto, tiene_foto):
        return {"relevante": 1.0 if self.TEMA.search(_sin_tildes(texto)) else 0.0, "tipo": None, "texto": "", "retenido": True}

    def foto(self, jpeg, texto):
        return {"revisar": True, "motivo": "sin clasificador de fotos", "muestra": 0.5 if texto else None}


# ── Medios: fotos y fotogramas con ffmpeg ────────────────────────────────────
def ffmpeg():
    return shutil.which("ffmpeg") or next((p for p in ("/opt/homebrew/bin/ffmpeg", "/usr/local/bin/ffmpeg") if Path(p).exists()), None)


ESCALA = "scale=w='if(gte(iw,ih),max(min(iw,1280),320),-2)':h='if(gte(iw,ih),-2,max(min(ih,1280),320))'"


def _a_jpeg(entrada, salida, desde_s=None):
    orden = [ffmpeg(), "-v", "error", "-y"] + (["-ss", f"{desde_s:.2f}"] if desde_s is not None else []) + [
        "-i", str(entrada), "-frames:v", "1", "-vf", ESCALA, "-map_metadata", "-1", "-q:v", "4", str(salida)]
    subprocess.run(orden, capture_output=True, timeout=120, check=True)
    datos = Path(salida).read_bytes()
    if not datos.startswith(b"\xff\xd8"):
        raise ValueError("ffmpeg no dio un JPEG")
    return datos


def preparar_foto(archivo):
    """La foto vuelta a codificar en JPEG, de 320 a 1280 px de lado y sin metadatos."""
    with tempfile.TemporaryDirectory() as d:
        return _a_jpeg(archivo, Path(d) / "f.jpg")


def duracion(archivo):
    ffprobe = str(Path(ffmpeg()).with_name("ffprobe"))
    hecho = subprocess.run([ffprobe, "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(archivo)], capture_output=True, text=True, timeout=60)
    try:
        return float(hecho.stdout.strip())
    except ValueError:
        return 0.0


def fotogramas(archivo, cuantos=3):
    """Fotogramas al 20 %, 50 % y 80 % del video."""
    largo = duracion(archivo)
    puntos = [largo * f for f in (0.2, 0.5, 0.8)][:cuantos] if largo > 1 else [0.0]
    salida = []
    with tempfile.TemporaryDirectory() as d:
        for i, t in enumerate(puntos):
            try:
                salida.append(_a_jpeg(archivo, Path(d) / f"{i}.jpg", t))
            except Exception:
                pass
    return salida


# ── Registro (en la carpeta, nunca en el repositorio) ────────────────────────
class Registro:
    def __init__(self, carpeta):
        self.archivo = carpeta / REGISTRO
        self.filas = {}
        if self.archivo.exists():
            for linea in self.archivo.read_text().splitlines():
                try:
                    fila = json.loads(linea)
                    self.filas[fila["id"]] = fila
                except (ValueError, KeyError):
                    pass

    def hecho(self, id_mensaje):
        fila = self.filas.get(id_mensaje)
        return bool(fila) and (fila["resultado"] != "error" or fila.get("intentos", 1) >= INTENTOS_MAXIMOS)

    def anotar(self, id_mensaje, **datos):
        intentos = self.filas.get(id_mensaje, {}).get("intentos", 0) + (1 if datos.get("resultado") == "error" else 0)
        fila = {"id": id_mensaje, "en": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"), "intentos": intentos, **datos}
        self.filas[id_mensaje] = fila
        with self.archivo.open("a") as f:
            f.write(json.dumps(fila, ensure_ascii=False) + "\n")


# ── Servidor ─────────────────────────────────────────────────────────────────
class Plataforma:
    def __init__(self, servidor, llave):
        self.base, self.llave = servidor.rstrip("/") + "/riesgos/api/ingesta", llave

    def tipos(self):
        try:
            pedido = urllib.request.Request(self.base + "/tipos", headers={"X-Llave": self.llave, "User-Agent": "sosgalapagos-ingesta"})
            with urllib.request.urlopen(pedido, timeout=30) as r:
                return json.load(r)["tipos"] or TIPOS_POR_DEFECTO
        except Exception as e:
            aviso("No pude leer los tipos del servidor; uso los de siempre:", type(e).__name__)
            return TIPOS_POR_DEFECTO

    def subir(self, campos, foto=None):
        frontera = "----sosg" + uuid.uuid4().hex
        partes = []
        for k, v in campos.items():
            if v is None or v == "":
                continue
            partes.append(f'--{frontera}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode())
        if foto:
            partes.append(f'--{frontera}\r\nContent-Disposition: form-data; name="foto"; filename="foto.jpg"\r\nContent-Type: image/jpeg\r\n\r\n'.encode() + foto + b"\r\n")
        cuerpo = b"".join(partes) + f"--{frontera}--\r\n".encode()
        pedido = urllib.request.Request(self.base + "/whatsapp", data=cuerpo, headers={
            "X-Llave": self.llave, "Content-Type": f"multipart/form-data; boundary={frontera}", "User-Agent": "sosgalapagos-ingesta"})
        try:
            with urllib.request.urlopen(pedido, timeout=60) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            detalle = e.read()[:200].decode(errors="replace")
            raise RuntimeError(f"la plataforma respondió {e.code}: {detalle}")


# ── 3. Procesar ──────────────────────────────────────────────────────────────
def id_origen(id_mensaje):
    """Un resumen del id de WhatsApp: no deja volver al grupo ni a la persona, y no cambia entre corridas."""
    return "wa:" + hashlib.sha256(id_mensaje.encode()).hexdigest()[:40]


def clasificar_rafaga(rafaga, carpeta_chat, ubicaciones, clasificador, conocidos, zona):
    """Decide qué hacer con una ráfaga. Devuelve (resultado, elementos), con resultado «ruido», «subir» o «error»."""
    textos = [(m.get("body") or "").strip() for m in rafaga if m.get("type") in ("text", "chat", "image", "video") and (m.get("body") or "").strip()]
    textos = [t for t in textos if not t.startswith("/9j/") and len(t) < 3000]  # el cuerpo de una ubicación es una miniatura
    crudo = "\n".join(textos)
    punto = None
    for m in rafaga:
        if m.get("type") == "location":
            hora = datetime.datetime.fromtimestamp(m["timestamp"], zona).strftime("%Y-%m-%d %H:%M:%S")
            par = ubicaciones.get(hora)
            if par and en_galapagos(*par):
                punto = par
    punto = punto or lugar_del_texto(crudo)
    texto = limpiar_texto(crudo, conocidos)

    medios = []
    for m in rafaga:
        archivo = archivo_de(carpeta_chat, m)
        if archivo:
            medios.append((m, archivo))

    info_texto = clasificador.texto(texto, bool(medios)) if texto else {"relevante": 0.0, "tipo": None, "texto": "", "retenido": False}
    elementos = []
    for m, archivo in medios:
        es_video = m["type"] == "video"
        try:
            cuadros = fotogramas(archivo) if es_video else [preparar_foto(archivo)]
        except Exception:
            cuadros = []
        if not cuadros:
            elementos.append({"m": m, "foto": None, "es_video": es_video, "revisar": True, "motivo": "no se pudo leer el archivo", "muestra": None, "archivo": archivo})
            continue
        revisiones = [(c, clasificador.foto(c, info_texto["texto"])) for c in cuadros]
        # Del video se muestra el fotograma que mejor enseña lo que pasa; se revisa si cualquiera lo pide.
        mejor, info = max(revisiones, key=lambda x: x[1].get("muestra") or 0)
        motivos = sorted({r["motivo"] for _, r in revisiones if r.get("revisar") and r.get("motivo")})
        elementos.append({"m": m, "foto": mejor, "es_video": es_video, "revisar": any(r.get("revisar") for _, r in revisiones),
                          "motivo": ", ".join(motivos), "muestra": info.get("muestra"), "tipo": info.get("tipo"),
                          "clasif": {k: info.get(k) for k in ("muestra", "persona", "menor", "documento")}, "archivo": archivo})

    relevancia = max([info_texto["relevante"]] + [e["muestra"] or 0 for e in elementos])
    if relevancia < UMBRAL["relevante"]:
        return "ruido", []
    if not elementos:
        if not info_texto["texto"]:
            return "ruido", []  # un aviso solo de texto que no se puede publicar sin nombres no sirve aquí
        primero = next(m for m in rafaga if (m.get("body") or "").strip())
        elementos.append({"m": primero, "foto": None, "es_video": False, "revisar": False, "motivo": "", "muestra": None, "archivo": None})
    for e in elementos:
        e.update(texto=info_texto["texto"], punto=punto, tipo=e.get("tipo") or info_texto["tipo"],
                 clasificacion={"proveedor": clasificador.nombre, "relevante": round(relevancia, 3), "texto_retenido": info_texto["retenido"],
                                **{k: (round(v, 3) if isinstance(v, float) else v) for k, v in (e.get("clasif") or {}).items()}})
    return "subir", elementos


def procesar(cfg, grupos, carpeta, ensayo=False, desde_h=None, limite=None, plataforma=None, clasificador=None, ahora=None):
    ahora = ahora or time.time()
    zona = ZoneInfo(grupos.get("tz") or "Pacific/Galapagos")
    chats = carpetas_de_grupos(grupos, carpeta)
    registro = Registro(carpeta)
    plataforma = plataforma or Plataforma(cfg["INGESTA_SERVIDOR"], cfg.get("INGESTA_LLAVE", ""))
    if not ensayo and not plataforma.llave:
        raise SystemExit("Falta INGESTA_LLAVE")
    if clasificador is None:
        tipos = plataforma.tipos() if plataforma.llave else TIPOS_POR_DEFECTO
        if cfg.get("TYPESAFE_API_KEY"):
            clasificador = ClasificadorJev(Jev(cfg["TYPESAFE_API_KEY"], cfg["TYPESAFE_URL"], cfg["TYPESAFE_MODELO"]), tipos)
        else:
            aviso("Sin TYPESAFE_API_KEY: clasificación con reglas, todas las fotos a revisión")
            clasificador = ClasificadorReglas()
    if not ffmpeg():
        aviso("No encuentro ffmpeg: las fotos y los videos irán a revisión")
    conocidos = nombres_conocidos(carpeta, chats)
    desde = ahora - (desde_h if desde_h is not None else 7 * 24) * 3600
    cuentas = {"mapa": 0, "ubicar": 0, "revision": 0, "repetida": 0, "ruido": 0, "ya": 0, "error": 0, "ignorados": 0}
    hechas = 0
    for carpeta_chat in chats:
        try:
            mensajes = json.loads((carpeta_chat / "mensajes.json").read_text())
        except ValueError:
            continue
        ubicaciones = ubicaciones_del_txt(carpeta_chat)
        nuevos = []
        for m in mensajes:
            ident = m.get("waMessageId") or m.get("id")
            if not ident or (m.get("timestamp") or 0) < desde or registro.hecho(ident):
                continue
            if m.get("type") not in TIPOS_PROCESADOS:
                cuentas["ignorados"] += 1
                if not ensayo:
                    registro.anotar(ident, chat=str(carpeta_chat.relative_to(carpeta)), resultado="ignorado", tipo=m.get("type"))
                continue
            nuevos.append(m)
        for rafaga in rafagas(nuevos, ahora):
            if limite and hechas >= limite:
                break
            hechas += 1
            ids = [m.get("waMessageId") or m["id"] for m in rafaga]
            relativo = str(carpeta_chat.relative_to(carpeta))
            try:
                resultado, elementos = clasificar_rafaga(rafaga, carpeta_chat, ubicaciones, clasificador, conocidos, zona)
            except ErrorClasificador as e:
                aviso(f"{relativo}: el clasificador falló ({e}); se reintenta en la próxima corrida")
                cuentas["error"] += 1
                if not ensayo:
                    for i in ids:
                        registro.anotar(i, chat=relativo, resultado="error", detalle=str(e)[:120])
                continue
            if resultado == "ruido":
                cuentas["ruido"] += 1
                if not ensayo:
                    for i in ids:
                        registro.anotar(i, chat=relativo, resultado="ruido")
                continue
            subidos = {}
            for e in elementos:
                m = e["m"]
                ident = m.get("waMessageId") or m["id"]
                campos = {
                    "id_origen": id_origen(ident),
                    "visto_en": datetime.datetime.fromtimestamp(m["timestamp"], datetime.timezone.utc).isoformat(),
                    "texto": e["texto"], "tipo": e.get("tipo") or "",
                    "lat": f"{e['punto'][0]:.6f}" if e["punto"] else "", "lon": f"{e['punto'][1]:.6f}" if e["punto"] else "",
                    "revisar": "1" if e["revisar"] else "", "motivo": e["motivo"], "es_video": "1" if e["es_video"] else "",
                    "clasificacion": json.dumps(e["clasificacion"], ensure_ascii=False),
                }
                if ensayo:
                    destino = "revision" if e["revisar"] else ("mapa" if e["punto"] else "ubicar")
                    cuentas[destino] += 1
                    continue
                try:
                    respuesta = plataforma.subir(campos, e["foto"])
                    destino = "ya" if respuesta.get("ya") else respuesta.get("destino", "ubicar")
                    cuentas[destino] = cuentas.get(destino, 0) + 1
                    subidos[ident] = {"resultado": destino, "id_origen": campos["id_origen"], "archivo": e["archivo"].name if e["archivo"] else "",
                                      "publico": respuesta.get("id", ""), "reporte": respuesta.get("reporte", "")}
                except Exception as error:
                    aviso(f"{relativo}: no se pudo subir ({error}); se reintenta en la próxima corrida")
                    cuentas["error"] += 1
                    subidos[ident] = {"resultado": "error", "detalle": str(error)[:120]}
            if not ensayo:
                fallo = any(s["resultado"] == "error" for s in subidos.values())
                for i in ids:
                    registro.anotar(i, chat=relativo, **subidos.get(i, {"resultado": "error" if fallo else "parte"}))
    return cuentas


# ── Entrada ──────────────────────────────────────────────────────────────────
def _horas(valor):
    m = re.fullmatch(r"(\d+)([hd])", valor or "")
    if not m:
        raise argparse.ArgumentTypeError("usa por ejemplo 48h o 7d")
    return int(m.group(1)) * (24 if m.group(2) == "d" else 1)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("paso", choices=["horario", "descargar", "procesar"])
    ap.add_argument("--carpeta", help="carpeta de la exportación (por defecto INGESTA_CARPETA o ~/Downloads/WhatsApp lluvias 2027)")
    ap.add_argument("--grupos", help="JSON con los grupos (por defecto INGESTA_GRUPOS)")
    ap.add_argument("--ensayo", action="store_true", help="clasifica y cuenta, pero no sube ni anota nada")
    ap.add_argument("--desde", type=_horas, help="solo mensajes de las últimas N horas (48h, 7d). Por defecto, 7 días")
    ap.add_argument("--limite", type=int, help="como mucho N ráfagas en esta corrida")
    ap.add_argument("--sin-descarga", action="store_true", help="en «horario», no llama a wa_export.py")
    a = ap.parse_args(argv)
    cfg = configuracion()
    carpeta = Path(a.carpeta or cfg["INGESTA_CARPETA"]).expanduser()
    grupos_ruta = a.grupos or cfg.get("INGESTA_GRUPOS")
    grupos = leer_grupos(grupos_ruta)
    if a.paso in ("horario", "descargar") and not a.sin_descarga:
        descargar(cfg, grupos_ruta, carpeta)
    if a.paso in ("horario", "procesar"):
        cuentas = procesar(cfg, grupos, carpeta, ensayo=a.ensayo, desde_h=a.desde, limite=a.limite)
        print(json.dumps({"ensayo": a.ensayo, **cuentas}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())

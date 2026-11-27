# SOS Galápagos · © 2026 Universidad San Francisco de Quito (USFQ) · Autor: Julián Maya <jamaya@usfq.edu.ec>
# Licencia Apache 2.0 (ver LICENSE y NOTICE): puede reutilizarse dando crédito.
"""Pruebas del cliente de la Mac (despliegue/ingesta/ingesta.py), sin WhatsApp, sin Jev y sin ffmpeg.

Todos los datos son inventados. Jev, OpenWA y la plataforma se reemplazan por dobles.
"""
import importlib.util
import json
import time
from io import BytesIO
from pathlib import Path

import pytest
from PIL import Image

RUTA = Path(__file__).resolve().parents[2] / "despliegue" / "ingesta" / "ingesta.py"
_spec = importlib.util.spec_from_file_location("ingesta_cliente", RUTA)
I = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(I)

AHORA = int(time.time())  # las horas de los mensajes de prueba se cuentan desde ahora
GRUPO = "120363000000000001@g.us"
PRIVADO = "593000000000@c.us"


def jpeg(color="steelblue"):
    salida = BytesIO()
    Image.new("RGB", (400, 300), color).save(salida, "JPEG")
    return salida.getvalue()


def msg(n, tipo="text", cuerpo="", hace_min=60, autor="111@lid", chat=GRUPO):
    return {"id": f"{n:08d}-0000-0000-0000-000000000000", "waMessageId": f"false_{chat}_{n:08X}_{autor}", "chatId": chat,
            "author": autor, "from": autor, "type": tipo, "body": cuerpo, "timestamp": AHORA - hace_min * 60, "direction": "incoming"}


def armar(tmp_path, mensajes, carpeta="Barrio de prueba", chat_txt="", adjuntos=()):
    d = tmp_path / carpeta
    d.mkdir(parents=True, exist_ok=True)
    (d / "mensajes.json").write_text(json.dumps(mensajes))
    (d / "mensajes.txt").write_text(chat_txt)
    for m in adjuntos:
        (d / f"120000_{m['type']}_{m['id'][:8]}.{'jpg' if m['type'] == 'image' else 'mp4'}").write_bytes(jpeg())
    return d


GRUPOS = {"tz": "Pacific/Galapagos", "sessions": {"trabajo": {"chats": [{"id": GRUPO, "name": "Barrio de prueba"}]}}}


class ClasificadorFalso:
    """Relevante si el texto habla de agua; la foto «roja» tiene una cara."""

    nombre = "falso"

    def __init__(self, falla=False):
        self.falla, self.textos, self.fotos = falla, [], 0

    def texto(self, texto, tiene_foto):
        if self.falla:
            raise I.ErrorClasificador("caído")
        self.textos.append(texto)
        return {"relevante": 0.9 if "agua" in texto or "quebrada" in texto else 0.05, "tipo": "agua_via", "texto": texto, "retenido": False}

    def foto(self, datos, texto):
        self.fotos += 1
        cara = Image.open(BytesIO(datos)).getpixel((5, 5))[0] > 200
        return {"muestra": 0.8, "persona": 0.9 if cara else 0.0, "menor": 0.0, "documento": 0.0, "tipo": None,
                "revisar": cara, "motivo": "persona identificable" if cara else ""}


class PlataformaFalsa:
    llave = "x"

    def __init__(self):
        self.subidos = []

    def tipos(self):
        return I.TIPOS_POR_DEFECTO

    def subir(self, campos, foto=None):
        ya = any(s["id_origen"] == campos["id_origen"] for s, _ in self.subidos)
        self.subidos.append((campos, foto))
        destino = "revision" if campos.get("revisar") else ("mapa" if campos.get("lat") else "ubicar")
        return {"ya": ya, "destino": destino, "id": "abc12345"}


@pytest.fixture(autouse=True)
def sin_ffmpeg(monkeypatch):
    monkeypatch.setattr(I, "preparar_foto", lambda archivo: Path(archivo).read_bytes())
    monkeypatch.setattr(I, "fotogramas", lambda archivo: [jpeg("darkgreen"), jpeg("darkgreen")])


def correr(tmp_path, **k):
    return I.procesar({}, GRUPOS, tmp_path, ahora=AHORA, desde_h=48, **k)


# ── Piezas ───────────────────────────────────────────────────────────────────
def prueba_rafagas_por_persona_y_maduras():
    a, b = msg(1, hace_min=30), msg(2, hace_min=28)            # misma persona, 2 min: juntas
    c = msg(3, hace_min=29, autor="222@lid")                   # otra persona
    d = msg(4, hace_min=2)                                     # demasiado reciente: espera
    r = I.rafagas([a, b, c, d], AHORA)
    assert [[m["id"][:8] for m in x] for x in r] == [["00000001", "00000002"], ["00000003"]]


def prueba_limpiar_texto_quita_telefonos_menciones_enlaces_y_nombres_conocidos():
    t = I.limpiar_texto("Dice Rosa Pérez @593999111222 que llamen al 099 123 4567, ver https://x.y/z o rosa@correo.ec", {"Rosa Pérez"})
    assert "Rosa" not in t and "593999111222" not in t and "4567" not in t and "https" not in t and "correo" not in t
    assert "[nombre oculto]" in t and "[número oculto]" in t


def prueba_lugar_del_texto():
    assert I.lugar_del_texto("aquí https://maps.google.com/?q=-0.7435,-90.3145 ") == (-0.7435, -90.3145)
    assert I.lugar_del_texto("coordenadas -0.74350, -90.31450") == (-0.7435, -90.3145)
    assert I.lugar_del_texto("https://maps.google.com/?q=-2.19,-79.88") is None  # Guayaquil: fuera de Galápagos
    assert I.lugar_del_texto("en la calle Marchena") is None


def prueba_ubicaciones_del_txt(tmp_path):
    d = armar(tmp_path, [], chat_txt="[2026-11-22 10:00:05] Persona: [location] Mi casa lat=-0.7435, lon=-90.3145 https://maps.google.com/?q=-0.7435,-90.3145\n")
    assert I.ubicaciones_del_txt(d) == {"2026-11-22 10:00:05": (-0.7435, -90.3145)}


def prueba_solo_grupos_configurados(tmp_path):
    armar(tmp_path, [msg(1)])
    armar(tmp_path, [msg(2, chat=PRIVADO)], carpeta="Alguien")  # un chat privado nunca se procesa
    todos = {"sessions": {"trabajo": {"chats": "all"}}}
    assert [d.name for d in I.carpetas_de_grupos(todos, tmp_path)] == ["Barrio de prueba"]


def prueba_no_se_pierde_nada_si_wa_export_reescribe_con_menos(tmp_path):
    d = armar(tmp_path, [msg(1), msg(2)], chat_txt="viejo")
    antes = I._instantanea(tmp_path)
    (d / "mensajes.json").write_text(json.dumps([msg(2), msg(3)]))
    (d / "mensajes.txt").write_text("nuevo")
    I._no_perder_nada(antes)
    ids = [m["id"][:8] for m in json.loads((d / "mensajes.json").read_text())]
    assert sorted(ids) == ["00000001", "00000002", "00000003"]
    assert any(p.read_text() == "viejo" for p in d.glob("mensajes.anterior-*.txt"))


# ── De punta a punta ─────────────────────────────────────────────────────────
def prueba_foto_con_ubicacion_va_al_mapa_y_sin_ubicacion_a_ubicar(tmp_path):
    foto1 = msg(1, "image", hace_min=60)
    texto1 = msg(2, "text", "Así está el agua en mi calle", hace_min=59)
    ubic1 = msg(3, "location", "/9j/miniatura", hace_min=58)
    foto2 = msg(4, "image", hace_min=40, autor="222@lid")
    texto2 = msg(5, "text", "se desbordó la quebrada", hace_min=40, autor="222@lid")
    hora = time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime(ubic1["timestamp"] - 6 * 3600))
    armar(tmp_path, [foto1, texto1, ubic1, foto2, texto2], chat_txt=f"[{hora}] P: [location] lat=-0.7435, lon=-90.3145\n", adjuntos=[foto1, foto2])
    plataforma = PlataformaFalsa()
    cuentas = correr(tmp_path, plataforma=plataforma, clasificador=ClasificadorFalso())
    assert cuentas["mapa"] == 1 and cuentas["ubicar"] == 1
    con_punto = next(c for c, _ in plataforma.subidos if c["lat"])
    assert con_punto["lat"] == "-0.743500" and con_punto["texto"] == "Así está el agua en mi calle"
    # A la plataforma nunca llega el grupo, el autor ni el id de WhatsApp.
    for campos, _ in plataforma.subidos:
        enviado = json.dumps(campos)
        assert GRUPO not in enviado and "111@lid" not in enviado and "Barrio de prueba" not in enviado and "false_" not in enviado
        assert campos["id_origen"].startswith("wa:")


def prueba_ruido_se_cuenta_y_no_se_sube(tmp_path):
    armar(tmp_path, [msg(1, "text", "buenos días a todos"), msg(2, "sticker", hace_min=50, autor="333@lid")])
    plataforma = PlataformaFalsa()
    cuentas = correr(tmp_path, plataforma=plataforma, clasificador=ClasificadorFalso())
    assert cuentas["ruido"] == 1 and cuentas["ignorados"] == 1 and not plataforma.subidos


def prueba_foto_con_persona_va_a_revision(tmp_path):
    foto = msg(1, "image", hace_min=60)
    d = armar(tmp_path, [foto, msg(2, "text", "agua por todos lados", hace_min=59)])
    (d / f"120000_image_{foto['id'][:8]}.jpg").write_bytes(jpeg("red"))
    plataforma = PlataformaFalsa()
    correr(tmp_path, plataforma=plataforma, clasificador=ClasificadorFalso())
    campos, _ = plataforma.subidos[0]
    assert campos["revisar"] == "1" and "persona" in campos["motivo"]


def prueba_video_sube_un_fotograma(tmp_path):
    video = msg(1, "video", hace_min=60)
    armar(tmp_path, [video, msg(2, "text", "la quebrada así", hace_min=60)], adjuntos=[video])
    plataforma = PlataformaFalsa()
    correr(tmp_path, plataforma=plataforma, clasificador=ClasificadorFalso())
    campos, foto = plataforma.subidos[0]
    assert campos["es_video"] == "1" and foto.startswith(b"\xff\xd8")


def prueba_segunda_corrida_no_repite_nada(tmp_path):
    foto = msg(1, "image", hace_min=60)
    armar(tmp_path, [foto, msg(2, "text", "agua en la vía", hace_min=59), msg(3, "text", "hola", hace_min=30, autor="9@lid")], adjuntos=[foto])
    plataforma, clasificador = PlataformaFalsa(), ClasificadorFalso()
    correr(tmp_path, plataforma=plataforma, clasificador=clasificador)
    antes = (len(plataforma.subidos), len(clasificador.textos))
    cuentas = correr(tmp_path, plataforma=plataforma, clasificador=clasificador)
    assert (len(plataforma.subidos), len(clasificador.textos)) == antes
    assert sum(cuentas.values()) == 0
    # El registro, en la carpeta, dice de qué archivo salió cada cosa.
    filas = [json.loads(l) for l in (tmp_path / I.REGISTRO).read_text().splitlines()]
    assert any(f.get("archivo", "").endswith(".jpg") for f in filas)


def prueba_ensayo_no_sube_ni_anota(tmp_path):
    foto = msg(1, "image", hace_min=60)
    armar(tmp_path, [foto, msg(2, "text", "agua en la vía", hace_min=59)], adjuntos=[foto])
    plataforma = PlataformaFalsa()
    cuentas = correr(tmp_path, plataforma=plataforma, clasificador=ClasificadorFalso(), ensayo=True)
    assert cuentas["ubicar"] == 1 and not plataforma.subidos and not (tmp_path / I.REGISTRO).exists()


def prueba_si_el_clasificador_falla_se_reintenta(tmp_path):
    armar(tmp_path, [msg(1, "text", "agua en la vía")])
    plataforma = PlataformaFalsa()
    assert correr(tmp_path, plataforma=plataforma, clasificador=ClasificadorFalso(falla=True))["error"] == 1
    assert correr(tmp_path, plataforma=plataforma, clasificador=ClasificadorFalso())["ubicar"] == 1


# ── Jev, con un doble que responde como la API real ───────────────────────────
class JevFalso:
    def __init__(self, respuestas, falla_fotos=False):
        self.respuestas, self.falla_fotos, self.pedidos = respuestas, falla_fotos, []

    def preguntar(self, estado, preguntas, imagenes=None):
        self.pedidos.append((estado, preguntas, imagenes))
        if imagenes and self.falla_fotos:
            raise I.ErrorClasificador("400")
        return {k: self.respuestas.get(k, {"type": "noul", "noul": 0.0}) for k in preguntas}


def prueba_jev_oculta_los_nombres_y_retiene_si_quedan_dudas():
    jev = JevFalso({"relevante": {"type": "noul", "noul": 0.95}, "n0": {"type": "noul", "noul": 0.9}, "n1": {"type": "noul", "noul": 0.1},
                    "tipo": {"type": "choice", "choice": "agua_via"}})
    r = I.ClasificadorJev(jev, I.TIPOS_POR_DEFECTO).texto("Pedro dice que en Bellavista hay agua", False)
    assert r["texto"] == "[nombre oculto] dice que en Bellavista hay agua" and r["tipo"] == "agua_via"
    jev.respuestas["quedan"] = {"type": "noul", "noul": 0.8}
    r = I.ClasificadorJev(jev, I.TIPOS_POR_DEFECTO).texto("Pedro dice que hay agua", False)
    assert r["retenido"] and r["texto"] == ""


def prueba_jev_sin_respuesta_de_foto_la_manda_a_revision():
    jev = JevFalso({}, falla_fotos=True)
    r = I.ClasificadorJev(jev, I.TIPOS_POR_DEFECTO).foto(jpeg(), "")
    assert r["revisar"]


def prueba_sin_jev_todo_a_revision_y_sin_texto():
    c = I.ClasificadorReglas()
    assert c.foto(jpeg(), "x")["revisar"] and c.texto("se inundó la calle", True)["texto"] == ""


# ── Contra la plataforma de verdad (vista y base de prueba) ──────────────────
@pytest.mark.django_db
def prueba_de_la_carpeta_a_ayudanos_a_ubicar(tmp_path, client, settings):
    from reportes.models import PorUbicar

    settings.INGESTA_LLAVE = "llave"

    class PorElCliente(PlataformaFalsa):
        def subir(self, campos, foto=None):
            datos = {k: v for k, v in campos.items() if v}
            if foto:
                from django.core.files.uploadedfile import SimpleUploadedFile

                datos["foto"] = SimpleUploadedFile("foto.jpg", foto, content_type="image/jpeg")
            return client.post("/riesgos/api/ingesta/whatsapp", datos, headers={"X-Llave": "llave"}).json()

    foto = msg(1, "image", hace_min=60)
    armar(tmp_path, [foto, msg(2, "text", "agua hasta la rodilla", hace_min=59)], adjuntos=[foto])
    cuentas = I.procesar({}, GRUPOS, tmp_path, ahora=AHORA, desde_h=48, plataforma=PorElCliente(), clasificador=ClasificadorFalso())
    assert cuentas["ubicar"] == 1
    item = PorUbicar.objects.get()
    assert item.texto == "agua hasta la rodilla" and item.foto

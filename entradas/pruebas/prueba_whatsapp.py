# SOS Galápagos · © 2026 Universidad San Francisco de Quito (USFQ) · Autor: Julián Maya <jamaya@usfq.edu.ec>
# Todos los derechos reservados. Usar, copiar, modificar o derivar de este código requiere permiso escrito del autor (ver LICENSE).
"""Pruebas de WhatsApp: el filtro de reglas, el lugar, y la conversación completa sin modelo ni red."""
import json
from io import BytesIO

import pytest
from PIL import Image

from entradas import filtro, flujo, ia, lugar, openwa
from entradas.models import Conversacion, EstadoCola, MensajeEntrante
from reportes.models import Colaborador, Reporte

pytestmark = pytest.mark.django_db
CHAT = "593990000001@c.us"


@pytest.fixture(autouse=True)
def whatsapp(settings):
    settings.WHATSAPP_MODO = "activo"
    settings.WHATSAPP_CHATS = [CHAT]
    settings.WHATSAPP_DIRECTOS = False
    settings.WHATSAPP_SECRETO = "secreto-de-prueba"
    settings.OPENWA_LLAVE = settings.OPENWA_URL = settings.OPENWA_SESION = ""  # nunca se llama al servidor
    settings.IA_MODELO = ""  # extracción con reglas


@pytest.fixture
def enviados(monkeypatch):
    lista = []
    monkeypatch.setattr(openwa, "enviar_texto", lambda chat, texto: lista.append((chat, texto)))
    return lista


def mensaje(texto="", chat=CHAT, n=[0], **campos):
    n[0] += 1
    return openwa.Mensaje(id=f"m{n[0]}", chat=chat, autor=campos.pop("autor", chat), es_grupo=chat.endswith("@g.us"),
                          tipo=campos.pop("tipo", "text"), texto=texto, **campos)


def decir(texto="", **campos):
    foto = campos.pop("foto", None)
    guardado = flujo.recibir(mensaje(texto, **campos))
    return flujo.procesar(guardado.pk, foto=foto) if guardado else None


def jpeg():
    salida = BytesIO()
    Image.new("RGB", (60, 40), "teal").save(salida, "JPEG")
    return salida.getvalue()


# ── Filtro ───────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("texto", [
    "Se inundó la calle Marchena, el agua llega a la rodilla",
    "La vía a Bellavista está cerrada por un derrumbe en el km 4",
    "Hay un cable caído frente a la escuela del barrio El Edén",
    "Centro de acopio en la USFQ, reciben víveres y kits de higiene",
    "Tubería rota en la avenida Baltra, hay una fuga grande",
    "#sos quiero avisar algo",
])
def prueba_el_filtro_deja_pasar_lo_que_es_para_el_mapa(texto):
    assert filtro.evaluar(texto).es_material, filtro.evaluar(texto).motivos


@pytest.mark.parametrize("texto", [
    "Hola, buenos días",
    "jajaja",
    "¿A qué hora es la reunión de mañana?",
    "Te mando el informe en la tarde, gracias",
    "ok",
])
def prueba_el_filtro_descarta_la_conversacion_comun(texto):
    assert not filtro.evaluar(texto).es_material


def prueba_una_foto_sola_no_basta_pero_con_tema_si():
    assert not filtro.evaluar("", tiene_foto=True).es_material
    assert filtro.evaluar("así está la calle, toda inundada", tiene_foto=True).es_material


# ── Lugar ────────────────────────────────────────────────────────────────────
def prueba_saca_el_punto_de_enlaces_de_mapas():
    assert lugar.de_enlace("mira https://www.google.com/maps/place/-0.7412,-90.3135/@-0.7412,-90.3135,17z") == (-0.7412, -90.3135)
    assert lugar.de_enlace("https://maps.google.com/?q=-0.9020,-89.6100") == (-0.902, -89.61)
    assert lugar.de_enlace("https://www.google.com/maps/place/Quito/@-0.18,-78.47,12z") is None  # fuera de Galápagos
    corto = lugar.de_enlace("https://maps.app.goo.gl/AbCd", seguir=lambda u: "https://www.google.com/maps/place/X/@-0.7400,-90.3100,17z/data=!3d-0.7401!4d-90.3102")
    assert corto == (-0.7401, -90.3102)
    assert lugar.de_enlace("https://sitio-cualquiera.test/?q=-0.74,-90.31") is None
    assert lugar.de_coordenadas("estoy en -0.74120, -90.31350") == (-0.7412, -90.3135)


# ── Chats permitidos y privacidad ────────────────────────────────────────────
def prueba_un_chat_fuera_de_la_lista_no_se_lee(enviados):
    assert flujo.recibir(mensaje("Se inundó la calle Marchena", chat="593998888888@c.us")) is None
    assert MensajeEntrante.objects.count() == 0 and Conversacion.objects.count() == 0


def prueba_la_conversacion_comun_no_se_guarda(enviados):
    assert decir("Hola, buenos días") is None
    assert MensajeEntrante.objects.count() == 0 and not enviados


def prueba_apagado_no_atiende_nada(settings):
    settings.WHATSAPP_MODO = "apagado"
    assert flujo.recibir(mensaje("Se inundó la calle Marchena")) is None


def prueba_el_numero_nunca_queda_en_claro(enviados):
    decir("Se inundó la calle Marchena, el agua llega a la rodilla")
    c = Conversacion.objects.get()
    assert "593990000001" not in c.chat_hash and "593990000001" not in c.chat_cifrado
    assert flujo.descifrar(c.chat_cifrado) == CHAT
    assert "593990000001" not in json.dumps(list(MensajeEntrante.objects.values("remitente_hash", "candidato", "texto")), default=str)


def prueba_un_mensaje_repetido_no_se_procesa_dos_veces(enviados):
    m = mensaje("Se inundó la calle Marchena")
    assert flujo.recibir(m) is not None and flujo.recibir(m) is None


# ── Conversación completa ────────────────────────────────────────────────────
def prueba_pide_la_ubicacion_publica_y_responde_con_el_enlace(enviados, settings):
    r1 = decir("Se inundó la calle Marchena, el agua llega a la rodilla", tiene_foto=True, tipo="image", foto=jpeg())
    assert "ubicación" in r1 and "Google Maps" in r1 and "dirección exacta" in r1
    assert Reporte.objects.count() == 0
    r2 = decir("", tipo="location", lat=-0.7412, lon=-90.3135)
    reporte = Reporte.objects.get()
    assert reporte.fuente == "whatsapp" and reporte.estado == "por_verificar" and reporte.contenido_visible
    assert reporte.tipo.codigo == "agua_via" and reporte.foto and abs(reporte.punto.y + 0.7412) < 1e-6
    assert f"{settings.SITIO_URL}/riesgos/?r={reporte.id_publico}" in r2
    assert "Ganaste 15 puntos" in r2 and "nombre o apodo" in r2 and "911" in r2
    assert enviados[-1] == (CHAT, r2)
    # Después dice su nombre: queda en la tabla.
    r3 = decir("Me llamo Lucía")
    assert "Gracias, Lucía" in r3 and Colaborador.objects.get().nombre == "Lucía"
    assert MensajeEntrante.objects.filter(estado_cola=EstadoCola.PUBLICADO).count() == 2


def prueba_un_enlace_de_google_maps_vale_como_ubicacion(enviados):
    decir("Hay un derrumbe, la vía está cerrada https://maps.google.com/?q=-0.6950,-90.3260")
    assert abs(Reporte.objects.get().punto.x + 90.326) < 1e-6


def prueba_un_lugar_de_donacion_pide_el_telefono_del_sitio(enviados):
    r1 = decir("Centro de acopio en el coliseo, reciben víveres y ropa https://maps.google.com/?q=-0.7430,-90.3120")
    assert "teléfono" in r1 and Reporte.objects.count() == 0
    decir("el contacto es 05 252 6000, se inundó pero siguen recibiendo donaciones")
    reporte = Reporte.objects.get()
    assert reporte.tipo.codigo == "donar_colaborar" and reporte.contacto == "052526000"


def prueba_si_no_hay_telefono_se_publica_igual(enviados):
    decir("Punto de acopio, reciben donaciones de agua https://maps.google.com/?q=-0.7430,-90.3120")
    decir("no hay")
    assert Reporte.objects.get().contacto == ""


def prueba_sin_ubicacion_tras_insistir_pasa_a_coordinacion(enviados):
    decir("Se inundó toda la calle, el agua corre fuerte")
    decir("es por mi casa, se inundó feo")
    r = decir("no sé cómo mandar eso, se inundó y ya")
    assert "coordinación" in r and Reporte.objects.count() == 0
    assert MensajeEntrante.objects.filter(estado_cola=EstadoCola.PENDIENTE).exists()


def prueba_en_ensayo_no_publica_ni_envia(enviados, settings):
    settings.WHATSAPP_MODO = "ensayo"
    r = decir("Se inundó la calle Marchena https://maps.google.com/?q=-0.7412,-90.3135")
    assert r.startswith("[ensayo]") and Reporte.objects.count() == 0 and not enviados
    assert MensajeEntrante.objects.get().respuesta == r


def prueba_en_un_grupo_no_responde_si_no_esta_permitido(enviados, settings):
    grupo = "120363000000000000@g.us"
    settings.WHATSAPP_CHATS = [grupo]
    decir("Se inundó la calle Marchena https://maps.google.com/?q=-0.7412,-90.3135", chat=grupo, autor="593991111111@c.us")
    assert Reporte.objects.count() == 1 and not enviados


def prueba_se_borra_el_texto_viejo(enviados, settings):
    from datetime import timedelta

    from django.utils import timezone

    decir("Se inundó la calle Marchena https://maps.google.com/?q=-0.7412,-90.3135")
    MensajeEntrante.objects.update(recibido_en=timezone.now() - timedelta(days=8))
    Conversacion.objects.update(actualizada_en=timezone.now() - timedelta(days=8))
    assert flujo.purgar() == (1, 1)
    assert MensajeEntrante.objects.get().texto == "" and Reporte.objects.count() == 1


# ── Modelo de lenguaje, sin depender del proveedor ───────────────────────────
def prueba_la_extraccion_usa_el_modelo_configurado(settings):
    from pydantic_ai.models.test import TestModel

    settings.IA_MODELO = TestModel(custom_output_args={"es_reporte": True, "tipo": "dano_infraestructura", "titulo": "Puente dañado", "descripcion": "La baranda del puente se cayó"})
    e = ia.extraer(["el puente quedó mal"], foto=jpeg(), tipos=[], borrador={})
    assert e.es_reporte and e.tipo == "dano_infraestructura" and e.titulo == "Puente dañado"


def prueba_si_el_modelo_falla_se_usan_las_reglas(settings):
    settings.IA_MODELO = "anthropic:modelo-que-no-existe"
    e = ia.extraer(["Tubería rota en la avenida Baltra, hay una fuga"])
    assert e.es_reporte and e.tipo == "dano_infraestructura"


# ── Webhook ──────────────────────────────────────────────────────────────────
def prueba_el_webhook_pide_el_secreto_y_encola(client, monkeypatch, enviados):
    from entradas import tareas

    encolados = []
    monkeypatch.setattr(tareas, "procesar_mensaje", type("Tarea", (), {"enqueue": staticmethod(encolados.append)}))
    carga = {"event": "message.received", "data": {"waMessageId": "abc", "chatId": CHAT, "from": CHAT, "type": "text", "direction": "incoming",
                                                   "body": "Se inundó la calle Marchena, el agua llega a la rodilla"}}
    assert client.post("/riesgos/api/whatsapp/entrada", json.dumps(carga), content_type="application/json").status_code == 403
    r = client.post("/riesgos/api/whatsapp/entrada", json.dumps(carga), content_type="application/json", headers={"X-Secreto": "secreto-de-prueba"})
    assert r.json() == {"atendido": True} and len(encolados) == 1
    propio = {"data": {**carga["data"], "waMessageId": "def", "direction": "outgoing"}}
    r = client.post("/riesgos/api/whatsapp/entrada?secreto=secreto-de-prueba", json.dumps(propio), content_type="application/json")
    assert r.json() == {"atendido": False}


def prueba_normaliza_la_ubicacion_y_la_miniatura():
    m = openwa.normalizar({"data": {"waMessageId": "x", "chatId": CHAT, "type": "location", "body": "/9j/4AAQ" + "A" * 500,
                                    "location": {"latitude": -0.74, "longitude": -90.31}}})
    assert (m.lat, m.lon, m.texto) == (-0.74, -90.31, "")


def prueba_la_forma_del_webhook_no_lleva_contenido():
    from api.rutas import openwa_forma

    forma = json.dumps(openwa_forma({"event": "message.received", "data": {"chatId": CHAT, "body": "texto privado", "location": {"latitude": -0.74}, "ids": ["a"]}}))
    assert "593990000001" not in forma and "privado" not in forma
    assert '"latitude": "float"' in forma and "texto(13)" in forma

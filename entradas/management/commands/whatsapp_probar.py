# SOS Galápagos · © 2026 Universidad San Francisco de Quito (USFQ) · Autor: Julián Maya <jamaya@usfq.edu.ec>
# Licencia Apache 2.0 (ver LICENSE y NOTICE): puede reutilizarse dando crédito.
"""Conversa con el asistente de WhatsApp desde la terminal, sin WhatsApp.

  manage.py whatsapp_probar "Se inundó la calle Marchena, el agua llega a la rodilla"
  manage.py whatsapp_probar --ubicacion=-0.7412,-90.3135
  manage.py whatsapp_probar --foto ruta/foto.jpg "así está el puente"
  manage.py whatsapp_probar --solo-filtro "hola, buenos días"

Usa un chat de mentira («prueba@c.us»). En modo «ensayo» no publica nada; con --publicar
sí crea el reporte (solo en desarrollo).
"""
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from entradas import filtro, flujo, openwa


class Command(BaseCommand):
    help = "Simula un mensaje de WhatsApp y muestra qué respondería el asistente"

    def add_arguments(self, parser):
        parser.add_argument("texto", nargs="?", default="")
        parser.add_argument("--ubicacion", help="lat,lon como si mandara su ubicación")
        parser.add_argument("--foto", help="ruta de una foto")
        parser.add_argument("--chat", default="prueba@c.us")
        parser.add_argument("--solo-filtro", action="store_true", help="solo dice si pasa el filtro de reglas")
        parser.add_argument("--publicar", action="store_true", help="crea el reporte de verdad (solo en desarrollo)")

    def handle(self, texto, ubicacion, foto, chat, solo_filtro, publicar, **opciones):
        lat = lon = None
        if ubicacion:
            lat, lon = (float(x) for x in ubicacion.split(","))
        if solo_filtro:
            v = filtro.evaluar(texto, bool(foto), lat is not None)
            self.stdout.write(f"{'PASA' if v.es_material else 'NO PASA'} · puntaje {v.puntaje} · {'; '.join(v.motivos) or 'sin motivos'}")
            return
        if publicar and not settings.DEBUG:
            raise CommandError("--publicar solo funciona en desarrollo")
        import uuid

        settings.WHATSAPP_MODO = "activo" if publicar else "ensayo"
        settings.OPENWA_LLAVE = ""  # nunca se manda nada a WhatsApp desde aquí
        settings.WHATSAPP_CHATS = [chat]
        datos = open(foto, "rb").read() if foto else None
        mensaje = openwa.Mensaje(id=uuid.uuid4().hex, chat=chat, autor=chat, es_grupo=chat.endswith("@g.us"),
                                 tipo="image" if foto else "location" if ubicacion else "text", texto=texto,
                                 lat=lat, lon=lon, tiene_foto=bool(foto))
        guardado = flujo.recibir(mensaje)
        if not guardado:
            self.stdout.write("(no pasa el filtro: no se guarda ni se responde)")
            return
        self.stdout.write(f"filtro: {'; '.join(guardado.candidato['filtro'])}")
        self.stdout.write(f"modelo: {settings.IA_MODELO or 'ninguno (reglas)'}")
        self.stdout.write("asistente: " + (flujo.procesar(guardado.pk, foto=datos) or "(silencio)"))

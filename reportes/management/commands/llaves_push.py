# SOS Galápagos · © 2026 Universidad San Francisco de Quito (USFQ) · Autor: Julián Maya <jamaya@usfq.edu.ec>
# Licencia Apache 2.0 (ver LICENSE y NOTICE): puede reutilizarse dando crédito.
"""Genera el par de llaves de los avisos del navegador (VAPID). Se hace una sola vez."""
import base64

from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Imprime PUSH_PUBLICA y PUSH_PRIVADA para el .env"

    def handle(self, **opciones):
        from cryptography.hazmat.primitives import serialization
        from py_vapid import Vapid

        v = Vapid()
        v.generate_keys()
        b64 = lambda b: base64.urlsafe_b64encode(b).rstrip(b"=").decode()  # noqa: E731
        publica = v.public_key.public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)
        privada = v.private_key.private_numbers().private_value.to_bytes(32, "big")
        self.stdout.write(f"PUSH_PUBLICA={b64(publica)}")
        self.stdout.write(f"PUSH_PRIVADA={b64(privada)}")

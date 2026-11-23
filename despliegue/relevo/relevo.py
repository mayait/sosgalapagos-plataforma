#!/usr/bin/env python3
# SOS Galápagos · relevo de IERSE.
# © 2026 Universidad San Francisco de Quito (USFQ) · SOS Galápagos · Julián Maya <jamaya@usfq.edu.ec>
# Licencia Apache 2.0 (ver LICENSE y NOTICE en la raíz del repositorio): puede reutilizarse dando crédito.
"""Relevo: pide a IERSE lo que la plataforma le indica y le devuelve las respuestas tal cual.

Por qué existe: el servidor de IERSE (Universidad del Azuay) solo responde a conexiones desde
Ecuador, y el de sosgalapagos.org está fuera. Esta máquina, que sí está en Ecuador, hace de
mensajera. No interpreta nada, no guarda nada y no conoce a IERSE: la lista de pedidos se la
da la plataforma cada vez. Toda la lógica está en la plataforma (clima/fuentes/ierse.py).

Solo usa la biblioteca estándar de Python 3 (3.8 o más). Lo corre launchd o cron cada 5 minutos.
Configuración (variables de entorno o ~/.config/sosgalapagos/relevo.env, con permisos 600):
    RELEVO_SERVIDOR=https://sosgalapagos.org
    RELEVO_LLAVE=…        la misma que CLIMA_RELEVO_LLAVE en el servidor
"""
import ipaddress
import json
import os
import socket
import ssl
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

AQUI = Path(__file__).resolve().parent
RONDAS_MAXIMAS = 8      # tras un corte largo se pone al día en varias rondas
ESPERA_S = 40


def configuracion():
    archivo = Path(os.environ.get("RELEVO_ENV", Path.home() / ".config" / "sosgalapagos" / "relevo.env"))
    valores = {}
    if archivo.exists():
        for linea in archivo.read_text().splitlines():
            if "=" in linea and not linea.strip().startswith("#"):
                k, v = linea.split("=", 1)
                valores[k.strip()] = v.strip().strip('"').strip("'")
    servidor = os.environ.get("RELEVO_SERVIDOR") or valores.get("RELEVO_SERVIDOR") or "https://sosgalapagos.org"
    llave = os.environ.get("RELEVO_LLAVE") or valores.get("RELEVO_LLAVE")
    if not llave:
        sys.exit("Falta RELEVO_LLAVE (ver el encabezado de este archivo)")
    return servidor.rstrip("/"), llave


def tls():
    """Las raíces del sistema más el certificado intermedio que el servidor de IERSE no envía desde
    el 27-oct-2026 (es público, de DigiCert). La verificación sigue activa."""
    contexto = ssl.create_default_context()
    intermedios = AQUI / "ca-intermedios.pem"
    if intermedios.exists():
        contexto.load_verify_locations(str(intermedios))
    return contexto


def es_publica(url):
    """Solo se piden direcciones https de internet: nunca de esta máquina ni de su red local."""
    u = urllib.parse.urlsplit(url)
    if u.scheme != "https" or not u.hostname:
        return False
    try:
        direcciones = {a[4][0] for a in socket.getaddrinfo(u.hostname, u.port or 443)}
    except OSError:
        return False
    return all(ipaddress.ip_address(d).is_global for d in direcciones)


def pedir(url, cuerpo=None, cabeceras=None, contexto=None, agente="sosgalapagos-relevo/1.0"):
    datos = json.dumps(cuerpo).encode() if cuerpo is not None else None
    pedido = urllib.request.Request(url, data=datos, method="POST" if datos else "GET",
                                    headers={"Content-Type": "application/json", "User-Agent": agente, **(cabeceras or {})})
    with urllib.request.urlopen(pedido, timeout=ESPERA_S, context=contexto) as r:
        texto = r.read()
        return json.loads(texto) if texto.strip() else []


def ronda(servidor, llave, contexto):
    """Una ronda: preguntar qué pedir, pedirlo y entregar. Devuelve (guardadas, ¿queda más?)."""
    puerta, cabecera = f"{servidor}/riesgos/api/clima/relevo/ierse", {"X-Llave": llave}
    plan = pedir(puerta, cabeceras=cabecera, contexto=contexto)
    respuestas, errores = {}, []
    for p in plan.get("pedidos", []):
        if not es_publica(p["url"]):
            errores.append(f"{p['id']}: dirección no permitida")
            continue
        try:
            respuestas[p["id"]] = pedir(p["url"], p.get("cuerpo"), contexto=contexto, agente=plan.get("agente") or "sosgalapagos-clima")
        except Exception as e:
            errores.append(f"{p['id']}: {type(e).__name__}")
            if len(errores) >= 3 and not respuestas:
                break  # la fuente no responde: no vale la pena insistir con el resto
    r = pedir(puerta, {"respuestas": respuestas, "errores": errores[:5]}, cabeceras=cabecera, contexto=contexto)
    return r.get("guardadas", 0), bool(r.get("pendiente")), len(respuestas), errores


def main():
    servidor, llave = configuracion()
    contexto, total = tls(), 0
    for _ in range(RONDAS_MAXIMAS):
        guardadas, pendiente, respondidos, errores = ronda(servidor, llave, contexto)
        total += guardadas
        print(time.strftime("%Y-%m-%d %H:%M:%S"), f"respuestas {respondidos} · guardadas {guardadas}" + (f" · errores: {errores[:3]}" if errores else ""), flush=True)
        if not pendiente or not respondidos:
            break
    return 0 if total or not errores else 1


if __name__ == "__main__":
    sys.exit(main())

# SOS Galápagos · © 2026 Universidad San Francisco de Quito (USFQ) · Autor: Julián Maya <jamaya@usfq.edu.ec>
# Licencia Apache 2.0 (ver LICENSE y NOTICE): puede reutilizarse dando crédito.
"""Añade un documento oficial a la línea del tiempo y a la portada: un informe de un GAD, una resolución del COE…

  manage.py oficial_agregar gad-santa-cruz --archivo informe.pdf
  manage.py oficial_agregar coe --enlace https://… --titulo "Resolución del COE cantonal" --fecha 2026-11-23T15:00
  manage.py oficial_agregar gad-san-cristobal --archivo informe.pdf --zona san-cristobal --resumen "Qué dice…"

Si no se da el resumen (ni el título) y hay un modelo de lenguaje configurado, lee el PDF y los propone.
El documento queda público: no subas uno con nombres de personas afectadas, cédulas ni teléfonos.
"""
from datetime import datetime, timezone
from pathlib import Path

from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand, CommandError
from pydantic import BaseModel, Field

from reportes.models import ClaseSuceso, Institucion, Suceso, ZonaGrande


class DocumentoLeido(BaseModel):
    titulo: str = Field(description="Título del documento, corto y tal como se presenta (por ejemplo «Informe de situación n.º 5 del COE cantonal de Santa Cruz»).")
    fecha: str | None = Field(default=None, description="Fecha y hora del documento, ISO 8601 con zona (-06:00 si es hora de Galápagos).")
    resumen: str = Field(description="Qué dice, en 2 a 4 frases claras, máximo 550 caracteres: decisiones, cifras y lugares, tal como aparecen. Sin nombres de personas, cédulas ni teléfonos. Sin inventar nada.")


INSTRUCCIONES = """Lees un documento oficial de una institución de Galápagos (un GAD municipal, el COE, el Consejo de Gobierno) sobre la emergencia por lluvias, y rellenas el esquema.
- Copia cifras, fechas y lugares tal como aparecen. No inventes ni deduzcas.
- No escribas nombres de personas, cédulas ni teléfonos, aunque el documento los traiga.
- El resumen es para vecinos: claro, sin siglas sin explicar, y sin recomendaciones propias."""


class Command(BaseCommand):
    help = "Añade un documento oficial (GAD, COE…) a la línea del tiempo y a la portada"

    def add_arguments(self, parser):
        parser.add_argument("institucion", choices=[v for v, _ in Institucion.choices])
        parser.add_argument("--archivo", help="PDF del documento")
        parser.add_argument("--enlace", default="", help="Dirección del documento, si está publicado en internet")
        parser.add_argument("--titulo", default="")
        parser.add_argument("--resumen", default="")
        parser.add_argument("--fecha", default="", help="ISO 8601; sin zona se entiende hora de Galápagos")
        parser.add_argument("--zona", default="", choices=[""] + [v for v, _ in ZonaGrande.choices])

    def handle(self, institucion, archivo, enlace, titulo, resumen, fecha, zona, **opciones):
        if not archivo and not enlace:
            raise CommandError("Indica --archivo o --enlace.")
        contenido = Path(archivo).read_bytes() if archivo else None
        if contenido is not None and not contenido.startswith(b"%PDF-"):
            raise CommandError("El archivo no es un PDF.")
        if contenido and not (titulo and resumen):
            from clima.oficiales import leer_documento

            leido = leer_documento(contenido, "application/pdf", f"documento oficial de {Institucion(institucion).label}", DocumentoLeido, INSTRUCCIONES)
            if leido:
                titulo, resumen, fecha = titulo or leido.titulo, resumen or leido.resumen, fecha or (leido.fecha or "")
        if not titulo:
            raise CommandError("Falta --titulo (no hay modelo de lenguaje configurado para proponerlo).")
        cuando = datetime.now(timezone.utc)
        if fecha:
            try:
                cuando = datetime.fromisoformat(fecha.replace("Z", "+00:00"))
                if not cuando.tzinfo:
                    from clima.consultas import GALAPAGOS

                    cuando = cuando.replace(tzinfo=GALAPAGOS)
            except ValueError:
                raise CommandError("No entiendo la fecha: usa 2026-11-23T15:00.")
        s = Suceso(clase=ClaseSuceso.OFICIAL, institucion=institucion, titulo=titulo[:140], texto=resumen[:600], fuente=Institucion(institucion).label,
                   enlace=enlace, ocurrido=cuando, zona=zona)
        if contenido:
            s.archivo.save("documento.pdf", ContentFile(contenido), save=False)
        s.save()
        self.stdout.write(f"Añadido: {s.titulo} · {s.fuente} · {s.ocurrido:%Y-%m-%d %H:%M} → {s.destino}\n{s.texto}")

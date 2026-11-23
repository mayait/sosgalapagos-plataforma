# SOS Galápagos · © 2026 Universidad San Francisco de Quito (USFQ) · Autor: Julián Maya <jamaya@usfq.edu.ec>
# Todos los derechos reservados. Usar, copiar, modificar o derivar de este código requiere permiso escrito del autor (ver LICENSE).
"""Tareas periódicas del clima. Las encola el reloj."""
from django.tasks import task


@task
def ciclo_clima():
    """El ciclo de cada cinco minutos: recoger las fuentes, calcular el nivel de cada zona y
    generar los datos del panel. Una parte que falla no frena a las demás."""
    from django.conf import settings

    from . import fuentes, niveles, panel

    r = {"fuentes": fuentes.recolectar()}
    try:
        r["nivel"] = niveles.actualizar()
    except Exception as e:
        r["nivel"] = f"{type(e).__name__}: {e}"
    if settings.CLIMA_SALIDA:
        try:
            r["panel"] = panel.publicar()
        except Exception as e:
            r["panel"] = f"{type(e).__name__}: {e}"
    return r


@task
def publicar_descargas():
    """Cada hora: los ZIP de descarga pública."""
    from . import descargas

    return descargas.publicar()


@task
def guardar_pronostico():
    """Cada hora: lo que dijo cada modelo y lo que se publicó, para poder verificarlo después."""
    from . import pronostico

    leidas, nuevas = pronostico.guardar_modelos()
    return {"corridas": leidas, "modelos": nuevas, "publicados": pronostico.guardar_emitido()}


@task
def recalibrar_pronostico():
    from . import pronostico

    return [{k: str(v) for k, v in r.items()} for r in pronostico.recalibrar()]


@task
def revisar_alertas():
    from . import alertas

    return [a.clave for a in alertas.revisar()]


@task
def actualizar_oficiales():
    """Pronóstico del INAMHI y boletines nuevos (cada hora)."""
    from . import alertas, oficiales

    islas = oficiales.actualizar_pronostico_inamhi()
    nuevos = oficiales.revisar_boletines()
    alertas.revisar()  # un boletín nuevo se avisa enseguida
    return {"islas": islas, "boletines": [str(b) for b in nuevos]}


@task
def actualizar_mar(stormglass=True):
    """Tabla del INOCAR (sin cupo) y, dos veces al día, mareas y oleaje de Stormglass."""
    from . import mar

    r = {"inocar": mar.actualizar_inocar()}
    if stormglass:
        r["stormglass_mareas"] = mar.actualizar_stormglass_mareas()
        r["stormglass_mar"] = mar.actualizar_stormglass_mar()
    return r


@task
def actualizar_lluvia_mapa():
    """Cada hora: el mapa de lluvia de los modelos, solo si hay una corrida nueva del IFS (unas 957 llamadas)."""
    from django.conf import settings

    from . import lluvia_mapa

    if not settings.CLIMA_SALIDA or not lluvia_mapa.hay_corrida_nueva(settings.CLIMA_SALIDA):
        return {"lluvia_mapa": "sin corrida nueva"}
    return {"lluvia_mapa": str(lluvia_mapa.exportar(settings.CLIMA_SALIDA))}


@task
def actualizar_nino():
    """El Niño (índices, mar, boyas, MJO) y la ZCIT del NHC: escribe nino.json, nino_mapa.json y zcit.json (cada seis horas)."""
    from django.conf import settings

    from . import nino, zcit

    if not settings.CLIMA_SALIDA:
        return {}
    r = {"nino": nino.exportar(settings.CLIMA_SALIDA)}
    try:
        r["zcit"] = zcit.exportar(settings.CLIMA_SALIDA)
    except Exception as e:  # la discusión del NHC falla a veces: El Niño ya quedó escrito
        r["zcit"] = {"error": type(e).__name__}
    return r

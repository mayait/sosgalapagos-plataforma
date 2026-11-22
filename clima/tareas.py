"""Tareas periódicas del clima. Las encola el reloj."""
from django.tasks import task


@task
def sincronizar_clima():
    from .sincronizar import sincronizar

    s = sincronizar()
    r = {"leidas": s.leidas, "cambiadas": s.cambiadas, "borradas": s.borradas, "segundos": s.segundos, "error": s.error}
    if not s.error:  # con los datos frescos se recalcula el nivel de cada zona
        from . import niveles

        try:
            r["nivel"] = niveles.actualizar()
        except Exception as e:  # el cálculo nuevo está en prueba: un fallo no debe frenar la copia
            r["nivel"] = f"{type(e).__name__}: {e}"
    return r


@task
def guardar_pronostico():
    from . import pronostico

    leidos, nuevas = pronostico.guardar_archivo()
    return {"archivos": leidos, "modelos": nuevas, "publicados": pronostico.guardar_emitido()}


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


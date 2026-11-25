# SOS Galápagos · © 2026 Universidad San Francisco de Quito (USFQ) · Autor: Julián Maya <jamaya@usfq.edu.ec>
# Licencia Apache 2.0 (ver LICENSE y NOTICE): puede reutilizarse dando crédito.
"""«Lluvia medida ahora» en la portada: el nivel de cada zona, leído en el servidor.

Desde el 25-nov-2026 la portada abre con la animación de la lluvia de las próximas 24 horas y de
lo medido muestra solo el nivel de cada zona, con enlace a su detalle en /clima/. `filas()` sigue
armando también las cifras («7 mm en la última hora») y la línea de causa: no se pintan en la
portada, pero quedan listas y probadas por si vuelven.

Sale del mismo cálculo que /clima/ y /riesgos/api/clima/nivel (clima.niveles guarda el
resultado en clima.Estado «inundacion»), sin pasar por HTTP. Lo que se decide aquí es
solo cómo se dice:

- la hora es la del dato (la última medición de la zona), nunca la de la página;
- con más de 30 min, la fila va en gris y dice «hace X»;
- con más de 3 h, se quitan las cifras: «Las estaciones no han enviado datos desde las HH:MM»;
- una zona sin estaciones o callada dice «sin estaciones» o «sin datos», nunca «0 mm» ni «bajo»;
- si el nivel es alto o muy alto y casi no llueve ahora, una línea dice por qué sigue así,
  con la ventana que de verdad supera el umbral (por ejemplo, la lluvia de 3 días).

`filas()` es pura: recibe los datos ya leídos y la hora, para poder probarla sin base.
"""
from datetime import timedelta, timezone as dt_timezone

from reportes.templatetags.reportes_extras import hace

GALAPAGOS = dt_timezone(timedelta(hours=-6))
FRESCO_MIN = 30   # hasta aquí, el dato es de ahora
VIEJO_MIN = 180   # desde aquí, no se muestran cifras
CASI_SECO_MM = 1  # «casi no llueve ahora»: menos de 1 mm en la última hora

# Las zonas y los nombres cortos de /clima/ (clima/web/index.html, ZINFO), en el mismo orden.
ZONAS = [
    ("la-cascada", "La Cascada", "Puerto Ayora"),
    ("santa-cruz-alta", "Parte alta de Santa Cruz", ""),
    ("san-cristobal", "San Cristóbal", ""),
    ("isabela", "Isabela", "Puerto Villamil"),
]

# Barra de 4 tramos, con la escala de /clima/: «bajo» gris, «medio» rosa, «alto» rojo, «muy alto» granate. Sin verde.
TRAMOS = {"bajo": (1, "bajo"), "medio": (2, "medio"), "alto": (3, "alto"), "muy alto": (4, "muy-alto")}
VENTANA_TXT = {"R72h": "en 3 días", "R24h": "en 24 h", "R3h": "en las últimas 3 h", "R1h": "en la última hora"}


def mm(valor):
    """12 → «12 mm»; 0,3 → «0,3 mm». Coma decimal."""
    v = round(float(valor), 1)
    texto = f"{v:.0f}" if v == int(v) or v >= 10 else f"{v:.1f}".replace(".", ",")
    return f"{texto} mm"


def hora(fecha):
    return fecha.astimezone(GALAPAGOS).strftime("%H:%M")


def _regla():
    from clima import nivel

    return nivel.REGLA


def _ventana_que_dispara(zona, regla, umbrales_de):
    """La ventana de lluvia que supera hoy el umbral del nivel mostrado, o None (lo sostiene la persistencia)."""
    nv = next((n for n in regla["niveles"] if n["nivel"] == zona.get("nivel")), None)
    R = zona.get("R") or {}
    if not nv:
        return None
    factor = zona.get("factor") or 1.0
    umbrales = umbrales_de(zona.get("_regla") or {}, nv)
    # De la más larga a la más corta: la lluvia de varios días es la que explica un nivel alto sin lluvia ahora.
    for k in ("R72h", "R24h", "R3h", "R1h"):
        u = umbrales.get(k)
        if u is not None and R.get(k) is not None and R[k] >= u * (1.0 if k == "R72h" else factor):
            return k
    return None


def causa(zona, regla=None, umbrales_de=None):
    """La línea que explica un nivel alto o muy alto cuando casi no llueve ahora. None si no corresponde."""
    nivel = zona.get("nivel")
    R = zona.get("R") or {}
    if nivel not in ("alto", "muy alto") or zona.get("silencio") or R.get("R1h") is None or R["R1h"] >= CASI_SECO_MM:
        return None
    if zona.get("manual"):
        return f"Sigue {nivel} por los reportes de campo que recibió la coordinación."
    if regla is None or umbrales_de is None:
        from clima import nivel as calculo

        regla, umbrales_de = calculo.REGLA, calculo._umbrales
    k = _ventana_que_dispara(zona, regla, umbrales_de)
    if k == "R72h":
        return f"Sigue {nivel} por lo que llovió en 3 días ({mm(R['R72h'])}): el suelo está saturado."
    if k:
        return f"Sigue {nivel} por lo que llovió {VENTANA_TXT[k]} ({mm(R[k])})."
    horas = regla.get("persistencia_horas", 8)
    return f"Sigue {nivel} por la lluvia fuerte de las últimas horas: el nivel se mantiene {horas} h porque el agua tarda en bajar."


def filas(estado, generado, ultimas, ahora, regla=None, umbrales_de=None):
    """Las cuatro filas de «Ahora».

    estado: los datos de clima.Estado «inundacion» (o None si aún no hay cálculo).
    generado: cuándo se calculó. ultimas: {zona: última medición de sus estaciones (sin las dañadas)}.
    Devuelve {"filas": [...], "hora": «HH:MM» del dato más reciente o "", "vacio": bool}.
    """
    if regla is None or umbrales_de is None:
        from clima import nivel as calculo

        regla, umbrales_de = calculo.REGLA, calculo._umbrales
    if not estado or not estado.get("zonas"):
        return {"filas": [], "hora": "", "vacio": True}
    por_id = {z["id"]: z for z in estado["zonas"]}
    regla_por_id = {z["id"]: z for z in regla["zonas"]}
    salida, horas = [], []
    for zid, nombre, lugar in ZONAS:
        z = dict(por_id.get(zid) or {"id": zid, "nivel": "sin datos"})
        z["_regla"] = regla_por_id.get(zid) or {}
        fila = {"id": zid, "nombre": nombre, "lugar": lugar, "nivel": "", "tramos": 0, "tono": "", "cifras": "", "causa": None,
                "texto": "", "hora": "", "hace": "", "estado": ""}
        estaciones = z["_regla"].get("estaciones")
        if not estaciones:
            fila.update(estado="sin-estaciones", nivel="sin estaciones",
                        texto="No hay pluviómetros en vivo.")
            salida.append(fila)
            continue
        ultima = ultimas.get(zid)
        dato = min(x for x in (ultima, generado) if x) if (ultima and generado) else None
        if dato:
            fila["hora"] = hora(dato)
            fila["hace"] = hace(dato, ahora)
        edad = (ahora - dato).total_seconds() / 60 if dato else None
        if z.get("silencio"):
            fila.update(estado="silencio", nivel="sin datos en lluvia fuerte", tramos=4, tono="muy-alto",
                        texto="Las estaciones dejaron de enviar datos durante una lluvia fuerte. Tómalo como un nivel muy alto.")
        elif z.get("nivel") in TRAMOS and not z.get("R"):
            # Sin estaciones válidas ahora, pero con nivel: lo subió la coordinación o lo sostienen las 8 h
            # de persistencia. Se muestra como en /clima/, sin cifras.
            tramos, tono = TRAMOS[z["nivel"]]
            horas_p = regla.get("persistencia_horas", 8)
            fila.update(estado="sostenido", nivel=z["nivel"], tramos=tramos, tono=tono,
                        causa="Lo subió la coordinación por reportes de campo." if z.get("manual")
                        else f"Sigue {z['nivel']}: el nivel se mantiene {horas_p} h después de la lluvia fuerte y ahora las estaciones no tienen datos válidos.")
        elif dato is None or z.get("nivel") in (None, "", "sin datos") or not z.get("R"):
            fila.update(estado="sin-datos", nivel="sin datos",
                        texto=(f"Las estaciones no han enviado datos desde las {fila['hora']}." if dato else "Las estaciones de la zona no responden.")
                        + " «Sin datos» no quiere decir que no llueva.")
        elif edad > VIEJO_MIN:
            fila.update(estado="mudo", nivel="sin datos", texto=f"Las estaciones no han enviado datos desde las {fila['hora']}")
        else:
            tramos, tono = TRAMOS.get(z["nivel"], (0, ""))
            R = z["R"]
            partes = []
            if R.get("R1h") is not None:
                partes.append(f"{mm(R['R1h'])} en la última hora")
            if R.get("R24h") is not None:
                partes.append(f"{mm(R['R24h'])} en 24 h")
            fila.update(estado="viejo" if edad > FRESCO_MIN else "vivo", nivel=z["nivel"], tramos=tramos, tono=tono,
                        cifras=" · ".join(partes), causa=causa(z, regla, umbrales_de))
            horas.append(dato)
        salida.append(fila)
    return {"filas": salida, "hora": hora(max(horas)) if horas else "", "vacio": False}


def leer(ahora):
    """Lee el nivel guardado y la última medición de cada zona, y arma las filas."""
    from clima.models import EstacionDanada, Estado, Estacion

    e = Estado.objects.filter(clave="inundacion").first()
    regla = _regla()
    claves = {c for z in regla["zonas"] for c, _ in z["estaciones"]}
    danadas = set(
        EstacionDanada.objects.filter(variable="lluvia_mm", desde__lte=ahora).exclude(hasta__lte=ahora)
        .values_list("estacion__fuente", "estacion__codigo")
    )
    ultima_por_clave = {}
    for est in Estacion.objects.filter(ultima__isnull=False).only("fuente", "codigo", "ultima"):
        if est.clave in claves and (est.fuente, est.codigo) not in danadas:
            ultima_por_clave[est.clave] = est.ultima
    ultimas = {}
    for z in regla["zonas"]:
        ts = [ultima_por_clave[c] for c, _ in z["estaciones"] if c in ultima_por_clave]
        ultimas[z["id"]] = max(ts) if ts else None
    return filas(e.datos if e else None, e.generado if e else None, ultimas, ahora)


def peligros_recientes(ahora, horas=48):
    """Peligros graves vistos en las últimas 48 h, por zona. Sin texto libre de vecinos: solo cuántos y dónde.

    Cuenta los de clase «riesgo» con gravedad «no pasar» o «peligro de vida». El historial de la
    coordinación anterior (fuente «anterior») nunca cuenta; los fusionados, tampoco (ya cuenta el otro).
    """
    from reportes.models import Clase, Gravedad, Reporte

    qs = (Reporte.objects.del_mapa()
          .filter(tipo__clase=Clase.RIESGO, gravedad__in=[Gravedad.NO_PASAR, Gravedad.PELIGRO_VIDA],
                  visto_en__gte=ahora - timedelta(hours=horas), visto_en__lte=ahora, fusionado_en__isnull=True)
          .select_related("zona"))
    total, zonas, sin_zona = 0, [], 0
    for r in qs.order_by("-visto_en"):
        total += 1
        if r.zona_id is None:
            sin_zona += 1
        elif r.zona.nombre not in zonas:
            zonas.append(r.zona.nombre)
    return {"total": total, "zonas": zonas[:5], "mas_zonas": len(zonas) > 5 or (sin_zona > 0 and bool(zonas))}


# Cómo se nombra cada clase en la portada (plural, singular).
CLASES_PORTADA = [("riesgo", "peligros", "peligro"), ("observa", "observaciones", "observación"),
                  ("ayuda", "puntos de ayuda", "punto de ayuda"), ("bueno", "cosas buenas", "cosa buena")]


def puntos_activos(ahora):
    """Todos los puntos que se ven ahora en el mapa, por clase y por zona. Sin texto libre de vecinos.

    Cuenta lo vivo (no cerrado, sin vencer). El historial de la coordinación anterior y los fusionados no cuentan.
    """
    from reportes.models import Reporte

    qs = (Reporte.objects.del_mapa().vivos(ahora).filter(fusionado_en__isnull=True)
          .select_related("tipo", "zona").order_by("-visto_en"))
    por_clase, zonas, sin_zona, total = {}, [], 0, 0
    for r in qs:
        total += 1
        por_clase[r.tipo.clase] = por_clase.get(r.tipo.clase, 0) + 1
        if r.zona_id is None:
            sin_zona += 1
        elif r.zona.nombre not in zonas:
            zonas.append(r.zona.nombre)
    clases = [f"{por_clase[c]} {plural if por_clase[c] != 1 else singular}"
              for c, plural, singular in CLASES_PORTADA if por_clase.get(c)]
    return {"total": total, "clases": clases, "zonas": zonas[:6], "mas_zonas": len(zonas) > 6 or (sin_zona > 0 and bool(zonas))}

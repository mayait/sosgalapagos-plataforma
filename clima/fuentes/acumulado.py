"""Lluvia por diferencia del acumulado, para las estaciones que solo dan el total del día.

WeatherLink y Weather Underground dan el acumulado del día; la lluvia de cada lectura es la
diferencia con la lectura ANTERIOR (sea del día que sea): el contador de algunas estaciones
no se reinicia a medianoche de Galápagos (Casa Marina lo hacía a otras horas y se contaba
dos veces). Si el acumulado vuelve a ~0 (≤ 1 mm), el contador se reinició: cuenta solo lo
nuevo. Si baja sin llegar a 0 (Casa Marina descuenta la lluvia vieja a lo largo del día), no
cuenta nada. Tras un hueco de más de HUECO_MAX_MIN no se atribuye nada a esa lectura.
"""
from . import base

HUECO_MAX_MIN = 60
MAX_MM_H = 100  # un incremento por encima de esta intensidad se descarta
MAX_EDAD_S = 3 * 86400  # una estación que no transmite hace más de 3 días no se registra


def lluvia_por_diferencia(t, acumulado, anterior):
    """anterior: (hora, acumulado) de la lectura previa, o None. Devuelve mm, o None si no se puede saber."""
    if anterior is None or acumulado is None or anterior[1] is None:
        return None
    minutos = (t - anterior[0]).total_seconds() / 60
    if minutos <= 0 or minutos > HUECO_MAX_MIN:
        return None
    if acumulado >= anterior[1]:
        incremento = acumulado - anterior[1]
    elif acumulado <= 1.0:
        incremento = acumulado  # el contador se reinició entre las dos lecturas
    else:
        incremento = 0.0  # baja sin llegar a 0: redondeo, o un total que va descontando lluvia vieja
    if incremento > max(10, MAX_MM_H * minutos / 60):
        return None  # salto imposible
    return round(incremento, 2)


def anterior(fuente, codigo, antes_de):
    filas = base.serie(fuente, codigo, "lluvia_dia_acum_mm", antes_de=antes_de, orden="DESC", limite=1)
    return filas[0] if filas else None


def recalcular(clave, desde):
    """Rehace lluvia_mm de una estación a partir de su acumulado guardado. Devuelve cuántas filas escribió."""
    fuente, codigo = clave.split("/", 1)
    lecturas = base.serie(fuente, codigo, "lluvia_dia_acum_mm", desde=desde)
    base.borrar(fuente, codigo, "lluvia_mm", desde=desde, de_respaldo=False)
    previa, nuevas = (anterior(fuente, codigo, lecturas[0][0]) if lecturas else None), []
    for t, valor in lecturas:
        mm = lluvia_por_diferencia(t, valor, previa)
        if mm is not None:
            nuevas.append((codigo, "lluvia_mm", t, mm))
        previa = (t, valor)
    return base.guardar(fuente, nuevas)

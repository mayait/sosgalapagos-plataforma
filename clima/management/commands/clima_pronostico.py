"""Guarda en la base lo que dijeron los modelos y lo que se publicó, y lo verifica.

  manage.py clima_pronostico              lee lo nuevo (corre solo cada hora)
  manage.py clima_pronostico --verificar  muestra el acierto de los últimos 45 días
"""
from django.core.management.base import BaseCommand

from clima import pronostico


class Command(BaseCommand):
    help = "Guarda y verifica el pronóstico de lluvia"

    def add_arguments(self, parser):
        parser.add_argument("--verificar", action="store_true")
        parser.add_argument("--dias", type=int, default=45)
        parser.add_argument("--recalibrar", action="store_true", help="ajusta y valida la curva propia con lo medido")

    def handle(self, verificar, dias, recalibrar=False, **opciones):
        if recalibrar:
            for r in pronostico.recalibrar():
                self.stdout.write(f"{r['grupo']:6} plazo {r['plazo']} · {r['dias']} días ({r['eventos']} de lluvia fuerte) · a={r['a']} b={r['b']} · brier {r['brier']} frente a {r['brier_base']} · habilidad {r['habilidad']}")
            return
        if not verificar:
            leidos, nuevas = pronostico.guardar_archivo()
            self.stdout.write(f"archivos leídos {leidos} · filas nuevas de modelos {nuevas} · publicados nuevos {pronostico.guardar_emitido()}")
            return
        v = pronostico.verificar(dias)
        self.stdout.write(f"{v['desde']} a {v['hasta']}: {v['dias_observados']} días-punto observados, {v['dias_de_lluvia_fuerte']} con {v['umbral_mm']} mm o más")
        self.stdout.write("modelo                            ant  días  error  sesgo  fuertes avisados falsas  brier")
        for m in v["por_modelo"]:
            self.stdout.write(f"{m['modelo'][:33]:33} {m['anticipacion']:>3} {m['dias']:>5} {m['error_medio_mm']:>6} {m['sesgo_mm']:>6} {m['dias_de_lluvia_fuerte']:>8} {m['avisados']:>8} {m['falsas_alarmas']:>6}  {m['brier'] if m['brier'] is not None else ''}")
        for p in v["publicado"]:
            self.stdout.write(f"publicado {p['punto']:18} ant {p['anticipacion']} · {p['dias']} días · brier {p['brier']} · habilidad {p['habilidad']}")

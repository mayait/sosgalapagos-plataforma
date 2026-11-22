# Clima en el mismo stack: plan de migración a Django

*22-nov-2026. Pedido de Julián: todo el backend en Python con Django detrás, guardar más datos, mejores métricas, correr modelos, extraer los boletines del INAMHI y del INOCAR, mejores datos de mareas y mejorar el pronóstico.*

## 1. De dónde se parte

El clima actual (`sosgalapagos-datos/clima/`) es Python sin framework: 4 200 líneas en vivo, tres timers de systemd y una base SQLite.

| Qué | Cuánto |
|---|---|
| Mediciones guardadas | 2,5 millones, de 22 estaciones y 10 fuentes |
| Fuentes | IERSE (entra por un puente desde una Mac en Ecuador), USFQ GSC, INAMHI, IOC, METAR, WeatherLink, Tempest, Ambient, Weather Underground, Open-Meteo y GOES-19 |
| Costo de cada corrida | **≈ 2,5 minutos de CPU y ≈ 300 MB**, cada 5 minutos: medio núcleo ocupado siempre |
| Por qué cuesta tanto | Cada corrida rehace desde cero todas las exportaciones: la historia horaria completa, el nivel de lluvia de 80 horas por zona y la estacionalidad |

Lo que funciona y no se toca hasta tener reemplazo probado: la regla del nivel de lluvia peligrosa, el pronóstico calibrado, el satélite y las mareas.

## 2. Adónde se llega

Una sola aplicación Django (`sosgalapagos-plataforma`) con una app `clima`:

- **Datos en PostgreSQL**, junto a los reportes: mediciones, resúmenes por hora, corridas, pronósticos guardados, boletines y mareas.
- **Recolectores como tareas de Django**, una por fuente, con su registro de salud.
- **Cálculo incremental**: solo se recalcula lo que cambió. Es de donde sale el ahorro de CPU.
- **API propia** (`/riesgos/api/clima/…`) y el panel servido desde Django, con la identidad del mapa.
- **Lo nuevo**: boletines oficiales extraídos con el modelo de lenguaje, mareas de más puertos, y verificación continua del pronóstico.

## 3. Etapas

Cada etapa deja el clima funcionando. El recolector anterior no se apaga hasta la etapa 5.

| Etapa | Qué | Cómo se sabe que está bien | Estado |
|---|---|---|---|
| **1. Datos en Django** | App `clima`, copia de la base del recolector a PostgreSQL cada 5 min, resúmenes por hora, API de estaciones, series y salud | Mismas filas por fuente en los dos lados; la copia tarda segundos | **Hecha el 22-nov** |
| **2. Lo nuevo, nativo** | Guardar cada pronóstico y verificarlo contra lo medido (**hecho**); recalibración propia (**hecha**, en evaluación); boletines del INAMHI y del INOCAR y mareas (en curso) | Cada boletín nuevo aparece sin intervención; el error del pronóstico se mide solo | En curso |
| **3. Cálculos en Django** | Nivel de lluvia peligrosa, mareas y estacionalidad calculados desde PostgreSQL, de forma incremental | Durante 7 días dan lo mismo que el recolector anterior, hora a hora | Pendiente |
| **4. Panel desde Django** | `/clima/` lo sirve la plataforma, leyendo la API | Mismo contenido, misma dirección | Pendiente |
| **5. Recolectores en Django** | Cada fuente pasa a ser una tarea; se portan de una en una, empezando por las estables (IOC, METAR, INAMHI, Open-Meteo) y dejando para el final las frágiles (GSC, Weather Underground) | Cada fuente corre en paralelo 3 días y trae las mismas filas | Pendiente |
| **6. Apagar lo anterior** | Se detienen los timers de systemd (no se borran) y la base SQLite queda como archivo | 14 días sin usar el recolector anterior | Pendiente |

**Por qué en este orden.** Portar primero los recolectores sería lo más arriesgado en plena emergencia: varias fuentes son frágiles (una se lee simulando un navegador, otra raspando una página) y un fallo dejaría sin datos la alerta. Copiando la base se tiene todo en Django desde el primer día, sin tocar lo que recoge los datos.

## 3b. Pronóstico: lo que se encontró y lo que se hizo (22-nov-2026)

Antes no se podía saber si el pronóstico acertaba: las respuestas de los modelos iban a archivos comprimidos y lo publicado no se guardaba. Ahora todo queda en la base (`PronosticoModelo`, `PronosticoEmitido`) y se compara solo con la lluvia medida.

**Lo que salió al verificar del 3 al 21 de noviembre** (95 días-punto con estación, 46 de ellos con 20 mm o más):

- **Todos los modelos globales se quedan cortos por 35–45 mm al día.** No ven la montaña de una isla pequeña.
- El que mejor avisó fue el IFS de 9 km del ECMWF (10 a 14 de 45 días de lluvia fuerte, según el plazo), seguido del GEM. El resto avisó entre 0 y 9.
- **Los conjuntos, tomados tal cual, casi nunca dieron 20 mm**: su probabilidad cruda no sirve sin calibrar.
- La estación M0191 del INAMHI marcó 0 mm el 21-nov, cuando las vecinas midieron más de 200: un hueco que parece un día seco.

**Lo que se construyó:** una recalibración propia (`clima/pronostico.py`, `recalibrar`). Aprende, con los pares guardados, qué probabilidad de lluvia fuerte corresponde a los milímetros que dan los modelos. Es una regresión logística de dos parámetros por grupo (parte alta, costa) y plazo, y solo se usa si su validación —dejando fuera un día entero cada vez— supera a decir siempre la frecuencia observada.

| Grupo | Plazo | Brier | Brier de referencia | Habilidad |
|---|---|---|---|---|
| Parte alta | 0–1 días | 0,13 | 0,26 | 0,51 |
| Parte alta | 2–3 días | 0,16 | 0,25 | 0,38 |
| Parte alta | 4–5 días | 0,19 | 0,21 | 0,08 |
| Costa | 0–1 días | 0,15 | 0,25 | 0,40 |
| Costa | 2–3 días | 0,19 | 0,26 | 0,28 |
| Costa | 4–5 días | 0,23 | 0,28 | 0,19 |

**Lo que no hay que olvidar:**

- Está ajustada con **tres semanas de un evento extremo**. En esas semanas llovió fuerte más de la mitad de los días, así que hoy da probabilidades altas. Cuando el tiempo cambie tardará en bajar: se recalcula cada día, pero con una ventana de 60 días.
- **No reemplaza al pronóstico del panel**, que está calibrado con dos años. `/riesgos/api/clima/pronostico` muestra los dos juntos. La decisión de cuál publicar se toma cuando haya varias semanas de los dos verificados lado a lado (`/riesgos/api/clima/pronostico/verificacion`).
- No se pudo comparar hacia atrás con lo publicado, porque antes no se guardaba.

## 4. Lo que se gana con Django detrás

- **CPU**: de ≈ 2,5 min por corrida a segundos, cuando los cálculos pasen a ser incrementales (etapa 3).
- **Más datos**: PostgreSQL guarda sin problema toda la serie de 5 minutos, los pronósticos de cada corrida (hoy van a archivos comprimidos que nadie consulta) y los boletines.
- **Mejores métricas**: salud de cada fuente (aciertos, tiempos, minutos sin éxito), retraso de los datos y, con los pronósticos guardados, su error real por modelo y plazo.
- **Un solo lugar** para editar umbrales, estaciones dañadas y niveles puestos a mano: hoy son archivos JSON que se editan en git y se despliegan; pasan al admin.
- **Un respaldo**, una base, un despliegue.

## 5. Riesgos y cosas que hay que decidir

- **Licencias sin resolver** (vienen de antes; no las crea esta migración):
  - IERSE es CC BY-NC-ND (sin obras derivadas), y hoy se publican agregados y sus crudos.
  - USFQ GSC no publica licencia, y sus crudos están en las descargas públicas desde el 12-nov.
  - Las series de la FCD (CC BY-NC-SA) se tratan como privadas, pero están en el repositorio público.
- **La predicción de mareas se acaba el 30-dic-2027** y hoy no avisa. Se añade un aviso (etapa 2).
- **IERSE depende de una Mac encendida en Ecuador.** No cambia con la migración.
- **Los endpoints de las fuentes siguen siendo privados**: van en variables de entorno, nunca en este repositorio.
- **Tres husos horarios mezclados** en las fuentes (UTC−6, UTC−5 y UTC). Al portar cada recolector se conserva su conversión exacta.

## 6. Cómo se usa la etapa 1

```bash
manage.py clima_sincronizar --completa   # toda la historia (la primera vez)
manage.py clima_sincronizar              # los últimos 3 días (corre solo cada 5 min)
manage.py clima_sincronizar --comparar   # cuenta filas en los dos lados, por fuente
```

- `/riesgos/api/clima/estaciones` · `/riesgos/api/clima/serie?estacion=…&variable=lluvia_mm&paso=hora|dia` · `/riesgos/api/clima/salud`
- `/riesgos/api/clima/pronostico` (publicado, recalibrado y modelos) · `/riesgos/api/clima/pronostico/verificacion`
- `manage.py clima_pronostico [--verificar | --recalibrar]`
- En el admin: estaciones, corridas, sincronizaciones y calibraciones (solo lectura), y **sensores dañados** (editable: reemplaza a `estaciones_danadas.json`).

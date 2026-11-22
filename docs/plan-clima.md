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
| **2. Lo nuevo, nativo** | Boletines del INAMHI y del INOCAR; mareas; guardar cada pronóstico y verificarlo contra lo medido | Cada boletín nuevo aparece sin intervención; el error del pronóstico se mide solo | En curso |
| **3. Cálculos en Django** | Nivel de lluvia peligrosa, mareas y estacionalidad calculados desde PostgreSQL, de forma incremental | Durante 7 días dan lo mismo que el recolector anterior, hora a hora | Pendiente |
| **4. Panel desde Django** | `/clima/` lo sirve la plataforma, leyendo la API | Mismo contenido, misma dirección | Pendiente |
| **5. Recolectores en Django** | Cada fuente pasa a ser una tarea; se portan de una en una, empezando por las estables (IOC, METAR, INAMHI, Open-Meteo) y dejando para el final las frágiles (GSC, Weather Underground) | Cada fuente corre en paralelo 3 días y trae las mismas filas | Pendiente |
| **6. Apagar lo anterior** | Se detienen los timers de systemd (no se borran) y la base SQLite queda como archivo | 14 días sin usar el recolector anterior | Pendiente |

**Por qué en este orden.** Portar primero los recolectores sería lo más arriesgado en plena emergencia: varias fuentes son frágiles (una se lee simulando un navegador, otra raspando una página) y un fallo dejaría sin datos la alerta. Copiando la base se tiene todo en Django desde el primer día, sin tocar lo que recoge los datos.

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
- En el admin: estaciones, corridas y sincronizaciones (solo lectura).

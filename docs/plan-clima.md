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
| **2. Lo nuevo, nativo** | Guardar y verificar cada pronóstico; recalibración propia (en evaluación); boletines del INAMHI y del INOCAR; mareas y oleaje; alertas por tema | Cada boletín nuevo aparece sin intervención; el error del pronóstico se mide solo | **Hecha el 22-nov** |
| **3. Cálculos en Django** | Nivel de lluvia peligrosa, mareas y estacionalidad desde PostgreSQL | Dan lo mismo que el recolector anterior | **Hecha el 22-nov.** Comparado valor por valor antes del relevo |
| **4. Panel desde Django** | Los datos que lee `/clima/` los genera la plataforma | Mismo contenido, misma dirección | **Hecha el 22-nov.** `horario.json` y `diario.json`: cero diferencias en 238 000 valores |
| **5. Recolectores en Django** | Cada fuente la recoge una tarea de esta aplicación | Traen las mismas filas | **Hecha el 22-nov** para 10 de 12. Faltan IERSE (entra por un puente) y el satélite (colector aparte) |
| **6. Apagar lo anterior** | Se detienen los timers de systemd (no se borran) | — | **Hecha el 22-nov** para el recolector principal y el de las descargas |

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

## 3c. Mar, boletines oficiales y alertas (22-nov-2026)

**Fuentes que se probaron y qué se hizo con cada una**

| Fuente | Qué da | Decisión |
|---|---|---|
| **INOCAR, tabla de mareas** | Pleamares y bajamares oficiales de Baltra, Santa Cruz, San Cristóbal e Isabela, hasta el 31-dic-2026 | **Se usa.** Es la referencia: antes San Cristóbal e Isabela solo tenían un modelo global |
| **Stormglass** (2 llaves, 10 llamadas al día cada una) | Mareas desde una estación a 1 km de Puerto Baquerizo; oleaje, mar de fondo, viento, nivel del mar y temperatura del agua, hora a hora | **Se usa**, dos veces al día: 6 llamadas por pasada. El gasto se cuenta y nunca se pasa de 9 por llave |
| **INAMHI, pronóstico por isla** | Condición por tramos del día y lluvia esperada hora a hora para las tres islas | **Se usa**, cada hora |
| **INAMHI, advertencia** | Un PDF en imagen, sin texto, que se sobrescribe | **Se usa**: se detecta por la huella del archivo y lo lee el modelo de lenguaje |
| **INOCAR, boletín de oleaje** | Una imagen cada 3–4 días | **Se usa**, igual |
| **ERFEN (El Niño)** | PDF quincenal | **Se usa**, igual |
| **Windy Point Forecast** (gratis) | GFS e ICON por punto | **No se usa.** La respuesta avisa: «This data is randomly shuffled and slightly modified». Son datos alterados a propósito, y además esos modelos ya se tienen |
| **Windy Map Forecast** | Mapa animado para incrustar | **Prototipo** en `/riesgos/mapa-del-tiempo/`. La llave está limitada por dominio: hay que autorizar `sosgalapagos.org` en la consola de Windy |
| **Windy Plugins** | Para publicar complementos dentro de Windy | No aplica |

**Lectura de boletines con el modelo de lenguaje.** En la primera corrida leyó bien los tres documentos reales (número, vigencia, nivel para Galápagos, altura de ola y período). Aun así es un resumen automático: en el admin una persona puede corregirlo y marcarlo como revisado, y siempre se muestra el enlace al documento oficial. La página del INAMHI iba atrasada ese día (tenía la advertencia n.º 88 cuando ya circulaba la 89 por redes).

**Alertas por tema.** Cada persona elige en «Mis avisos» de qué quiere enterarse y de qué islas:

| Tema | Cuándo sale | De dónde |
|---|---|---|
| Peligros confirmados | Coordinación confirma un peligro | El mapa |
| Lluvia peligrosa ahora | El nivel de la isla sube a «alto» o «muy alto» (una vez cada 8 h por zona y nivel) | Lo medido |
| Lluvia fuerte mañana | Por la tarde, si el pronóstico da señal alta para el día siguiente | Pronóstico |
| Mar | Olas de 2,5 m o más en las próximas 36 h, o boletín de oleaje del INOCAR | Stormglass e INOCAR |
| Oficiales | Advertencia o boletín nuevo que nombra a Galápagos | INAMHI e INOCAR |

Por defecto se encienden peligros, lluvia y oficiales. Cada aviso lleva una clave y no se repite. Los umbrales (2,5 m de ola, 8 horas) son preliminares.

**Lo que falta de esta parte:** avisar de pleamares muy altas (hace falta un umbral por puerto), usar el residuo del nivel del mar (con El Niño el mar está unos 50 cm más alto que la tabla), meter el pronóstico por horas del INAMHI en el nivel de lluvia, y que la tabla del INOCAR de 2027 exista (sale en diciembre).

## 3d. Etapas 3 y 5: cómo se hace el relevo (22-nov-2026)

**Nivel de lluvia peligrosa (etapa 3).** `clima/nivel.py` es la regla v0.2 del recolector copiada sin cambiar la lógica; solo cambia de dónde lee. Corre después de cada copia, para el mismo instante que el recolector anterior, y guarda en `NivelZona` el nivel de cada zona junto al del anterior y si coinciden.

- Primera pasada: las 4 zonas iguales. Tarda **0,44 s**; la exportación del recolector anterior, donde va este cálculo, gasta unos 2,5 min de CPU.
- La coincidencia acumulada está en `/riesgos/api/clima/nivel` y en `/riesgos/api/clima/salud`.
- **Cuándo se cambia:** con 7 días de comparación y más del 99 % de coincidencia, el panel, la franja del mapa y los avisos pasan a leer el nivel de Django. Hasta entonces mandan los del recolector anterior.
- Los niveles puestos a mano y los sensores dañados ya son registros del admin. **Mientras convivan los dos, hay que ponerlos en los dos sitios** (el admin y los archivos JSON del repo de datos), o dejarán de coincidir.

**Recolectores nativos (etapa 5).** Cada fuente de `CLIMA_FUENTES_NATIVAS` la recoge `clima/fuentes.py` y deja de copiarse de la base anterior. El recolector anterior la sigue recogiendo por su lado, así que `manage.py clima_sincronizar --comparar` muestra las dos cuentas una junto a la otra.

Orden previsto, de la más estable a la más frágil: METAR (hecha), IOC, INAMHI, Open-Meteo (mar y pronóstico), Tempest, Ambient, WeatherLink, GOES, Weather Underground y GSC. IERSE entra por el puente desde una Mac en Ecuador: su relevo es cambiar a dónde envía el puente.

**Lo que la plataforma ya no lee de archivos:** la lluvia de la línea del tiempo sale de esta base.

## 3e. El relevo (22-nov-2026)

Julián pidió seguir con todo el plan aprovechando un día de sol. Se hizo así:

**Cómo.** En vez de reescribir a mano los recolectores (4 200 líneas con conversiones de unidades y de horas ya probadas), corren **tal cual** dentro de Django (`clima/anterior/`), escribiendo en PostgreSQL por una conexión de compatibilidad (`clima/compat.py`): tres vistas con la forma de las tablas de SQLite. Lo que sí es nuevo y nativo es todo lo caro: los resúmenes por hora, el nivel de lluvia y la generación de los datos del panel (`clima/panel.py`).

**Validación antes de cambiar** (`manage.py clima_panel --comparar`):

| Archivo del panel | Valores comparados | Distintos |
|---|---|---|
| `horario.json` | 199 019 | 0 |
| `diario.json` (con la estacionalidad) | 39 394 | 0 |
| `estado.json` | 4 638 | Solo los que dependen de la hora (se generó 8 min después) y un reporte de campo que venció a las 12:30 |

**Costo.** Generar los tres archivos: **1,2 s** en Django. El recolector anterior gastaba unos 2,5 min de CPU por corrida, cada 5 minutos.

**Qué quedó corriendo dónde:**

| Qué | Dónde |
|---|---|
| GSC, INAMHI, IOC, METAR, WeatherLink, Tempest, Ambient, Weather Underground, mar y pronóstico | Django, cada 5 min |
| Nivel de lluvia peligrosa, mareas, estacionalidad, datos del panel | Django |
| Descargas públicas y copia privada para investigadores | Django, cada hora |
| IERSE | Sigue entrando por el puente a la base SQLite; Django la copia cada 5 min |
| Satélite GOES-19 | Su colector y su timer, sin cambios; Django copia sus mediciones |
| Niveles puestos a mano y sensores dañados | Solo en el admin de la plataforma |

**Dos cosas que aparecieron al mover las fuentes:**
- METAR «fallaba» un tercio de las veces: de noche la fuente responde «204, sin contenido» y el recolector lo contaba como error. Ya no.
- Weather Underground rechazaba (403) las peticiones desde el contenedor: no le gusta la lista de cifrados TLS del Python de la imagen. Con la de OpenSSL por defecto responde.

**Cómo volver atrás** (minutos, sin perder datos):

```bash
# en el servidor
cd /opt/sosgalapagos-plataforma/despliegue/produccion
sed -i 's/^CLIMA_PUBLICAR_PANEL=.*/CLIMA_PUBLICAR_PANEL=0/; s/^CLIMA_FUENTES_NATIVAS=.*/CLIMA_FUENTES_NATIVAS=/' .env && docker compose up -d
cp /root/respaldo-clima-relevo/recolector.py /root/respaldo-clima-relevo/recibir.sh /opt/sosgalapagos-clima/
systemctl enable --now sosgalapagos-clima.timer sosgalapagos-clima-csv.timer
```

La base SQLite sigue en su sitio, pero **desde el relevo solo recibe IERSE y el satélite**: si se vuelve atrás, el recolector anterior rellena por sí solo los últimos 3 días de las demás fuentes.

**Lo que falta para terminar del todo:**
- IERSE directo a PostgreSQL: cambiar a dónde envía el puente de la Mac en Ecuador.
- El satélite dentro de la plataforma: necesita `numpy` y `h5py` en la imagen.
- Sacar cada fuente de `clima/anterior/` a un módulo propio, sin la capa de compatibilidad, cuando haya que tocarla.
- Guardar el pronóstico y el mar del modelo en tablas, no en archivos sueltos.
- Vigilar unos días que ninguna fuente se degrade (`/riesgos/api/clima/salud`).

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

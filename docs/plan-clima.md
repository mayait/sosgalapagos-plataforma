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
| **5. Recolectores en Django** | Cada fuente la recoge un módulo de esta aplicación (`clima/fuentes/`) | Traen las mismas filas | **Hecha el 22-nov**: las 12, nativas. IERSE entra por un relevo mínimo; el satélite corre en su propio servicio |
| **6. Apagar lo anterior** | Se detienen los timers de systemd y se deja de usar SQLite (nada se borra) | No queda nada fuera de esta aplicación | **Hecha el 22-nov** |

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
| **Windy Map Forecast** | Mapa animado para incrustar | **No se usa.** La llave gratis es «Development purpose only, not intended for production», solo trae GFS y no tiene capa de lluvia; la de pago cuesta 990 €/año y su ECMWF es «for internal use only». En su lugar, `/riesgos/mapa-del-tiempo/` y `/clima/` muestran un mapa propio de lluvia y viento con Open-Meteo (`clima/lluvia_mapa.py`) |
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

## 3d. Un solo stack (22-nov-2026)

Julián pidió cerrar la migración sin dejar deuda: todo en Python dentro de esta aplicación, escribiendo en PostgreSQL, sin SQLite y sin correr el recolector anterior «tal cual». Quedó así:

| Qué | Dónde | Antes |
|---|---|---|
| Cada fuente de mediciones | `clima/fuentes/<fuente>.py`, con `recoger()`; lo común en `base.py` | 1 400 líneas en dos archivos escritos para SQLite, detrás de una capa de compatibilidad |
| IERSE | `clima/fuentes/ierse.py` + `clima/relevo.py`. Una máquina en Ecuador corre `despliegue/relevo/relevo.py` (90 líneas, sin dependencias), que pide lo que la plataforma le indica y devuelve las respuestas tal cual | Un «puente» con su propio recolector, su base SQLite y SSH al servidor |
| Satélite GOES-19 | `clima/satelite/`, servicio `satelite` del Compose; guarda en PostgreSQL y deja el resumen en `Estado` | Programa aparte con su entorno, su timer y archivos de estado |
| Corridas de los modelos de pronóstico | Tabla `PronosticoCorrida` (queda la historia) | Archivos JSON en una carpeta |
| Modelo del mar (Open-Meteo) | Tabla `MarHora`, junto a Stormglass, con la fuente de cada fila | Un archivo `mar_modelo.json` |
| Señal del pronóstico, mareas, estacionalidad, descargas | `clima/senal.py`, `mareas.py`, `estacionalidad.py`, `descargas.py` | Módulos del recolector anterior |
| Series históricas de la FCD | En la base (fuente `fcd`), cargadas con `manage.py clima_importar fcd` | Archivos CSV en una carpeta del servidor |
| Nivel de lluvia para el mapa | Se lee de la tabla `Estado` | Se leía de `estado.json` |

**Lo que se retiró** (movido a `Archivo/clima-recolector-anterior/`, sin uso): el recolector anterior, la capa de compatibilidad (`compat.py` y las vistas de la migración 0007) y la copia desde SQLite. La tabla del registro de copias se conserva como `archivo_clima_sincronizacion`.

**En el servidor quedan sin uso, sin borrar:** la base `/var/lib/sosgalapagos-clima/clima.db`, `/opt/sosgalapagos-clima/` y los timers `sosgalapagos-clima*.timer` (detenidos y deshabilitados).

**Por qué IERSE necesita un relevo.** Su servidor solo responde a conexiones desde Ecuador; desde el de sosgalapagos.org la conexión se agota (comprobado otra vez el 22-nov). Se deja de depender de una máquina cuando IERSE autorice la IP del servidor (`CLIMA_IERSE_DIRECTO=1`) o cuando el relevo corra en una máquina siempre encendida en Ecuador. Detalle en `despliegue/relevo/LEEME.md`.

**La copia privada en CSV se dejó de generar.** Todo está en PostgreSQL, con respaldo diario; quien necesite los datos completos los saca de ahí o de la API.

**Dos cosas que aparecieron al mover las fuentes** (siguen valiendo):
- Los aeropuertos responden «204, sin contenido» de noche: no es un fallo.
- Weather Underground rechaza (403) la lista de cifrados TLS del Python de la imagen; con la de OpenSSL por defecto responde.

**Si algo sale mal.** No hay vuelta al recolector anterior: su base dejó de recibir datos. Se vuelve a la versión anterior de esta aplicación (`git checkout` de la etiqueta previa y `desplegar.sh`); las tablas nuevas no estorban, y lo recogido mientras tanto se recupera solo (las fuentes rellenan 3 días; IERSE, 10).

## 4. Lo que se gana con Django detrás

- **CPU**: de ≈ 2,5 min por corrida a segundos, cuando los cálculos pasen a ser incrementales (etapa 3).
- **Más datos**: PostgreSQL guarda sin problema toda la serie de 5 minutos, los pronósticos de cada corrida (hoy van a archivos comprimidos que nadie consulta) y los boletines.
- **Mejores métricas**: salud de cada fuente (aciertos, tiempos, minutos sin éxito), retraso de los datos y, con los pronósticos guardados, su error real por modelo y plazo.
- **Un solo lugar** para editar umbrales, estaciones dañadas y niveles puestos a mano: hoy son archivos JSON que se editan en git y se despliegan; pasan al admin.
- **Un respaldo**, una base, un despliegue.

## 5. Riesgos y cosas que hay que decidir

- **Licencias de los datos: resuelto el 22-nov-2026.** Julián confirmó que hay permiso de IERSE, del GSC, de la Fundación Charles Darwin y del INAMHI para publicar sus datos. Cada fuente conserva su licencia, que se nombra en las descargas (`clima/descargas.py`), en el panel y en `LICENCIA-DATOS.md`.
- **La predicción de mareas se acaba el 30-dic-2027** y hoy no avisa. Se añade un aviso (etapa 2).
- **IERSE depende de una Mac encendida en Ecuador.** No cambia con la migración.
- **Los endpoints de las fuentes siguen siendo privados**: van en variables de entorno, nunca en este repositorio.
- **Tres husos horarios mezclados** en las fuentes (UTC−6, UTC−5 y UTC). Al portar cada recolector se conserva su conversión exacta.

## 6. Cómo se usa la etapa 1

```bash
manage.py clima_panel --recoger          # corre una vez todas las fuentes configuradas
manage.py clima_panel --publicar         # escribe los datos del panel
manage.py clima_satelite                 # una pasada del satélite
manage.py clima_importar …               # cargas históricas puntuales
```

- `/riesgos/api/clima/estaciones` · `/riesgos/api/clima/serie?estacion=…&variable=lluvia_mm&paso=hora|dia` · `/riesgos/api/clima/salud`
- `/riesgos/api/clima/pronostico` (publicado, recalibrado y modelos) · `/riesgos/api/clima/pronostico/verificacion`
- `manage.py clima_pronostico [--verificar | --recalibrar]`
- En el admin: estaciones, corridas, sincronizaciones y calibraciones (solo lectura), y **sensores dañados** (editable: reemplaza a `estaciones_danadas.json`).

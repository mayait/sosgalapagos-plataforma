# Entrada horaria desde los grupos de WhatsApp

**Qué hace.** Cada hora lee los grupos de WhatsApp de la emergencia, clasifica cada mensaje y sube a la plataforma lo que sirve: lo que trae una ubicación segura va al mapa; una foto o un aviso relevante sin ubicación segura va a **«Ayúdanos a ubicar»** (`/riesgos/ubicar/`); el ruido se descarta y se cuenta.

**Dónde corre.** En la Mac de coordinación (decisión de Julián, 26-nov-2026), sobre la carpeta de la exportación de siempre, `~/Downloads/WhatsApp lluvias 2027`. Orca la lanza cada hora. La carpeta tiene nombres y teléfonos: **nunca va al repositorio ni al servidor**.

**Qué llega al servidor.** Solo lo ya limpio: la foto (o un fotograma, si era un video), la hora del mensaje, el texto sin nombres ni teléfonos, la clasificación y, si es segura, la ubicación. Nunca el nombre del grupo, el remitente, su número, el video ni la carpeta.

## Cómo funciona

```
OpenWA (solo lectura) ──wa_export.py──► ~/Downloads/WhatsApp lluvias 2027/<grupo>/mensajes.json + adjuntos
                                                      │
                     ingesta.py procesar ◄────────────┘   (solo los grupos de la configuración, nunca chats privados)
   1. Junta en una ráfaga los mensajes de una persona con menos de 5 min entre sí (foto + texto + ubicación).
   2. Lugar seguro: una ubicación compartida (sus coordenadas están en mensajes.txt), un enlace de mapa
      o coordenadas en el texto, dentro de Galápagos. Un barrio nombrado no basta: es aproximado.
   3. Texto: quita teléfonos, menciones, enlaces, correos y los nombres conocidos (remitentes.json y el
      nombre del grupo). Después Jev decide qué palabras con mayúscula son nombres de persona y las oculta,
      y comprueba que no quede ninguno. Si queda la duda, el texto no se publica (la foto sí).
   4. Foto (o 3 fotogramas de un video, con ffmpeg): Jev mira si muestra la emergencia y si hay una persona
      identificable, un menor o un documento. Cualquiera de esas cosas, o un fallo al revisar → revisión.
   5. Sube cada elemento a POST /riesgos/api/ingesta/whatsapp (cabecera X-Llave).
                                                      │
   Plataforma: con ubicación → reglas.crear_reporte (como cualquier reporte, con sus duplicados).
               sin ubicación → «Ayúdanos a ubicar».   revisión → no se ve hasta que coordinación la aprueba.
```

- **Nunca duplica.** En la carpeta queda `registro_ingesta.jsonl`, con cada mensaje ya procesado, de qué chat y de qué archivo salió y qué se hizo con él: así coordinación encuentra el original (y el video completo). Además, el servidor no acepta dos veces el mismo `id_origen` (un resumen del id de WhatsApp que no permite volver al grupo ni a la persona) ni pide ubicar dos veces la misma foto reenviada a varios grupos.
- **Lo que falla se reintenta** en las corridas siguientes, hasta tres veces.
- **No borra nada de la carpeta.** `wa_export.py` reescribe `mensajes.json` y `mensajes.txt` con lo que encuentra desde `--since`. Por eso se le pide desde el mensaje más antiguo que ya está en la carpeta, y si aun así faltara alguno, `ingesta.py` lo vuelve a unir y guarda el `mensajes.txt` anterior como `mensajes.anterior-<fecha>.txt`.
- **Una ráfaga con un mensaje de hace menos de 5 minutos** espera a la próxima corrida, para no separar una foto de su texto.
- **Audios, stickers y documentos** no se procesan (se cuentan como «ignorados»).

## Clasificación: Jev (TypeSafe)

Comprobado el 26-nov-2026 con llamadas reales:

- `POST https://api.typesafe.ai/v1/systemone`, cabecera `Authorization: Bearer $TYPESAFE_API_KEY`, modelo `jev-latest` (responde `jev-1.14.0`). `GET /v1/models` lista los modelos.
- Cuerpo: `{"model", "state", "questions": {id: {"type": "noul" | "choice", "instructions", "criteria"}}}`. Respuesta: `{"model", "answers": {id: {"noul": p} | {"choice", "confidence", "probabilities"}}, "usage"}`.
- Imágenes: en `assets` (`{"type": "image", "format": "jpg", "data_base64"}`), referenciadas por su clave dentro de `state`, y con la cabecera `TypeSafe-Danger-Zone-Images: true`. Cada lado debe medir de 280 a 1568 px: `ingesta.py` las deja entre 320 y 1280. Documentación: <https://docs.typesafe.ai/llms.txt>.
- Los umbrales están en `UMBRAL`, al principio de `ingesta.py`, y son **preliminares**.
- **Respaldo:** si no hay llave de Jev, `ClasificadorReglas` decide la relevancia con palabras clave, manda **todas** las fotos a revisión y no publica ningún texto. Cualquier otro clasificador entra por la misma interfaz (`texto()` y `foto()`).

## La configuración de los grupos

Un JSON con la forma de `wa_export.py`. Va fuera del repositorio; la lista la mantiene coordinación:

```json
{
  "since": "2026-11-21T00:00:00",
  "tz": "Pacific/Galapagos",
  "sessions": {
    "trabajo": {"chats": [{"match": "Barrio", "name": "Nombre de la carpeta"}, {"id": "1203630000000000@g.us"}]},
    "personal": {"subdir": "Personal", "chats": "all"}
  }
}
```

Con `"chats": "all"`, se procesan todas las carpetas de esa sesión **que sean grupos** (`@g.us`). Un chat privado nunca se procesa, aunque esté en la carpeta.

## Instalar en la Mac

1. **ffmpeg:** `brew install ffmpeg`.
2. **wa_export.py:** `gh repo clone mayait/home-server-docs ~/dev/home-server-docs` (o define `WA_EXPORT` con su ruta).
3. **Llaves en el Llavero** (ya están `jev` y `openwa-lectura`). La de la plataforma se guarda con:
   ```sh
   security add-generic-password -s sosgalapagos -a plataforma-ingesta -w   # pega la llave cuando la pida
   ```
   Es el mismo valor que `INGESTA_LLAVE` en el `.env` del servidor (ver abajo). `ingesta.py` la pide sola a `~/.config/sosgalapagos/secreto.sh`.
4. **Configuración** en `~/.config/sosgalapagos/ingesta.env` (permisos 600; sin llaves dentro):
   ```sh
   INGESTA_SERVIDOR=https://sosgalapagos.org
   INGESTA_GRUPOS=/Users/julian/.config/sosgalapagos/export.horario.json
   INGESTA_CARPETA=/Users/julian/Downloads/WhatsApp lluvias 2027
   ```
5. **Probar sin subir nada:**
   ```sh
   python3 despliegue/ingesta/ingesta.py procesar --ensayo --desde 48h --limite 20
   ```
   Imprime cuántas ráfagas irían al mapa, a «Ayúdanos a ubicar», a revisión y cuántas son ruido.
6. **La orden de cada hora** (la que lanza Orca):
   ```sh
   python3 /Users/julian/dev/sosgalapagos-plataforma/despliegue/ingesta/ingesta.py horario
   ```
   Al terminar imprime una línea JSON con las cuentas: `{"mapa", "ubicar", "revision", "repetida", "ruido", "ya", "error", "ignorados"}`.

## En el servidor

Una sola variable en `despliegue/produccion/.env`:

```sh
INGESTA_LLAVE=        # openssl rand -hex 32 ; la misma va al Llavero de la Mac como «plataforma-ingesta»
```

Vacía, la entrada está cerrada (responde 403). La llave solo permite crear elementos de ingesta y leer la lista de tipos; cada foto pesa como mucho 3 MB y entran como mucho 300 elementos por hora (`INGESTA_MAX_BYTES` e `INGESTA_LIMITE_HORA` en `plataforma/ajustes.py`). Tras cambiarla: `docker compose up -d` en esa carpeta. Hace falta la migración `reportes/0017` (`desplegar.sh` la aplica).

## Apagarlo

Que Orca deje de lanzarlo, o vaciar `INGESTA_LLAVE` en el servidor.

# WhatsApp: del mensaje al mapa

*Escrito el 22-nov-2026. Está construido y probado sin WhatsApp real; en producción queda **apagado** hasta que Julián lo encienda (sección 5).*

Una persona escribe por WhatsApp lo que ve. El servicio decide si es material para el mapa, saca los datos, pregunta lo que falte, lo publica y le responde con el enlace y sus puntos.

## 1. El camino de un mensaje

```
WhatsApp ──► servidor OpenWA (homeserver) ──webhook──► /riesgos/api/whatsapp/entrada
                                                             │
        1. ¿Es de un chat permitido?            no ──► se ignora, no se guarda
        2. Filtro de reglas (entradas/filtro.py) no ──► se ignora, no se guarda
                                                             │ sí
        3. Modelo de lenguaje (entradas/ia.py): tipo, título, descripción, lugar, contacto
        4. Conversación (entradas/flujo.py): ¿falta algo? ──► pregunta por WhatsApp
                                                             │ completo
        5. Se publica como «por verificar» ──► responde con el enlace y los puntos
```

- **El filtro** son reglas y expresiones regulares: temas (agua, vía, infraestructura, ayuda, buenas noticias), si trae foto o ubicación, si nombra un lugar. Es gratis, corre en el servidor y deja fuera los saludos y la conversación común. `manage.py whatsapp_probar --solo-filtro "texto"` dice el puntaje y los motivos.
- **El modelo** solo ve lo que pasó el filtro. Devuelve siempre el mismo esquema (`Extraccion`).
- **Nada se publica sin lugar.** Se pide, por este orden: la ubicación de WhatsApp, un enlace de Google Maps o la dirección exacta. Si la persona no puede y nombró un barrio conocido, se publica en el centro del barrio y se dice que es aproximado. Si ni eso, pasa a la cola de coordinación.
- **Un lugar que recibe donaciones** pide además el teléfono de contacto del sitio.
- **El nombre para los puntos** se pregunta después de publicar: nunca frena un aviso.

## 2. Cambiar de modelo: Anthropic o Gemini

Se usa [Pydantic AI](https://ai.pydantic.dev), que no depende del proveedor. Se cambia con una variable:

| `IA_MODELO` | Llave |
|---|---|
| `anthropic:claude-haiku-5-5` | `ANTHROPIC_API_KEY` |
| `google:gemini-3.5-flash-lite` | `GOOGLE_API_KEY` |
| *(vacío)* | Ninguna: extracción con reglas, sin modelo |

Si el modelo falla o tarda, se usa la extracción con reglas y el servicio sigue. Las instrucciones del modelo están en `entradas/ia.py` (`INSTRUCCIONES`).

## 3. Privacidad

- **Solo se leen los chats de `WHATSAPP_CHATS`.** Los chats privados solo con `WHATSAPP_DIRECTOS=1`, y aun así solo lo que pasa el filtro o una conversación ya abierta.
- **Lo que no pasa el filtro no se guarda** ni se manda a ningún modelo.
- **El número nunca queda en claro.** Se guarda su resumen con clave (para reconocer a la persona) y el identificador del chat cifrado (para poder responderle).
- **El texto de los mensajes se borra a los 7 días**, y las conversaciones también.
- **La foto, el texto y el teléfono de contacto no se ven en el mapa** hasta que coordinación los revise, igual que en el formulario. El punto sí aparece de inmediato, como «por verificar».
- En un grupo no se responde salvo con `WHATSAPP_RESPONDER_EN_GRUPOS=1`.

## 4. Probar sin WhatsApp

```bash
despliegue/local.sh whatsapp_probar "Se inundó la calle Marchena, el agua llega a la rodilla"
despliegue/local.sh whatsapp_probar --ubicacion=-0.7412,-90.3135
despliegue/local.sh whatsapp_probar --foto foto.jpg "así está el puente de la vía a Bellavista"
```

Mantiene la conversación entre llamadas (chat de mentira `prueba@c.us`). No publica nada salvo con `--publicar`, que solo funciona en desarrollo.

## 5. Encenderlo en producción

Todo va en `despliegue/produccion/.env` del servidor. Faltan cuatro cosas que solo Julián puede dar:

1. **Una llave de API de OpenWA propia de este servicio** (`OPENWA_LLAVE`), con permiso sobre la sesión «trabajo», y la dirección del servidor (`OPENWA_URL`) y el id de la sesión (`OPENWA_SESION`).
2. **La llave del modelo** (`ANTHROPIC_API_KEY` o `GOOGLE_API_KEY`) y `IA_MODELO`.
3. **Qué chats se atienden** (`WHATSAPP_CHATS`) y si se abren los privados (`WHATSAPP_DIRECTOS`).
4. **El webhook en OpenWA**, para la sesión «trabajo», evento de mensaje recibido:
   `https://sosgalapagos.org/riesgos/api/whatsapp/entrada?secreto=<WHATSAPP_SECRETO>`

Orden recomendado: primero `WHATSAPP_MODO=ensayo` unos días. En ensayo no envía ni publica nada: guarda lo que habría respondido, y se revisa en el admin (`/riesgos/admin/entradas/mensajeentrante/`). Cuando las respuestas convenzan, `WHATSAPP_MODO=activo`.

## 6. Lo que no se pudo comprobar

- **El formato exacto del webhook de OpenWA.** No hay documentación pública y no tenía llave de API. El lector (`entradas/openwa.py`, `normalizar`) acepta las formas más comunes; hay que mirar el primer mensaje real en modo ensayo.
- **Dónde vienen las coordenadas de una ubicación.** En la base del servidor una ubicación trae solo la miniatura del mapa, sin latitud ni longitud. Si el webhook tampoco las trae, la ubicación de WhatsApp no servirá y habrá que pedir el enlace de Google Maps.
- **La descarga de fotos** (`bajar_foto`): la dirección sale del panel de OpenWA, sin probar.
- **Ninguna llamada real a un modelo**: no había llaves. Se probó con el modelo de pruebas de la librería.
- La sesión «trabajo» es el número personal de trabajo de Julián. Responder de forma automática desde ahí puede hacer que WhatsApp restrinja la cuenta.

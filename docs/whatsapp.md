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

## 5. Estado en producción (22-nov-2026)

**Encendido en modo ensayo.** Lee los chats privados del número de trabajo, procesa lo que pasa el filtro y guarda lo que respondería. No envía ningún mensaje ni publica nada.

| Qué | Cómo quedó |
|---|---|
| Modo | `WHATSAPP_MODO=ensayo` |
| Chats | Privados (`WHATSAPP_DIRECTOS=1`), solo lo que pasa el filtro. Ningún grupo (`WHATSAPP_CHATS` vacío) |
| Modelo | `IA_MODELO=anthropic:claude-haiku-5-5`. La llave de Gemini también está en el servidor: se cambia con `IA_MODELO=google:gemini-3.5-flash-lite` |
| Llave de OpenWA | «sosgalapagos-riesgos», rol operador, solo la sesión «trabajo» |
| Webhook | Sesión «trabajo», evento `message.received`, hacia `/riesgos/api/whatsapp/entrada`, con el secreto en la cabecera `X-Secreto` |

Todo está en `despliegue/produccion/.env` del servidor. Para cambiar algo: editar esa línea y `docker compose up -d` en esa carpeta.

**Revisar el ensayo:** `/riesgos/admin/entradas/mensajeentrante/` muestra cada mensaje atendido, por qué pasó el filtro y qué se habría respondido.

**Pasar a activo** (responde y publica): `WHATSAPP_MODO=activo`. Antes conviene leer unos días de ensayo.

**Apagarlo:** `WHATSAPP_MODO=apagado`, o desactivar el webhook en el panel de OpenWA.

## 6. Lo que se comprobó y lo que no

Comprobado el 22-nov-2026 con un mensaje de prueba del número personal de Julián a su número de trabajo:

- El webhook llega y trae el texto, y **la ubicación de WhatsApp sí trae latitud y longitud**.
- El modelo real (Claude Haiku 5.5) entiende el aviso, y Gemini 3.5 Flash Lite también (unos 2 s por mensaje).
- La conversación completa: texto → pide el lugar → ubicación → aviso armado en el punto correcto.
- La descarga de una foto con la llave del servicio.

Sin comprobar:

- Un mensaje **con foto** de punta a punta (la descarga funciona; falta verla entrar por el webhook).
- El modo **activo**: nunca se ha enviado una respuesta real ni publicado un aviso desde WhatsApp.
- Los **grupos**: no se sabe en qué campo viene quien escribe dentro de un grupo.
- La sesión «trabajo» es el número personal de trabajo de Julián. Responder de forma automática desde ahí puede hacer que WhatsApp restrinja la cuenta.

## Observaciones y duración (22-nov-2026)

Por el chat también se puede avisar lo que no es una emergencia y sirve para corregir el mapa de riesgo: «aquí no se inundó» o «todo bien por aquí» (`aqui_no_paso`), «anoche se inundó» (`aqui_se_inundo`) y «aquí siempre se inunda» (`zona_de_riesgo`). El filtro los deja pasar (tema `observacion`) y el modelo los distingue del agua que está ahí ahora.

En un daño en infraestructura, si la persona dice cuánto va a durar («un mes»), el aviso se queda ese tiempo (`duracion_dias`, entre 1 y 180 días). Si no lo dice, dura el plazo del tipo (14 días).


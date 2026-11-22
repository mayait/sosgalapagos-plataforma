# Relevo de IERSE

**Por qué existe.** El servidor de IERSE (Universidad del Azuay) solo responde a conexiones desde Ecuador. El de sosgalapagos.org está fuera del país y su conexión se agota. Una máquina que esté en Ecuador hace de mensajera.

**Qué hace.** Cada 5 minutos le pregunta a la plataforma qué pedir, se lo pide a IERSE y devuelve las respuestas tal cual. No interpreta nada, no guarda datos y no conoce las direcciones de IERSE: se las da la plataforma cada vez. Toda la lógica está en `clima/fuentes/ierse.py`.

**Qué necesita.** Python 3 (el que trae la Mac o cualquier Linux) y salida a internet. Nada más: ni base de datos, ni entorno virtual, ni SSH al servidor.

## Instalar

En la máquina de Ecuador, con esta carpeta copiada (o el repositorio clonado):

```sh
sh despliegue/relevo/instalar.sh
```

Pide la llave del relevo. Es el valor de `CLIMA_RELEVO_LLAVE` en el `.env` del servidor (la crea `desplegar.sh`). El instalador hace una vuelta de prueba y lo deja programado cada 5 minutos. Si en esa máquina corría el puente anterior (el que enviaba por SSH a la base SQLite), lo detiene y guarda su archivo; no lo borra.

## Qué pasa si se apaga

- IERSE deja de actualizarse. Las demás fuentes siguen.
- El nivel de lluvia de Santa Cruz se calcula con las otras estaciones de la isla. Si todas callan cuando el nivel era alto, la regla sube a «muy alto»; sin ninguna estación válida dice «sin datos», nunca «bajo».
- Al volver, el relevo recupera solo **hasta 10 días** hacia atrás.
- En `/riesgos/api/clima/salud` la fuente `ierse` muestra hace cuántos minutos fue su último éxito.

## Cómo dejar de depender de una máquina

Cualquiera de estas dos cosas hace innecesario el relevo:

1. **Pedir a IERSE que autorice la dirección IP del servidor.** Entonces se pone `CLIMA_IERSE_DIRECTO=1` en el `.env` y la plataforma pide por su cuenta.
2. **Instalar el relevo en una máquina que esté siempre encendida en Ecuador** (un servidor de la USFQ, por ejemplo). Puede haber más de un relevo a la vez: no se estorban.

## Ver cómo va

```sh
tail ~/.sosgalapagos-relevo/relevo.log
```

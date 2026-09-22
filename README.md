# Bot anti-bots de Telegram

Bot para grupos de Telegram que verifica que los nuevos miembros son humanos antes de dejarles escribir.

## Qué hace

Cuando alguien nuevo entra al grupo:

1. Lo silencia automáticamente (no puede escribir texto, mandar fotos, stickers, etc.)
2. Le manda un mensaje en el propio grupo con una pregunta de opción múltiple y botones para responder
3. Si responde correctamente antes de que pase el tiempo límite (120 segundos por defecto), recupera los permisos normales de escritura
4. Si no responde a tiempo, se le expulsa automáticamente del grupo (kick, no ban permanente — puede volver a intentar unirse)
5. Borra el mensaje de verificación una vez resuelto, para no ensuciar el chat
6. Si quien entra es otro bot, se le expulsa directamente sin preguntarle nada

Las preguntas son de cultura general de programación (por ejemplo, sintaxis básica de Java) — pensadas para filtrar bots automatizados, no para examinar a nadie. Se pueden editar o ampliar fácilmente (ver más abajo).

## Tecnología

- **Lenguaje**: Python 3.12
- **Librería**: [python-telegram-bot](https://github.com/python-telegram-bot/python-telegram-bot) (v21+), con el extra `job-queue` para poder programar la expulsión automática
- **Despliegue**: Docker (ver `Dockerfile`), corre como un contenedor único
- **Conexión con Telegram**: por *polling* (el bot pregunta activamente a Telegram por novedades), no por webhook — no necesita dominio, IP pública ni certificado SSL, solo salida a internet

## Archivos

- `anti_bot_telegram.py` — todo el código del bot (un único fichero)
- `requirements.txt` — dependencias de Python
- `Dockerfile` — receta para construir la imagen del contenedor

## Configuración necesaria en Telegram (@BotFather)

1. `/newbot` (o usar un bot ya creado) → te da un **token**
2. `/mybots` → tu bot → **Bot Settings** → **Group Privacy** → **Turn off**
   (imprescindible: sin esto, el bot no puede ver cuándo alguien nuevo entra al grupo)
3. Añadir el bot al grupo y hacerlo **administrador**, con permisos de:
   - **Ban users** (incluye poder restringir/silenciar miembros)
   - **Delete messages** (para poder borrar el mensaje de verificación)

## Cómo se ejecuta

El token se pasa como variable de entorno `TELEGRAM_BOT_TOKEN`, nunca va escrito en el código.

**Con Docker** (como está desplegado):

```bash
docker build -t anti-bot-telegram .
docker run -e TELEGRAM_BOT_TOKEN="tu_token_aqui" anti-bot-telegram
```

**Sin Docker, directamente con Python:**

```bash
pip install -r requirements.txt
export TELEGRAM_BOT_TOKEN="tu_token_aqui"
python anti_bot_telegram.py
```

## Configuración ajustable

Al principio del archivo `anti_bot_telegram.py`:

- `VERIFICATION_TIMEOUT` — segundos que tiene alguien para responder antes de ser expulsado (por defecto 120)
- `QUESTIONS` — lista de preguntas. Cada una tiene el texto, las opciones, y el índice (empezando en 0) de la opción correcta. Se puede editar libremente para añadir/quitar preguntas o cambiar el tema.

## Limitaciones a tener en cuenta

- El estado de las verificaciones pendientes se guarda **en memoria** (dentro del propio proceso). Si el contenedor se reinicia mientras alguien tiene una verificación pendiente, se pierde ese estado — no le expulsará ni le recuperará los permisos automáticamente, quedaría silenciado hasta que un admin lo revise a mano. Para un grupo con mucho movimiento de altas simultáneas, valdría la pena guardar esto en una base de datos en vez de en memoria.
- Solo gestiona un tipo de verificación (pregunta de opción múltiple). No hay CAPTCHA de imagen ni otros métodos.

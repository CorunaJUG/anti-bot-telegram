"""
Bot de Telegram anti-bots para grupos
=======================================

Qué hace:
- Cuando alguien nuevo entra al grupo, el bot lo silencia automáticamente
  (no puede escribir texto, mandar fotos, stickers, etc.)
- Le manda un mensaje privado en el chat del grupo con un botón "Soy humano ✅"
- Si pulsa el botón antes de que pase el tiempo límite (por defecto 120s),
  se le devuelven los permisos normales de escritura.
- Si NO pulsa el botón a tiempo, se le expulsa automáticamente del grupo
  (kick, no ban permanente: puede volver a intentar unirse).
- Borra el mensaje de verificación una vez resuelto, para no ensuciar el chat.

Requisitos
----------
1. Python 3.10+
2. Instalar la librería:
       pip install python-telegram-bot --break-system-packages

3. Crear el bot con @BotFather en Telegram:
   - /newbot -> te da un TOKEN
   - IMPORTANTE: en @BotFather -> /mybots -> tu bot -> Bot Settings ->
     Group Privacy -> "Turn off" (el bot necesita ver los mensajes/eventos
     de entrada de miembros).
   - Añade el bot al grupo y hazlo ADMINISTRADOR con permiso para:
       - Restringir/banear miembros ("Ban users" / "Restrict members")
       - Borrar mensajes (opcional, para limpiar)

4. Pon tu token abajo en TOKEN o como variable de entorno TELEGRAM_BOT_TOKEN.

Cómo ejecutarlo
----------------
    export TELEGRAM_BOT_TOKEN="123456:ABC-tu-token-aqui"
    python anti_bot_telegram.py
"""

import logging
import os
import random
import time
from dataclasses import dataclass, field

from telegram import (
    Update,
    ChatPermissions,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from telegram.ext import (
    Application,
    ChatMemberHandler,
    CallbackQueryHandler,
    ContextTypes,
)
from telegram.constants import ChatMemberStatus

# ------------------------------------------------------------------
# CONFIGURACIÓN
# ------------------------------------------------------------------

TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "PON_AQUI_TU_TOKEN")

# Segundos que tiene el nuevo miembro para verificarse antes de ser expulsado
VERIFICATION_TIMEOUT = 120

# --------------------------------------------------------------
# LISTA DE PREGUNTAS
# Cada pregunta tiene: el texto, una lista de opciones,
# y el índice (0-based) de la opción correcta.
# Añade/edita las que quieras.
# --------------------------------------------------------------
QUESTIONS = [
    {
        "text": "¿Cómo se declara una variable entera en Java?",
        "options": ["int numero;", "integer numero;", "num numero;", "entero numero;"],
        "correct": 0,
    },
    {
        "text": "¿Cuál es el método principal por el que empieza a ejecutarse un programa en Java?",
        "options": ["start()", "main()", "run()", "init()"],
        "correct": 1,
    },
    {
        "text": "¿Qué símbolo se usa para terminar una instrucción en Java?",
        "options": ["Punto (.)", "Coma (,)", "Punto y coma (;)", "Dos puntos (:)"],
        "correct": 2,
    },
    {
        "text": "¿Cuál de estos es un tipo de dato en Java?",
        "options": ["boolean", "texto", "letra", "cadena"],
        "correct": 0,
    },
    {
        "text": "¿Cómo se llama la palabra clave para crear una clase en Java?",
        "options": ["class", "struct", "object", "define"],
        "correct": 0,
    },
    {
        "text": "¿Qué imprime System.out.println(\"Hola\");?",
        "options": ["Hola", "\"Hola\"", "System.out", "Nada"],
        "correct": 0,
    },
    {
        "text": "¿Cuál es la extensión de un archivo fuente de Java?",
        "options": [".jav", ".java", ".jv", ".class"],
        "correct": 1,
    },
    {
        "text": "¿Qué tipo de dato se usa para valores verdadero/falso?",
        "options": ["boolean", "int", "char", "double"],
        "correct": 0,
    },
    {
        "text": "¿Cuál de estos es un bucle válido en Java?",
        "options": ["loop()", "repeat()", "for()", "iterate()"],
        "correct": 2,
    },
    {
        "text": "¿Qué palabra clave se usa para crear un objeto en Java?",
        "options": ["new", "create", "make", "object"],
        "correct": 0,
    },
]

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


@dataclass
class PendingVerification:
    chat_id: int
    user_id: int
    message_id: int
    join_time: float
    correct_option: int  # índice de la opción correcta para esta verificación


# user_id -> PendingVerification (en memoria; para producción usa una BD si tienes muchos grupos)
pending: dict[int, PendingVerification] = {}


# Permisos "silenciado": no puede mandar nada
MUTED_PERMISSIONS = ChatPermissions(
    can_send_messages=False,
    can_send_audios=False,
    can_send_documents=False,
    can_send_photos=False,
    can_send_videos=False,
    can_send_video_notes=False,
    can_send_voice_notes=False,
    can_send_polls=False,
    can_send_other_messages=False,
    can_add_web_page_previews=False,
)

# Permisos normales al verificarse (ajusta a como tengas configurado el grupo)
NORMAL_PERMISSIONS = ChatPermissions(
    can_send_messages=True,
    can_send_audios=True,
    can_send_documents=True,
    can_send_photos=True,
    can_send_videos=True,
    can_send_video_notes=True,
    can_send_voice_notes=True,
    can_send_polls=True,
    can_send_other_messages=True,
    can_add_web_page_previews=True,
)


async def on_chat_member_update(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Se dispara cuando el estado de un miembro cambia (entra, sale, etc.)."""
    result = update.chat_member
    if result is None:
        return

    old_status = result.old_chat_member.status
    new_status = result.new_chat_member.status
    user = result.new_chat_member.user
    chat = result.chat

    # Detectar SOLO cuando alguien pasa de "no miembro" a "miembro"
    just_joined = (
        old_status in (ChatMemberStatus.LEFT, ChatMemberStatus.BANNED, ChatMemberStatus.RESTRICTED)
        and new_status == ChatMemberStatus.MEMBER
    )
    if not just_joined:
        return

    if user.is_bot:
        # Opcional: banear directamente cualquier bot que intente unirse
        # salvo que tú mismo lo hayas añadido como admin/bot de confianza.
        try:
            await context.bot.ban_chat_member(chat.id, user.id)
            logger.info(f"Bot {user.username or user.id} expulsado automáticamente al unirse.")
        except Exception as e:
            logger.warning(f"No pude expulsar al bot {user.id}: {e}")
        return

    # 1) Silenciar inmediatamente al nuevo miembro humano
    try:
        await context.bot.restrict_chat_member(
            chat_id=chat.id,
            user_id=user.id,
            permissions=MUTED_PERMISSIONS,
        )
    except Exception as e:
        logger.warning(f"No pude restringir a {user.id}: {e}")
        return

    # 2) Elegir una pregunta aleatoria y mandarla con las opciones como botones
    question = random.choice(QUESTIONS)
    options = list(enumerate(question["options"]))
    random.shuffle(options)  # mezclar el orden en que se muestran

    buttons = [
        [
            InlineKeyboardButton(
                text,
                callback_data=f"verify:{user.id}:{original_idx}",
            )
        ]
        for original_idx, text in options
    ]
    keyboard = InlineKeyboardMarkup(buttons)

    name = user.first_name or user.username or "nuevo miembro"
    msg = await context.bot.send_message(
        chat_id=chat.id,
        text=(
            f"👋 ¡Bienvenido/a {name}!\n\n"
            f"Para evitar bots, responde correctamente en menos de "
            f"{VERIFICATION_TIMEOUT} segundos:\n\n"
            f"❓ {question['text']}"
        ),
        reply_markup=keyboard,
    )

    pending[user.id] = PendingVerification(
        chat_id=chat.id,
        user_id=user.id,
        message_id=msg.message_id,
        join_time=time.time(),
        correct_option=question["correct"],
    )

    # 3) Programar el kick automático si no se verifica a tiempo
    context.job_queue.run_once(
        kick_if_not_verified,
        when=VERIFICATION_TIMEOUT,
        data={"chat_id": chat.id, "user_id": user.id, "message_id": msg.message_id},
        name=f"verify_{chat.id}_{user.id}",
    )


async def on_verify_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Se dispara cuando alguien pulsa una de las opciones de respuesta."""
    query = update.callback_query

    _, uid_str, option_idx_str = query.data.split(":")
    target_user_id = int(uid_str)
    chosen_option = int(option_idx_str)

    # Solo el propio usuario puede responder por sí mismo
    if query.from_user.id != target_user_id:
        await query.answer("Esta pregunta no es para ti 🙂", show_alert=True)
        return

    chat_id = query.message.chat_id

    if target_user_id not in pending:
        # Ya se verificó antes o ya expiró
        await query.answer("Ya no hay verificación pendiente.", show_alert=True)
        return

    verification = pending[target_user_id]

    # Respuesta incorrecta: avisar pero dejar que lo siga intentando
    # mientras no se acabe el tiempo (no se borra "pending").
    if chosen_option != verification.correct_option:
        await query.answer("❌ Respuesta incorrecta, inténtalo de nuevo.", show_alert=True)
        return

    await query.answer("✅ ¡Correcto!")

    # Restaurar permisos normales
    try:
        await context.bot.restrict_chat_member(
            chat_id=chat_id,
            user_id=target_user_id,
            permissions=NORMAL_PERMISSIONS,
        )
    except Exception as e:
        logger.warning(f"No pude restaurar permisos de {target_user_id}: {e}")

    del pending[target_user_id]

    try:
        await query.message.delete()
    except Exception:
        pass

    await context.bot.send_message(
        chat_id=chat_id,
        text=f"✅ {query.from_user.first_name} verificado/a correctamente. ¡Bienvenido/a!",
    )


async def kick_if_not_verified(context: ContextTypes.DEFAULT_TYPE):
    """Job que se ejecuta pasado el tiempo límite si el usuario no se verificó."""
    job_data = context.job.data
    chat_id = job_data["chat_id"]
    user_id = job_data["user_id"]
    message_id = job_data["message_id"]

    if user_id not in pending:
        return  # Ya se verificó, no hacer nada

    del pending[user_id]

    try:
        await context.bot.ban_chat_member(chat_id, user_id)
        # Desbanear inmediatamente = kick (puede volver a intentar unirse más tarde)
        await context.bot.unban_chat_member(chat_id, user_id, only_if_banned=True)
        logger.info(f"Usuario {user_id} expulsado por no verificarse a tiempo.")
    except Exception as e:
        logger.warning(f"No pude expulsar a {user_id}: {e}")

    try:
        await context.bot.delete_message(chat_id, message_id)
    except Exception:
        pass


def main():
    if TOKEN == "PON_AQUI_TU_TOKEN":
        raise SystemExit(
            "Configura tu token: export TELEGRAM_BOT_TOKEN='tu_token' "
            "o edita la variable TOKEN en el script."
        )

    app = Application.builder().token(TOKEN).build()

    app.add_handler(ChatMemberHandler(on_chat_member_update, ChatMemberHandler.CHAT_MEMBER))
    app.add_handler(CallbackQueryHandler(on_verify_button, pattern=r"^verify:"))

    logger.info("Bot anti-bots iniciado. Esperando nuevos miembros...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()

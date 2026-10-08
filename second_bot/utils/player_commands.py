"""Команды для получения игровых команд игрока."""

from telegram import Update
from telegram.ext import ContextTypes

from utils.permissions import chat_restricted
from utils.realm_sheet import get_player_realm_from_sheet


async def cmd_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показывает команды для игрока, на чьё сообщение отвечаем"""

    if not update.message.reply_to_message:
        await update.message.reply_text(
            "❌ Ответьте на сообщение игрока командой /cmd",
            parse_mode="HTML"
        )
        return

    user = update.message.reply_to_message.from_user
    user_tag = f"@{user.username}" if user.username else None

    if not user_tag:
        await update.message.reply_text(
            "❌ У пользователя нет username в Telegram.",
            parse_mode="HTML"
        )
        return

    player_data = get_player_realm_from_sheet(user_tag)

    if not player_data:
        await update.message.reply_text(
            f"❌ Игрок с тегом {user_tag} не найден в таблице Ремесло.",
            parse_mode="HTML"
        )
        return

    player_name = player_data['name']

    # Формируем ответ с командами в HTML-блоках
    response = f"<b>Команды для игрока в Epsilion {player_name}:</b>\n"
    response += f"<code>/trade {player_name}</code>\n"
    response += f"<code>/getplayer {player_name}</code>\n"
    response += f"<code>/use_k {player_name}</code>\n\n"
    response += f"<b>Команды для игрока в Анархии {player_name}:</b>\n"
    response += f"<code>/find {player_name}</code>\n"
    response += f"<code>/prof {player_name}</code>\n"
    await update.message.reply_text(response, parse_mode="HTML")


@chat_restricted
async def trade_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показывает команду /trade для игрока, на чьё сообщение отвечаем"""

    # Игнорируем, если после /trade есть текст (аргументы)
    if context.args:
        return

    reply = update.message.reply_to_message

    # Игнорируем, если нет reply, нет автора, или это сервисное сообщение топика
    if not reply or not reply.from_user or reply.forum_topic_created:
        return

    user = reply.from_user
    user_tag = f"@{user.username}" if user.username else None

    if not user_tag:
        await update.message.reply_text(
            "❌ У пользователя нет username в Telegram.",
            parse_mode="HTML"
        )
        return

    player_data = get_player_realm_from_sheet(user_tag)

    if not player_data:
        await update.message.reply_text(
            f"❌ Игрок с тегом {user_tag} не найден в таблице Ремесло.",
            parse_mode="HTML"
        )
        return

    player_name = player_data['name']

    response = f"<code>/trade {player_name}</code>"

    await update.message.reply_text(response, parse_mode="HTML")



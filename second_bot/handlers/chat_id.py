"""Команда /chat_id — информация о текущем чате."""

from telegram import Update
from telegram.ext import ContextTypes


async def chat_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показывает ID текущего чата."""

    chat = update.effective_chat

    await update.message.reply_text(
        f"📋 <b>Информация о чате</b>\n\n"
        f"🆔 ID чата: <code>{chat.id}</code>\n"
        f"📝 Название: {chat.title or 'Личный чат'}\n"
        f"📌 Тип: {chat.type}",
        parse_mode="HTML"
    )
"""Команда /get — запуск inline-поиска по карточкам крафта."""

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from utils.permissions import chat_restricted


@chat_restricted
async def get_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /get — открывает inline-поиск по карточкам крафта."""

    keyboard = [[
        InlineKeyboardButton(
            "🔍 Начать поиск",
            switch_inline_query_current_chat="get "
        )
    ]]

    await update.message.reply_text(
        "🔎 <b>Поиск предмета</b>\n\n"
        "Нажми кнопку и начни вводить название.",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
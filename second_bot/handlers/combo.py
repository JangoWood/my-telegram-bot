from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from utils.permissions import chat_restricted


@chat_restricted
async def getcombo_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    keyboard = [[
        InlineKeyboardButton(
            "🔍 Начать поиск",
            switch_inline_query_current_chat="getcombo ",
        )
    ]]

    await update.message.reply_text(
        "🔎 <b>Поиск приема</b>\n\n"
        "Нажми кнопку и начни вводить название.",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )
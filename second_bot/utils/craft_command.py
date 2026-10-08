"""Команда /craft — меню выбора раздела."""

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from utils.permissions import chat_restricted
from utils.craft_menu import (
    count_all_equipment,
    count_all_instruments,
    count_all_cooking,
    count_all_alchemy,
)


@chat_restricted
async def craft_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /craft — меню выбора раздела."""

    craft_base = context.application.bot_data.get("craft_base", {})

    if not craft_base.get('grades'):
        await update.message.reply_text(
            "❌ База крафта не загружена.",
            parse_mode="HTML"
        )
        return

    keyboard = [
        [
            InlineKeyboardButton(
                f"🎒 Экипировка ({count_all_equipment(craft_base)})",
                callback_data="craft_section:equip"
            ),
            InlineKeyboardButton(
                f"⚒️ Инструменты ({count_all_instruments(craft_base)})",
                callback_data="craft_section:instr"
            ),
        ],
        [
            InlineKeyboardButton(
                f"🥨 Кулинария ({count_all_cooking(craft_base)})",
                callback_data="craft_section:cook"
            ),
            InlineKeyboardButton(
                f"🧪 Алхимия ({count_all_alchemy(craft_base)})",
                callback_data="craft_section:alchemy"
            ),
        ]
    ]

    await update.message.reply_text(
        "⚒️ <b>Крафт — выбери раздел:</b>",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
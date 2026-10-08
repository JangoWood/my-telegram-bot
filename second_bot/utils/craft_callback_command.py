"""Callback-команда /craft."""

from telegram import Update
from telegram.ext import ContextTypes

from utils.craft_callback import handle_craft_callback


async def craft_callback(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):
    """Обёртка для callback-кнопок /craft."""

    craft_base = context.application.bot_data.get("craft_base", {})

    await handle_craft_callback(
        update,
        context,
        craft_base
    )
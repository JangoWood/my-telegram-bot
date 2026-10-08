"""Обёртка для callback-кнопок."""

from telegram import Update
from telegram.ext import ContextTypes

from services.callback_handlers import handle_button_callback
from services.table_data import get_table_data_by_gid


async def button_callback(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):
    """Обрабатывает общие callback-кнопки."""

    await handle_button_callback(
        update,
        context,
        get_table_data_by_gid
    )
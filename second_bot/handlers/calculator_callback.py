"""Callback-кнопки калькулятора крафта."""

from telegram import Update
from telegram.ext import ContextTypes

from services.craft_calculator import build_calculator_text, build_calculator_buttons
from services.get_craft import find_craft_item_by_id


async def calculator_callback(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):
    """Изменяет множитель ресурсов в текущей карточке."""

    query = update.callback_query
    await query.answer()

    try:
        _, item_id, quantity = query.data.split('_', 2)
        quantity = int(quantity)

        if quantity < 1:
            quantity = 1

    except (ValueError, AttributeError):
        await query.answer(
            "❌ Некорректные данные",
            show_alert=True
        )
        return

    craft_base = context.application.bot_data.get("craft_base", {})

    item = find_craft_item_by_id(item_id, craft_base)

    if not item:
        await query.answer(
            "❌ Предмет не найден",
            show_alert=True
        )
        return

    calc_back = context.user_data.get(
        'craft_calc_back',
        {}
    ).get(str(item_id))

    if calc_back == '__get__':
        calc_back = None

    text = build_calculator_text(item, quantity)
    markup = build_calculator_buttons(
        item_id,
        quantity,
        calc_back
    )

    await query.edit_message_text(
        text,
        parse_mode="HTML",
        reply_markup=markup
    )
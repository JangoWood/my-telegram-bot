import re

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from utils.get_craft import find_craft_item_by_id


def _multiply_quantities(text, multiplier):
    """Умножает количества в карточке, не трогая названия ресурсов и грейды."""
    import re

    def repl_fraction(match):
        current = int(match.group(1))
        required = int(match.group(2))
        return f"({current}/{required * multiplier})"

    text = re.sub(r'\((\d+)\s*/\s*(\d+)\)', repl_fraction, text)

    def repl_colon(match):
        prefix = match.group(1)
        number = match.group(2).replace(' ', '')
        return prefix + f"{int(number) * multiplier:,}".replace(',', ' ')

    return re.sub(r'(^[^\n]*:\s*)([0-9][0-9 ]*)$', repl_colon, text, flags=re.MULTILINE)


def build_calculator_text(item, quantity=1):
    """Формирует ту же карточку, но с умноженными необходимыми ресурсами."""
    quantity = max(1, int(quantity))
    text = f"<b>{item.get('title', 'Без названия')}</b>\n\n"

    if quantity > 1:
        text += f"🧮 <b>Количество: ×{quantity}</b>\n\n"

    if item.get('where'):
        text += f"📍 <b>Где:</b> {item['where']}\n\n"

    if item.get('craft_block'):
        text += "<b>Ресурсы для крафта:</b>\n"
        text += _multiply_quantities(item['craft_block'], quantity) + "\n\n"

    if item.get('resources_block'):
        text += "<b>📊 Все необходимые ресурсы для крафта:</b>\n"
        resources = _multiply_quantities(item['resources_block'], quantity)
        text += f"<blockquote expandable>{resources}</blockquote>\n\n"

    if item.get('energy'):
        energy = item['energy']
        # В разных разделах энергия хранится в двух форматах:
        # "8🔋" / "8 🔋" и "🔋2". Умножаем оба варианта.
        energy = re.sub(
            r'(\d[\d ]*)\s*🔋',
            lambda m: f"{int(m.group(1).replace(' ', '')) * quantity}🔋",
            energy
        )
        energy = re.sub(
            r'🔋\s*(\d[\d ]*)',
            lambda m: f"🔋{int(m.group(1).replace(' ', '')) * quantity}",
            energy
        )
        text += f"<b>{energy}</b>"

    return text[:3997] + "..." if len(text) > 4000 else text


def build_calculator_buttons(item_id, quantity, back_cb=None):
    """Кнопки калькулятора. Уменьшение недоступно, если количество недостаточно."""
    quantity = max(1, int(quantity))
    # При первом нажатии +5/+10 это выбор количества, а не прибавление к базовой единице.
    # Поэтому из ×1 получаем ×5 или ×10, а дальше кнопки работают как обычное прибавление.
    plus5 = 5 if quantity == 1 else quantity + 5
    plus10 = 10 if quantity == 1 else quantity + 10
    row = [
        InlineKeyboardButton("➕1", callback_data=f"calc_{item_id}_{quantity + 1}"),
        InlineKeyboardButton("➕5", callback_data=f"calc_{item_id}_{plus5}"),
        InlineKeyboardButton("➕10", callback_data=f"calc_{item_id}_{plus10}"),
    ]
    buttons = [row]

    minus_row = []
    if quantity > 1:
        minus_row.append(InlineKeyboardButton("➖1", callback_data=f"calc_{item_id}_{quantity - 1}"))
    if quantity > 5:
        minus_row.append(InlineKeyboardButton("➖5", callback_data=f"calc_{item_id}_{quantity - 5}"))
    if quantity > 10:
        minus_row.append(InlineKeyboardButton("➖10", callback_data=f"calc_{item_id}_{quantity - 10}"))
    if minus_row:
        buttons.append(minus_row)

    if back_cb:
        buttons.append([InlineKeyboardButton("⬅️ Назад", callback_data=back_cb)])
    return InlineKeyboardMarkup(buttons)


async def calculator_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Изменяет множитель ресурсов в текущей карточке."""
    query = update.callback_query
    await query.answer()

    try:
        _, item_id, quantity = query.data.split('_', 2)
        quantity = int(quantity)
        if quantity < 1:
            quantity = 1
    except (ValueError, AttributeError):
        await query.answer("❌ Некорректные данные", show_alert=True)
        return

    item = find_craft_item_by_id(item_id, craft_base)
    if not item:
        await query.answer("❌ Предмет не найден", show_alert=True)
        return

    calc_back = context.user_data.get('craft_calc_back', {}).get(str(item_id))
    if calc_back == '__get__':
        calc_back = None

    text = build_calculator_text(item, quantity)
    markup = build_calculator_buttons(item_id, quantity, calc_back)

    await query.edit_message_text(text, parse_mode="HTML", reply_markup=markup)

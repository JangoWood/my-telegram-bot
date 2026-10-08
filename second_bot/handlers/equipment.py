"""Логика команды /enchant и парсинга экипировки."""

import re

from telegram import Update
from telegram.ext import ContextTypes

from utils.permissions import chat_restricted


def calculate_bonus(base_value, enchant_level):
    """Считает бонус параметра на уровне заточки по формуле"""
    bonuses = {
        1: 1,
        2: 2,
        3: 4,
        4: 6,
        5: 8,
        6: 10,
        7: 13,
        8: 16,
        9: 20,
        10: 25
    }

    if enchant_level not in bonuses:
        return 0

    bonus_percent = bonuses[enchant_level]
    bonus_value = base_value * bonus_percent / 100

    if 0 < bonus_value < 1:
        return 1
    return int(bonus_value)


def parse_equipment_message(text):
    """
    Парсит сообщение с экипировкой.
    Возвращает (название, текущий_уровень_заточки, список_бонусов) или (None, None, None).
    бонусы — список dict {'emoji': str, 'name': str, 'base': int}
    """
    if not text:
        return None, None, None

    lines = text.split('\n')

    # Ищем строку с заголовком предмета (содержит "[IV]" или другой грейд в скобках и ":")
    title_line = None
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        # Заголовок содержит "[...]" и заканчивается ":" (возможно с +N перед ним)
        if '[' in stripped and ']' in stripped and stripped.endswith(':'):
            title_line = stripped
            break

    if not title_line:
        return None, None, None

    # Извлекаем уровень заточки (+N) из заголовка
    current_enchant = 0
    enchant_match = re.search(r'\+(\d+)\s*:\s*$', title_line)
    if enchant_match:
        current_enchant = int(enchant_match.group(1))
        # Убираем "+N" из заголовка для чистого названия
        title_clean = re.sub(r'\s*\+\d+\s*:\s*$', '', title_line).rstrip(':').strip()
    else:
        title_clean = title_line.rstrip(':').strip()

    # Ищем блок "Бонусы предмета:" и парсим строки под ним
    bonuses = []
    in_bonus_block = False

    for line in lines:
        stripped = line.strip()

        if stripped.startswith('Бонусы предмета:'):
            in_bonus_block = True
            continue

        # Если начался другой блок — выходим
        if in_bonus_block and stripped.startswith('Бонусы заточки:'):
            break
        if in_bonus_block and stripped.startswith('⚙️'):
            break
        if in_bonus_block and stripped.startswith('Стоимость'):
            break
        if in_bonus_block and stripped.startswith('💰'):
            break

        if not in_bonus_block:
            continue

        # Строка вида: "· 🗡 Атака: 25 [➕️25]"
        match = re.match(r'^[·•]\s*(.+?):\s*(\d+)', stripped)
        if not match:
            continue

        name_part = match.group(1).strip()  # "🗡 Атака"
        base_value = int(match.group(2))

        # Разбиваем emoji и название
        parts = name_part.split(maxsplit=1)
        emoji = parts[0] if len(parts) > 1 else ''
        name = parts[1] if len(parts) > 1 else name_part

        bonuses.append({
            'emoji': emoji,
            'name': name,
            'base': base_value,
        })

    if not bonuses:
        return None, None, None

    return title_clean, current_enchant, bonuses


@chat_restricted
async def enchant_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показывает бонусы заточки для экипировки из сообщения (ответом)"""

    # Без reply — подсказка (в любом режиме)
    if not update.message.reply_to_message:
        await update.message.reply_text(
            "❌ Эта команда работает только ответом на сообщение с экипировкой.",
            parse_mode="HTML"
        )
        return

    text = update.message.reply_to_message.text or update.message.reply_to_message.caption
    if not text:
        await update.message.reply_text(
            "❌ В сообщении нет текста.",
            parse_mode="HTML"
        )
        return

    title, current_enchant, bonuses = parse_equipment_message(text)

    if not title or not bonuses:
        await update.message.reply_text(
            "❌ Не удалось распознать экипировку в сообщении.\n"
            "Убедитесь, что это сообщение со страницы экипировки.",
            parse_mode="HTML"
        )
        return

    # ==================== РЕЖИМ С АРГУМЕНТОМ ====================
    if context.args:
        arg = context.args[0].strip()

        # Проверяем, что это число от 1 до 10
        if not arg.isdigit() or not (1 <= int(arg) <= 10):
            await update.message.reply_text(
                "❌ Укажи уровень заточки от 1 до 10.\n"
                "Пример: /enchant 10",
                parse_mode="HTML"
            )
            return

        target_level = int(arg)

        response = f"<b>{title}</b>\n\n"

        # Блок 1: База
        response += "<b>📦 База:</b>\n"
        for bonus in bonuses:
            response += f"· {bonus['emoji']} {bonus['name']}: {bonus['base']}\n"

        # Блок 2: Бонус заточки
        response += f"\n<b>✨ Бонус заточки +{target_level}:</b>\n"
        for bonus in bonuses:
            bonus_value = calculate_bonus(bonus['base'], target_level)
            response += f"· {bonus['emoji']} {bonus['name']}: {bonus_value}\n"

        # Блок 3: Итог
        response += "\n<b>💎 Итог:</b>\n"
        for bonus in bonuses:
            bonus_value = calculate_bonus(bonus['base'], target_level)
            total = bonus['base'] + bonus_value
            response += f"· {bonus['emoji']} {bonus['name']}: {total}\n"

        await update.message.reply_text(response, parse_mode="HTML")
        return

    # ==================== РЕЖИМ БЕЗ АРГУМЕНТА (как раньше) ====================

    if current_enchant >= 10:
        await update.message.reply_text(
            "⚠️ Предмет уже заточен на +10. Заточить дальше не получится.",
            parse_mode="HTML"
        )
        return

    start_level = current_enchant + 1
    end_level = 10

    response = "Бонусы заточки (в скобках прирост от прошлого лвла)\n"
    response += f"{title} :\n"

    for level in range(start_level, end_level + 1):
        response += f"\n {level} \n"

        for bonus in bonuses:
            current_bonus = calculate_bonus(bonus['base'], level)
            prev_bonus = calculate_bonus(bonus['base'], level - 1) if level > 1 else 0
            diff = current_bonus - prev_bonus

            response += f"· {bonus['emoji']} {bonus['name']}: {current_bonus}({diff})\n"

    if len(response) > 4000:
        parts = [response[i:i + 4000] for i in range(0, len(response), 4000)]
        for part in parts:
            await update.message.reply_text(part, parse_mode="HTML")
    else:
        await update.message.reply_text(response, parse_mode="HTML")

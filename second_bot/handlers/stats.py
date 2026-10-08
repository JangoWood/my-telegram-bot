"""Команда /stats — статистика по выбранному грейду."""

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from utils.permissions import chat_restricted
from services.table_data import get_table_data_by_gid


@chat_restricted
async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показывает статистику для выбранного грейда"""

    grade_config = {
        't4+': {'gid': '0', 'name': 'T4+', 'aliases': ['t4+', 'т4+']},
        't4': {'gid': '296213375', 'name': 'T4', 'aliases': ['t4', 'т4']},
        't3+': {'gid': '677729120', 'name': 'T3+', 'aliases': ['t3+', 'т3+']},
    }

    if not context.args:
        keyboard = [
            [
                InlineKeyboardButton("📊 T4+", callback_data="stats_t4+"),
                InlineKeyboardButton("📊 T4", callback_data="stats_t4"),
                InlineKeyboardButton("📊 T3+", callback_data="stats_t3+")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await update.message.reply_text(
            "📊 <b>Выберите грейд для статистики:</b>\n\n"
            "• <b>T4+</b> — Анархия\n"
            "• <b>T4</b> — Наследие Анархии\n"
            "• <b>T3+</b> — Крылья Анархии",
            parse_mode="HTML",
            reply_markup=reply_markup
        )
        return

    arg = context.args[0].lower().strip()

    selected_gid = None
    selected_name = None

    for grade, config in grade_config.items():
        if arg in config['aliases']:
            selected_gid = config['gid']
            selected_name = config['name']
            break

    if not selected_gid:
        await update.message.reply_text(
            f"❌ Неизвестный грейд: '{arg}'\n\n"
            f"📋 <b>Доступные грейды:</b>\n"
            f"  • /stats t4+ — T4+\n"
            f"  • /stats t4 — T4\n"
            f"  • /stats t3+ — T3+",
            parse_mode="HTML"
        )
        return

    data, headers = get_table_data_by_gid(selected_gid)

    if not data:
        await update.message.reply_text(
            f"❌ Нет данных для статистики по грейду {selected_name}"
        )
        return

    date_start = headers[1].strip() if headers and len(headers) > 1 else "??"
    date_end = headers[2].strip() if headers and len(headers) > 2 else "??"

    total_points = 0
    total_coins = 0
    total_hand_coins = 0
    players_count = 0

    for row in data:
        if not row or len(row) < 7:
            continue

        name = row[0].strip()

        if not name or name.lower() == 'состав':
            continue

        try:
            points = float(row[3].replace(',', '.')) if row[3] else 0
            coins = float(row[4].replace(',', '.')) if row[4] else 0
            hand_coins = float(row[5].replace(',', '.')) if row[5] else 0

            players_count += 1

        except ValueError:
            continue

        total_points += points
        total_coins += coins
        total_hand_coins += hand_coins

    response = f"📊 <b>Статистика таблицы {selected_name}</b>\n"
    response += f"📅 <b>Период:</b> {date_start} – {date_end}\n\n"
    response += f"👥 <b>Игроков:</b> {players_count}\n"
    response += f"⚔️ <b>Сумма очков:</b> {total_points:,.2f}\n"
    response += f"💰 <b>Сумма монет:</b> {total_coins:,.2f}\n"
    response += f"💎 <b>Монет на руках:</b> {total_hand_coins:,.2f}\n"

    if players_count > 0:
        response += f"\n📈 <b>Средние значения:</b>\n"
        response += f"  ⚔️ Очки: {total_points / players_count:,.2f}\n"
        response += f"  💰 Монеты: {total_coins / players_count:,.2f}\n"
        response += f"  💎 Монет на руках: {total_hand_coins / players_count:,.2f}\n"

    await update.message.reply_text(response, parse_mode="HTML")
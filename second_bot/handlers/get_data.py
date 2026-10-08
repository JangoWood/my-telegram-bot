"""Команда /get_data — вывод данных выбранного грейда."""

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from utils.permissions import chat_restricted
from services.table_data import get_table_data_by_gid


@chat_restricted
async def get_data(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показывает данные из таблицы для указанного грейда."""

    grade_config = {
        't4+': {
            'gid': '0',
            'name': 'T4+',
            'aliases': ['t4+', 'т4+']
        },
        't4': {
            'gid': '296213375',
            'name': 'T4',
            'aliases': ['t4', 'т4']
        },
        't3+': {
            'gid': '677729120',
            'name': 'T3+',
            'aliases': ['t3+', 'т3+']
        },
    }

    if not context.args:
        keyboard = [
            [
                InlineKeyboardButton(
                    "📊 T4+",
                    callback_data="get_data_t4+"
                ),
                InlineKeyboardButton(
                    "📊 T4",
                    callback_data="get_data_t4"
                ),
                InlineKeyboardButton(
                    "📊 T3+",
                    callback_data="get_data_t3+"
                )
            ]
        ]

        reply_markup = InlineKeyboardMarkup(keyboard)

        await update.message.reply_text(
            "📊 <b>Выберите грейд для отображения таблицы:</b>\n\n"
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
            f"  • /get_data t4+ — T4+\n"
            f"  • /get_data t4 — T4\n"
            f"  • /get_data t3+ — T3+",
            parse_mode="HTML"
        )
        return

    data, headers = get_table_data_by_gid(selected_gid)

    if not data:
        await update.message.reply_text(
            f"❌ Нет данных для грейда {selected_name}"
        )
        return

    date_start = (
        headers[1].strip()
        if headers and len(headers) > 1
        else "??"
    )

    date_end = (
        headers[2].strip()
        if headers and len(headers) > 2
        else "??"
    )

    response = (
        f"📊 <b>Актуальная таблица {selected_name}</b>\n"
    )
    response += (
        f"📅 <b>Период:</b> {date_start} – {date_end}\n\n"
    )

    for row in data:
        name = row[0].strip() if row[0] else "???"
        points = row[3].strip() if len(row) > 3 else "0"
        coins = row[4].strip() if len(row) > 4 else "0"
        total = row[5].strip() if len(row) > 5 else "0"
        minus = row[6].strip() if len(row) > 6 else ""

        response += f"🤟🏼 <b>{name}</b>\n"
        response += (
            f"  📅 {date_start} – {date_end}: "
            f"⚔️ {points} очков, 💰 {coins} монет"
        )

        if total and total not in ['0', '']:
            response += f", 📦 итог: {total}"

        if minus and minus not in ['0', '', '-']:
            response += f" ⚠️ минус: {minus}"

        response += "\n\n"

        if len(response) > 4000:
            await update.message.reply_text(
                response,
                parse_mode="HTML"
            )
            response = ""

    if response:
        await update.message.reply_text(
            response,
            parse_mode="HTML"
        )
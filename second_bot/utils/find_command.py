"""Команда /find — поиск игрока в объединённых таблицах."""

from telegram import Update
from telegram.ext import ContextTypes

from utils.permissions import chat_restricted
from utils.find_search import find_players


MAIN_SHEET_GID = '0'
SECOND_SHEET_GID = '296213375'
THIRD_SHEET_GID = '677729120'


@chat_restricted
async def find(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Ищет игрока в объединённых данных с трёх листов."""

    if not context.args:
        await update.message.reply_text(
            "ℹ️ Укажите имя игрока для поиска. "
            "Пример: /find pa3ym",
            parse_mode="HTML"
        )
        return

    search = " ".join(context.args).lower().strip()

    found_items = find_players(
        search,
        MAIN_SHEET_GID,
        SECOND_SHEET_GID,
        THIRD_SHEET_GID
    )

    if found_items is None:
        await update.message.reply_text(
            "❌ Нет данных для поиска"
        )
        return

    if not found_items:
        await update.message.reply_text(
            f"❌ Игрок '{search}' не найден"
        )
        return

    response = (
        f"🔎 <b>Найдено {len(found_items)} результатов:</b>\n\n"
    )

    sheet_names = {
        'main': '📊 Анархия',
        'second': '📊 Наследие Анархии',
        'third': '📊 Крылья Анархии'
    }

    for item in found_items:
        row = item['row']
        headers = item['headers']
        source = item['source']

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

        player_name = (
            row[0].strip()
            if row[0]
            else "???"
        )
        points = (
            row[3].strip()
            if len(row) > 3
            else "0"
        )
        coins = (
            row[4].strip()
            if len(row) > 4
            else "0"
        )
        total = (
            row[5].strip()
            if len(row) > 5
            else "0"
        )
        minus = (
            row[6].strip()
            if len(row) > 6
            else ""
        )

        sheet_label = sheet_names.get(
            source,
            f'📊 {source}'
        )

        response += (
            f"🤟🏼 <b>{player_name}</b> — {sheet_label}\n"
        )
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
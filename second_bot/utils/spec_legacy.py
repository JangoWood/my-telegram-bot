"""Замороженная старая команда /s.

Команда больше не зарегистрирована в main().
Код сохранён без изменения логики для возможного использования в будущем.
"""

import csv
from io import StringIO

import requests
from telegram import Update
from telegram.ext import ContextTypes

from utils.permissions import chat_restricted


CW_SHEET_GID = '279368796'


@chat_restricted
async def spec(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показывает таблицу специализаций игроков (/s)."""

    try:
        url = (
            'https://docs.google.com/spreadsheets/d/e/'
            '2PACX-1vSWZzQ4H8cNNvFc0Yxt0XQ9XHH8869jWMoC12z8DPNc1Xd02CqRlIdRx4PbqTCb0lHA9yDx8nSdqb_i/'
            f'pub?gid={CW_SHEET_GID}&output=csv'
        )

        response = requests.get(url, timeout=15)
        response.raise_for_status()
        response.encoding = 'utf-8'

        csv_file = StringIO(response.text)
        reader = csv.reader(csv_file)
        data = list(reader)

        if not data:
            await update.message.reply_text("❌ Нет данных")
            return

        headers = data[0]

        response = "🛠️ <b>Специализации игроков</b>\n\n<pre>"
        response += (
            f"{'Игрок':<18} {'Крафтер':<8} {'Рыбалка':<8} "
            f"{'Шахтёр':<8} {'Охота':<8} {'Кулинария':<8} "
            f"{'Алхимия':<8} {'Плавильщик':<9} {'Фермер':<8}\n"
        )
        response += "-" * 85 + "\n"

        for row in data[1:]:
            if not row or len(row) < 2:
                continue

            name = row[0].strip() if row[0] else "???"
            crafter = row[1].strip() if len(row) > 1 else "-"
            fish = row[2].strip() if len(row) > 2 else "-"
            miner = row[3].strip() if len(row) > 3 else "-"
            hunt = row[4].strip() if len(row) > 4 else "-"
            cook = row[5].strip() if len(row) > 5 else "-"
            alchemy = row[6].strip() if len(row) > 6 else "-"
            smelt = row[7].strip() if len(row) > 7 else "-"
            farm = row[8].strip() if len(row) > 8 else "-"

            response += (
                f"{name:<18} {crafter:<8} {fish:<8} {miner:<8} "
                f"{hunt:<8} {cook:<8} {alchemy:<8} {smelt:<9} {farm:<8}\n"
            )

            if len(response) > 3900:
                response += "</pre>"
                await update.message.reply_text(
                    response,
                    parse_mode="HTML"
                )
                response = "<pre>"

        response += "</pre>"
        await update.message.reply_text(
            response,
            parse_mode="HTML"
        )

    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {e}")
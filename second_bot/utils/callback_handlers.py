from telegram import Update
from telegram.ext import ContextTypes


async def handle_button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE, get_table_data_by_gid):
    """Обрабатывает нажатия на кнопки выбора грейда"""
    query = update.callback_query
    await query.answer()

    # Для /get_data
    grade_map = {
        'get_data_t4+': ('0', 'T4+'),
        'get_data_t4': ('296213375', 'T4'),
        'get_data_t3+': ('677729120', 'T3+'),
    }

    # Для /stats
    stats_map = {
        'stats_t4+': ('0', 'T4+'),
        'stats_t4': ('296213375', 'T4'),
        'stats_t3+': ('677729120', 'T3+'),
    }

    # Обработка кнопок /get_data
    if query.data in grade_map:
        gid, name = grade_map[query.data]
        data, headers = get_table_data_by_gid(gid)

        if not data:
            await query.edit_message_text(f"❌ Нет данных для грейда {name}")
            return

        date_start = headers[1].strip() if headers and len(headers) > 1 else "??"
        date_end = headers[2].strip() if headers and len(headers) > 2 else "??"

        response = f"📊 <b>Актуальная таблица {name}</b>\n"
        response += f"📅 <b>Период:</b> {date_start} – {date_end}\n\n"

        for row in data:
            name_player = row[0].strip() if row[0] else "???"
            points = row[3].strip() if len(row) > 3 else "0"
            coins = row[4].strip() if len(row) > 4 else "0"
            total = row[5].strip() if len(row) > 5 else "0"
            minus = row[6].strip() if len(row) > 6 else ""

            response += f"🤟🏼 <b>{name_player}</b>\n"
            response += f"  📅 {date_start} – {date_end}: ⚔️ {points} очков, 💰 {coins} монет"
            if total and total not in ['0', '']:
                response += f", 📦 итог: {total}"
            if minus and minus not in ['0', '', '-']:
                response += f" ⚠️ минус: {minus}"
            response += "\n\n"

            if len(response) > 4000:
                await query.edit_message_text(response, parse_mode="HTML")
                response = ""

        await query.edit_message_text(response, parse_mode="HTML")

    # Обработка кнопок /stats
    elif query.data in stats_map:
        gid, name = stats_map[query.data]
        data, headers = get_table_data_by_gid(gid)

        if not data:
            await query.edit_message_text(f"❌ Нет данных для статистики по грейду {name}")
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

            player_name = row[0].strip()
            if not player_name or player_name.lower() == 'состав':
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

        response = f"📊 <b>Статистика таблицы {name}</b>\n"
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

        await query.edit_message_text(response, parse_mode="HTML")

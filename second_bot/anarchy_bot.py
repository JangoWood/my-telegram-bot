import os
import csv
import requests
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
from telegram.ext import InlineQueryHandler
from dotenv import load_dotenv
from pathlib import Path
from io import StringIO
import threading
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CallbackQueryHandler
import gspread
from google.oauth2.service_account import Credentials
import pytz
from telegram.ext import MessageHandler, filters
import json

# Загружаем переменные из .env в корне проекта
env_path = Path(__file__).parent.parent / '.env'
load_dotenv(env_path)

TELEGRAM_BOT_TOKEN = os.getenv('SECOND_BOT_TOKEN')
CSV_URL = 'https://docs.google.com/spreadsheets/d/e/2PACX-1vQhxznVeD5jD268Xb5x9crTJe0Di5Ra0OeSfqn_O_GA0plGpQHd8RFUg1GLlAnHgQx45XlklE1IVub9/pub?output=csv'
CW_SHEET_GID = '279368796'  # GID листа со специализациями

# GID листов с таблицами
MAIN_SHEET_GID = '0'                    # Основной лист
SECOND_SHEET_GID = '296213375'          # Второй лист
THIRD_SHEET_GID = '677729120'           # Третий лист (новый)

# Таблица с навыками игроков
CREDENTIALS_FILE = 'credentials.json'
REALM_SHEET_ID = os.getenv('REALM_SHEET_ID')
REALM_SHEET_NAME = 'Ремесло'  # Название листа (можно тоже вынести в переменные, если нужно)

user_sessions = {}  # {user_id: {'skills': {}, 'user_tag': str, 'telegram_name': str, 'skills_text': str}}
from utils.permissions import chat_restricted
from utils.health import run_flask
from utils.craft_loader import load_craft_file
from utils.get_keyboard import get_search_keyboard
from utils.get_craft import get_all_craft_search_items, build_get_card_text, find_craft_item_by_id
from utils.craft_menu import (
    get_grade_by_idx, get_class_by_idx, count_grade_items, count_instrument_items,
    count_cooking_items, count_group_items, count_class_items, count_all_equipment,
    count_all_instruments, count_all_cooking, count_all_alchemy, build_grades_keyboard,
    build_instruments_keyboard, build_cooking_keyboard, build_alchemy_keyboard,
    build_classes_keyboard, build_class_items_keyboard
,
    build_instrument_items_keyboard, build_cooking_items_keyboard
)
from utils.craft_calculator import build_calculator_text, build_calculator_buttons
from utils.craft_callback import handle_craft_callback
from utils.callback_handlers import handle_button_callback
from utils.table_data import get_table_data, get_table_data_by_gid, get_table_data_by_gid_with_fallback
from utils.find_search import find_players
from utils.spec_table import show_specializations
from utils.realm_skills import parse_skills_from_text
from utils.realm_update import user_sessions, update_realm, handle_nickname, clan_callback
from utils.realm_sheet import (
    get_player_realm_by_name,
    get_player_realm_from_sheet,
    update_player_realm,
    get_realm_worksheet,
)
from utils.equipment import enchant_command
from utils.player_commands import cmd_command, trade_command
from utils.stats import stats
from utils.get_command import get_command
from utils.get_data import get_data
from utils.chat_id import chat_id
from utils.help_command import help_command
from utils.start_command import start
from utils.craft_command import craft_command
from utils.calculator_callback import calculator_callback
from utils.realm_players import get_all_players_from_realm
from utils.realm_specializations import get_specializations_data
from utils.profile_command import get_profile
from utils.spec_command import spec_search
from utils.find_command import find
from utils.realm_profile_formatter import format_specializations_for_profile
from utils.craft_callback_command import craft_callback

# ==================== ЗАГРУЗКА БАЗЫ КРАФТА ====================

CRAFT_BASE_FILE = Path(__file__).parent / 'craft_base.json'

craft_base = {'grades': []}
craft_index = {
    'grades': [],         # [{name, classes: [...]}]
    'classes': {},        # {grade_idx: [{name, ...}]}
    'items': {},          # {(grade_idx, class_idx, item_path): item}
}


def load_craft_base():
    """Загружает craft_base.json и строит индексы для callback_data"""
    global craft_base, craft_index
    if not CRAFT_BASE_FILE.exists():
        print(f"⚠️ craft_base.json не найден по пути {CRAFT_BASE_FILE}")
        return

    craft_base, total = load_craft_file(CRAFT_BASE_FILE)

    # Строим индексы
    craft_index = {'grades': []}

    for grade in craft_base.get('grades', []):
        craft_index['grades'].append(grade['name'])
        for cls in grade.get('classes', []):
            # items — если плоский класс
            # groups — если класс с группами
            pass  # Индексы строим динамически в хендлерах по позициям

    print(f"✅ Загружено {len(craft_base.get('grades', []))} грейдов, {total} предметов")

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await handle_button_callback(update, context, get_table_data_by_gid)





# ==================== ОСНОВНАЯ ТАБЛИЦА (актуальная таблица) ====================



def format_table_row(row, headers):
    """Форматирует строку данных, используя даты из заголовков"""
    if not row or len(row) < 3:
        return ""

    name = row[0].strip()
    if not name or name.lower() == 'состав':
        return ""

    # Берём даты из заголовков (2-я и 3-я колонки, индекс 1 и 2)
    date_start = headers[1].strip() if len(headers) > 1 else "??"
    date_end = headers[2].strip() if len(headers) > 2 else "??"

    # Берём значения (индексы: 1=дата1, 2=дата2, 3=очки, 4=монеты, 5=итог)
    # Внимание: индексы зависят от того, что приходит из CSV
    points = row[3].strip() if len(row) > 3 else "0"
    coins = row[4].strip() if len(row) > 4 else "0"
    total = row[5].strip() if len(row) > 5 else "0"
    minus = row[6].strip() if len(row) > 6 else ""

    # Если очки и монеты пустые — пропускаем строку
    if not points and not coins:
        return ""

    result = f"🤟🏼 <b>{name}</b>\n"
    result += f"  📅 {date_start} – {date_end}: ⚔️ {points} очков, 💰 {coins} монет"
    if total and total not in ['0', '']:
        result += f", 📦 итог: {total}"
    if minus and minus not in ['0', '', '-']:
        result += f" ⚠️ минус: {minus}"
    result += "\n"

    return result


from utils.inline_search import inline_query

def format_realm_profile(player_data):
    """Форматирует вывод профиля из таблицы Ремесло"""
    name = player_data['name']
    tag = player_data['tag']
    clan = player_data['clan']
    skills = player_data['skills']
    updated = player_data['updated']

    response = f"🤟🏼 <b>{name}</b>\n"
    response += f"📱 {tag}\n"
    response += f"🏛️ {clan}\n\n"
    response += "<b>📋 Специализации:</b>\n"

    # Эмодзи для каждой специализации
    emojis = {
        'Крафтер': '⚒️',
        'Рыбалка': '🎣',
        'Шахтёр': '⛏️',
        'Охота': '🏹',
        'Кулинария': '🥨',
        'Алхимия': '🧪',
        'Плавильщик': '🪔',
        'Фермер': '🌽'
    }

    for skill, value in skills.items():
        if value:
            emoji = emojis.get(skill, '•')
            response += f"  {emoji} {skill}: <b>{value}</b>\n"
        else:
            response += f"  • {skill}: —\n"

    if updated:
        response += f"\n📅 <i>Обновлено: {updated}</i>"

    return response

# ==================== ЗАПУСК БОТА ====================

def main():
    print("🟢 Запуск бота...")
    load_craft_base()  # ← добавить эту строку
    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    app.bot_data["craft_base"] = craft_base

    # Основные команды
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))

    # Команды для основной таблицы
    app.add_handler(CommandHandler("get_data", get_data))
    app.add_handler(CommandHandler("stats", stats))
    app.add_handler(CommandHandler("find", find))

    # Команды для специализаций
    app.add_handler(CommandHandler("f", spec_search))
    app.add_handler(CommandHandler("get", get_command))

    # Инлайн-обработчик
    app.add_handler(InlineQueryHandler(inline_query))

    app.add_handler(CommandHandler("prof", get_profile))

    # Новая команда для обновления навыков
    app.add_handler(CommandHandler("update_me", update_realm))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_nickname))

    app.add_handler(CommandHandler("craft", craft_command))

    # Callback обработчики: сначала специфичный, потом общий

    app.add_handler(CallbackQueryHandler(clan_callback, pattern="^clan_"))
    app.add_handler(CallbackQueryHandler(calculator_callback, pattern="^calc_"))
    app.add_handler(CallbackQueryHandler(craft_callback, pattern="^craft_"))  #
    app.add_handler(CallbackQueryHandler(button_callback))  # без паттерна - обрабатывает всё остальное

    app.add_handler(CommandHandler("chat_id", chat_id))

    app.add_handler(CommandHandler("cmd", cmd_command))
    app.add_handler(CommandHandler("trade", trade_command))
    app.add_handler(CommandHandler("enchant", enchant_command))

    print("✅ Бот запущен и готов к работе!")
    app.run_polling()


if __name__ == '__main__':
    # Запускаем Flask в отдельном потоке для healthcheck
    threading.Thread(target=run_flask, daemon=True).start()
    # Запускаем бота
    main()
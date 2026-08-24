import os
import csv
import re
import requests
from datetime import datetime
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
from dotenv import load_dotenv
from pathlib import Path
from io import StringIO
from flask import Flask
import threading
from telegram import InlineQueryResultArticle, InputTextMessageContent
from telegram.ext import InlineQueryHandler
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CallbackQueryHandler
import gspread
from google.oauth2.service_account import Credentials
import pytz
from telegram.ext import MessageHandler, filters
import re

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

# Создаём Flask-приложение для healthcheck
flask_app = Flask(__name__)

@flask_app.route('/')
@flask_app.route('/health')
@flask_app.route('/healthcheck')
def health():
    return "OK", 200

def run_flask():
    # Render задаёт порт через переменную окружения PORT
    port = int(os.environ.get("PORT", 10000))
    flask_app.run(host='0.0.0.0', port=port)

# Белый список чатов (ID чатов, где бот работает)
ALLOWED_CHATS = [
    -1003335956100,  # Чат 1 (например, группа "Анархия")
    -1003692246189,  # Чат 2 (например, группа "Крылья")
    -1004260632686,  # Чат 2 (например, группа "Наследие")
]
# Белый список пользователей (кто может писать боту в личку)
ALLOWED_USERS = [
    121597158,  # Твой Telegram ID (замени на реальный)
]
def is_chat_allowed(chat_id):
    """Проверяет, разрешён ли чат"""
    return chat_id in ALLOWED_CHATS

def is_user_allowed(user_id):
    """Проверяет, разрешён ли пользователь для личных сообщений"""
    return user_id in ALLOWED_USERS

def chat_restricted(func):
    """Декоратор: команда работает только в разрешённых чатах или для разрешённых пользователей в личке"""

    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        # Если это инлайн-запрос — пропускаем
        if update.inline_query:
            return await func(update, context, *args, **kwargs)

        chat_id = update.effective_chat.id
        user_id = update.effective_user.id

        # Если чат в белом списке — разрешаем
        if is_chat_allowed(chat_id):
            return await func(update, context, *args, **kwargs)

        # Если это личный чат и пользователь в белом списке — разрешаем
        if update.effective_chat.type == 'private' and is_user_allowed(user_id):
            return await func(update, context, *args, **kwargs)

        # В личных сообщениях — подсказка
        if update.effective_chat.type == 'private':
            await update.message.reply_text(
                "🤖 <b>У вас нет доступа к боту в личных сообщениях.</b>\n\n"
                "Обратитесь к администратору для получения доступа.",
                parse_mode="HTML"
            )
        # В группах — игнорируем (молчим)
        return

    return wrapper

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
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


def get_table_data_by_gid_with_fallback(gid):
    """Загружает данные с листа по GID, с обработкой ошибок"""
    try:
        url = f'https://docs.google.com/spreadsheets/d/e/2PACX-1vQhxznVeD5jD268Xb5x9crTJe0Di5Ra0OeSfqn_O_GA0plGpQHd8RFUg1GLlAnHgQx45XlklE1IVub9/pub?gid={gid}&output=csv'
        response = requests.get(url, timeout=30)
        response.raise_for_status()
        response.encoding = 'utf-8'

        csv_file = StringIO(response.text)
        reader = csv.reader(csv_file)
        data = list(reader)

        if not data:
            return None, None, "❌ Таблица пуста"

        # Ищем строку с заголовком "Состав" (без учёта регистра)
        start_row = None
        for i, row in enumerate(data):
            if row and len(row) > 0 and row[0].strip().lower() == 'состав':
                start_row = i
                break

        if start_row is None:
            return None, None, "❌ Не найден заголовок 'Состав'"

        headers = data[start_row]
        start_row += 1

        result = []
        for row in data[start_row:]:
            if not row or len(row) < 2:
                continue
            name = row[0].strip() if row[0] else ""
            if name and len(name) > 1 and name.lower() != 'состав':
                result.append(row)

        return result, headers, None
    except Exception as e:
        return None, None, f"❌ Ошибка: {e}"

def get_table_data_by_gid(gid):
    """Загружает данные с конкретного листа по его GID (только одну таблицу под первым 'Состав')"""
    try:
        url = f'https://docs.google.com/spreadsheets/d/e/2PACX-1vQhxznVeD5jD268Xb5x9crTJe0Di5Ra0OeSfqn_O_GA0plGpQHd8RFUg1GLlAnHgQx45XlklE1IVub9/pub?gid={gid}&output=csv'
        response = requests.get(url, timeout=30)
        response.raise_for_status()
        response.encoding = 'utf-8'

        csv_file = StringIO(response.text)
        reader = csv.reader(csv_file)
        data = list(reader)

        if not data:
            return None, None

        # Ищем первую строку с "Состав" в первой колонке
        start_row = None
        for i, row in enumerate(data):
            if row and len(row) > 0 and row[0].strip().lower() == 'состав':
                start_row = i
                break

        if start_row is None:
            print(f"⚠️ На листе {gid} не найден заголовок 'Состав'")
            return None, None

        headers = data[start_row]
        start_row += 1

        # Собираем данные ТОЛЬКО до следующего "Состав" или пустой строки
        result = []
        for row in data[start_row:]:
            # Проверяем, не встретили ли новый "Состав" (начало следующей таблицы)
            if row and len(row) > 0 and row[0].strip().lower() == 'состав':
                break  # Останавливаемся на следующей таблице

            # Проверяем, не пустая ли строка (и не заканчивается ли таблица)
            if not row or len(row) < 2:
                continue

            name = row[0].strip() if row[0] else ""
            # Пропускаем пустые строки и строки-заголовки
            if name and len(name) > 1 and name.lower() != 'состав':
                result.append(row)

        print(f"✅ Лист {gid}: загружено {len(result)} строк (ожидалось около 40)")
        return result, headers
    except Exception as e:
        print(f"❌ Ошибка загрузки листа {gid}: {e}")
        return None, None

# ==================== ОСНОВНАЯ ТАБЛИЦА (актуальная таблица) ====================

def get_table_data():
    """Загружает CSV и возвращает данные из ПЕРВОЙ таблицы с 'Состав'"""
    try:
        response = requests.get(CSV_URL, timeout=15)
        response.raise_for_status()
        response.encoding = 'utf-8'

        csv_file = StringIO(response.text)
        reader = csv.reader(csv_file)
        data = list(reader)

        if not data:
            return None, None, "❌ Таблица пуста"

        # Находим ПЕРВУЮ ячейку с "Состав"
        target_row = None
        target_col = None
        for i, row in enumerate(data):
            for j, cell in enumerate(row):
                if cell and cell.strip() == 'Состав':
                    target_row = i
                    target_col = j
                    break
            if target_row is not None:
                break

        if target_row is None:
            return None, None, "❌ Не найдена ячейка 'Состав'"

        print(f"Найден 'Состав' в строке {target_row}, колонке {target_col}")

        # Заголовки — это строка target_row, начиная с target_col
        headers = data[target_row][target_col:]

        # Данные начинаются со следующей строки
        start_row = target_row + 1

        # Собираем ВСЕ строки, которые содержат данные
        result = []
        for row in data[start_row:]:
            # Проверяем, не наткнулись ли на новый "Состав" (начало следующей таблицы)
            for cell in row:
                if cell and cell.strip() == 'Состав':
                    break
            else:
                if len(row) > target_col:
                    data_row = row[target_col:]
                    if data_row and any(cell and cell.strip() for cell in data_row):
                        name = data_row[0].strip() if data_row[0] else ""
                        if name:
                            result.append(data_row)
                continue
            break

        if not result:
            return None, None, "❌ Нет данных под 'Состав'"

        return result, headers, None
    except Exception as e:
        return None, None, f"❌ Ошибка: {e}"


def get_combined_table_data():
    """Объединяет данные с трёх листов для поиска (/find), сохраняя заголовки каждого"""
    sheets = [
        {'gid': MAIN_SHEET_GID, 'name': 'main'},
        {'gid': SECOND_SHEET_GID, 'name': 'second'},
        {'gid': THIRD_SHEET_GID, 'name': 'third'},
    ]

    combined = []

    for sheet in sheets:
        data, headers = get_table_data_by_gid(sheet['gid'])
        if data:
            for row in data:
                combined.append({
                    'row': row,
                    'headers': headers,
                    'source': sheet['name']
                })

    print(f"📊 Всего строк для поиска: {len(combined)}")
    return combined

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


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📊 <b>Бот для чтения таблицы</b>\n\n"
        "Отправьте /help для просмотра всех команд.\n\n"
        "📋 <b>Быстрые команды:</b>\n"
        "  /get_data — данные из таблицы\n"
        "  /stats — статистика\n"
        "  /s — специализации игроков\n"
        "  /f алхимия — поиск по специализации"
        "  /prof - 👤 Показать специализации игрока (ответом на его сообщение)",
        parse_mode="HTML"
    )

@chat_restricted
async def get_data(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показывает данные из таблицы для указанного грейда"""

    grade_config = {
        't4+': {'gid': '0', 'name': 'T4+', 'aliases': ['t4+', 'т4+']},
        't4': {'gid': '296213375', 'name': 'T4', 'aliases': ['t4', 'т4']},
        't3+': {'gid': '677729120', 'name': 'T3+', 'aliases': ['t3+', 'т3+']},
    }

    if not context.args:
        keyboard = [
            [
                InlineKeyboardButton("📊 T4+", callback_data="get_data_t4+"),
                InlineKeyboardButton("📊 T4", callback_data="get_data_t4"),
                InlineKeyboardButton("📊 T3+", callback_data="get_data_t3+")
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
        await update.message.reply_text(f"❌ Нет данных для грейда {selected_name}")
        return

    date_start = headers[1].strip() if headers and len(headers) > 1 else "??"
    date_end = headers[2].strip() if headers and len(headers) > 2 else "??"

    response = f"📊 <b>Актуальная таблица {selected_name}</b>\n"
    response += f"📅 <b>Период:</b> {date_start} – {date_end}\n\n"

    for row in data:
        name = row[0].strip() if row[0] else "???"
        points = row[3].strip() if len(row) > 3 else "0"
        coins = row[4].strip() if len(row) > 4 else "0"
        total = row[5].strip() if len(row) > 5 else "0"
        minus = row[6].strip() if len(row) > 6 else ""

        response += f"🤟🏼 <b>{name}</b>\n"
        response += f"  📅 {date_start} – {date_end}: ⚔️ {points} очков, 💰 {coins} монет"
        if total and total not in ['0', '']:
            response += f", 📦 итог: {total}"
        if minus and minus not in ['0', '', '-']:
            response += f" ⚠️ минус: {minus}"
        response += "\n\n"

        if len(response) > 4000:
            await update.message.reply_text(response, parse_mode="HTML")
            response = ""

    if response:
        await update.message.reply_text(response, parse_mode="HTML")

@chat_restricted
async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показывает статистику для выбранного грейда"""

    # Словарь соответствия -> GID и название
    grade_config = {
        't4+': {'gid': '0', 'name': 'T4+', 'aliases': ['t4+', 'т4+']},
        't4': {'gid': '296213375', 'name': 'T4', 'aliases': ['t4', 'т4']},
        't3+': {'gid': '677729120', 'name': 'T3+', 'aliases': ['t3+', 'т3+']},
    }

    # Проверяем, указан ли аргумент
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

    # Определяем, какой грейд запросили
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

    # Загружаем данные с выбранного листа
    data, headers = get_table_data_by_gid(selected_gid)

    if not data:
        await update.message.reply_text(f"❌ Нет данных для статистики по грейду {selected_name}")
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

    # Средние значения
    if players_count > 0:
        response += f"\n📈 <b>Средние значения:</b>\n"
        response += f"  ⚔️ Очки: {total_points / players_count:,.2f}\n"
        response += f"  💰 Монеты: {total_coins / players_count:,.2f}\n"
        response += f"  💎 Монет на руках: {total_hand_coins / players_count:,.2f}\n"

    await update.message.reply_text(response, parse_mode="HTML")

@chat_restricted
async def find(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Ищет игрока в объединённых данных с трёх листов"""
    if not context.args:
        await update.message.reply_text(
            "ℹ️ Укажите имя игрока для поиска. Пример: /find pa3ym",
            parse_mode="HTML"
        )
        return

    search = ' '.join(context.args).lower().strip()

    combined_data = get_combined_table_data()

    if not combined_data:
        await update.message.reply_text("❌ Нет данных для поиска")
        return

    found_items = []

    for item in combined_data:
        row = item['row']
        name = row[0].strip().lower() if row[0] else ""
        if not name:
            continue

        if search in name:
            found_items.append(item)

    if not found_items:
        await update.message.reply_text(f"❌ Игрок '{search}' не найден")
        return

    response = f"🔎 <b>Найдено {len(found_items)} результатов:</b>\n\n"

    # Названия листов для отображения
    sheet_names = {
        'main': '📊 Анархия',
        'second': '📊 Наследие Анархии',
        'third': '📊 Крылья Анархии'
    }

    for item in found_items:
        row = item['row']
        headers = item['headers']
        source = item['source']

        date_start = headers[1].strip() if headers and len(headers) > 1 else "??"
        date_end = headers[2].strip() if headers and len(headers) > 2 else "??"

        player_name = row[0].strip() if row[0] else "???"
        points = row[3].strip() if len(row) > 3 else "0"
        coins = row[4].strip() if len(row) > 4 else "0"
        total = row[5].strip() if len(row) > 5 else "0"
        minus = row[6].strip() if len(row) > 6 else ""

        # Добавляем название листа
        sheet_label = sheet_names.get(source, f'📊 {source}')

        response += f"🤟🏼 <b>{player_name}</b> — {sheet_label}\n"
        response += f"  📅 {date_start} – {date_end}: ⚔️ {points} очков, 💰 {coins} монет"
        if total and total not in ['0', '']:
            response += f", 📦 итог: {total}"
        if minus and minus not in ['0', '', '-']:
            response += f" ⚠️ минус: {minus}"
        response += "\n\n"

        if len(response) > 4000:
            await update.message.reply_text(response, parse_mode="HTML")
            response = ""

    if response:
        await update.message.reply_text(response, parse_mode="HTML")

# ==================== СПЕЦИАЛИЗАЦИИ (лист с GID 279368796) ====================
@chat_restricted
async def spec(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показывает таблицу специализаций игроков (/s)"""
    try:
        url = f'https://docs.google.com/spreadsheets/d/e/2PACX-1vSWZzQ4H8cNNvFc0Yxt0XQ9XHH8869jWMoC12z8DPNc1Xd02CqRlIdRx4PbqTCb0lHA9yDx8nSdqb_i/pub?gid={CW_SHEET_GID}&output=csv'
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
        response += f"{'Игрок':<18} {'Крафтер':<8} {'Рыбалка':<8} {'Шахтёр':<8} {'Охота':<8} {'Кулинария':<8} {'Алхимия':<8} {'Плавильщик':<9} {'Фермер':<8}\n"
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

            response += f"{name:<18} {crafter:<8} {fish:<8} {miner:<8} {hunt:<8} {cook:<8} {alchemy:<8} {smelt:<9} {farm:<8}\n"

            if len(response) > 3900:
                response += "</pre>"
                await update.message.reply_text(response, parse_mode="HTML")
                response = "<pre>"

        response += "</pre>"
        await update.message.reply_text(response, parse_mode="HTML")

    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {e}")

async def spec_search(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Поиск игроков по специализации из таблицы Ремесло"""
    if not context.args:
        await update.message.reply_text(
            "🔍 <b>Поиск по специализации</b>\n\n"
            "Примеры:\n"
            "  /f крафтер — все крафтеры\n"
            "  /f крафтер ГМ4 — только ГМ4\n"
            "  /f кулинария ПМ3 — только ПМ3\n\n"
            "📋 <b>Доступные специализации и синонимы:</b>\n"
            "  • крафтер / крафт / к\n"
            "  • рыбалка / рыба / р\n"
            "  • шахтёр / шахта / ш\n"
            "  • охота / охотник / о\n"
            "  • кулинария / еда / кухня / кул\n"
            "  • алхимия / алхим / алх / а\n"
            "  • плавильщик / плавка / пл\n"
            "  • фермер / ферма / ф",
            parse_mode="HTML"
        )
        return

    # Разбираем аргументы
    search_input = context.args[0].lower()
    level_filter = context.args[1].upper() if len(context.args) > 1 else None

    synonyms = {
        'крафтер': 'Крафтер', 'крафт': 'Крафтер', 'к': 'Крафтер',
        'рыбалка': 'Рыбалка', 'рыба': 'Рыбалка', 'р': 'Рыбалка',
        'шахтёр': 'Шахтёр', 'шахта': 'Шахтёр', 'ш': 'Шахтёр',
        'охота': 'Охота', 'охотник': 'Охота', 'о': 'Охота',
        'кулинария': 'Кулинария', 'еда': 'Кулинария', 'кухня': 'Кулинария', 'кул': 'Кулинария',
        'алхимия': 'Алхимия', 'алхим': 'Алхимия', 'алх': 'Алхимия', 'а': 'Алхимия',
        'плавильщик': 'Плавильщик', 'плавка': 'Плавильщик', 'пл': 'Плавильщик',
        'фермер': 'Фермер', 'ферма': 'Фермер', 'ф': 'Фермер',
    }

    skill_name = synonyms.get(search_input)
    if not skill_name:
        await update.message.reply_text(
            f"❌ Специализация '{search_input}' не найдена.\n\n"
            f"📋 <b>Доступные:</b> крафтер, рыбалка, шахтёр, охота, кулинария, алхимия, плавильщик, фермер",
            parse_mode="HTML"
        )
        return

    # Загружаем данные из таблицы Ремесло
    all_players = get_all_players_from_realm()

    if not all_players:
        await update.message.reply_text("❌ Нет данных в таблице Ремесло")
        return

    # Группируем игроков по уровню
    levels = {}

    for player in all_players:
        level = player['skills'].get(skill_name, '')
        if not level or level == '-':
            continue

        if level_filter and level.upper() != level_filter:
            continue

        if level not in levels:
            levels[level] = []
        levels[level].append(player['name'])

    if not levels:
        filter_text = f" с уровнем {level_filter}" if level_filter else ""
        await update.message.reply_text(f"❌ Нет игроков по специализации '{skill_name}'{filter_text}")
        return

    # Сортировка уровней
    def sort_key(level):
        order = {'Э': 1, 'ГМ': 2, 'М': 3, 'ПМ': 4, 'У': 5}
        if level[:2] in order:
            prefix = level[:2]
            num_start = 2
        elif level[:1] in order:
            prefix = level[:1]
            num_start = 1
        else:
            return (99, 0)
        try:
            num = int(level[num_start:]) if len(level) > num_start else 0
        except:
            num = 0
        return (order.get(prefix, 99), -num)

    sorted_levels = sorted(levels.keys(), key=sort_key)

    filter_text = f" {level_filter}" if level_filter else ""
    response = f"🔍 <b>Поиск по специализации: {skill_name}{filter_text}</b>\n\n"

    for level in sorted_levels:
        players = sorted(levels[level], key=str.lower)
        response += f"<b>{level}</b> ({len(players)}): {', '.join(players)}\n"

        if len(response) > 4000:
            await update.message.reply_text(response, parse_mode="HTML")
            response = ""

    if response:
        await update.message.reply_text(response, parse_mode="HTML")

@chat_restricted
async def inline_query(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обрабатывает инлайн-запросы (@bot_name текст) — сразу показываем результат"""

    query = update.inline_query.query.strip().lower()

    if not query:
        results = [
            InlineQueryResultArticle(
                id="help",
                title="🔍 Введите имя игрока для поиска",
                input_message_content=InputTextMessageContent("📊 Введите имя игрока, например: pa3ym, Giz, Антифон")
            )
        ]
        await update.inline_query.answer(results, cache_time=0)
        return

    # Загружаем данные из таблицы
    data, headers, error = get_table_data()

    if error or not data:
        results = [
            InlineQueryResultArticle(
                id="error",
                title="❌ Ошибка загрузки данных",
                input_message_content=InputTextMessageContent("❌ Не удалось загрузить таблицу. Попробуйте позже.")
            )
        ]
        await update.inline_query.answer(results, cache_time=0)
        return

    # Ищем совпадения
    found = []
    for row in data:
        if not row:
            continue
        name = row[0].strip() if row[0] else ""
        if not name or name.lower() == 'состав':
            continue

        if query in name.lower():
            date_start = headers[1].strip() if len(headers) > 1 else "??"
            date_end = headers[2].strip() if len(headers) > 2 else "??"
            points = row[3].strip() if len(row) > 3 else "0"
            coins = row[4].strip() if len(row) > 4 else "0"
            total = row[5].strip() if len(row) > 5 else "0"
            minus = row[6].strip() if len(row) > 6 else ""

            text = f"🤟🏼 <b>{name}</b>\n"
            text += f"📅 {date_start} – {date_end}\n"
            text += f"⚔️ {points} очков\n"
            text += f"💰 {coins} монет"
            if total and total not in ['0', '']:
                text += f"\n📦 итог: {total}"
            if minus and minus not in ['0', '', '-']:
                text += f"\n⚠️ минус: {minus}"

            result = InlineQueryResultArticle(
                id=f"player_{name}",
                title=f"🤟🏼 {name}",
                description=f"⚔️ {points} очков, 💰 {coins} монет",
                input_message_content=InputTextMessageContent(text, parse_mode="HTML")
            )
            found.append(result)

            if len(found) >= 20:
                break

    if not found:
        results = [
            InlineQueryResultArticle(
                id="not_found",
                title=f"❌ Не найдено: '{query}'",
                description="Попробуйте другое имя",
                input_message_content=InputTextMessageContent(f"❌ Игрок '{query}' не найден в текущей таблице")
            )
        ]
        await update.inline_query.answer(results, cache_time=0)
        return

    await update.inline_query.answer(found, cache_time=0)

def get_all_players_from_realm():
    """Получает всех игроков из таблицы Ремесло"""
    try:
        ws = get_realm_worksheet()
        if ws is None:
            print("❌ Не удалось подключиться к таблице Ремесло")
            return None

        all_data = ws.get_all_values()
        if len(all_data) < 2:
            return []

        players = []
        for row in all_data[1:]:  # Пропускаем заголовки
            if not row or len(row) < 3:
                continue
            if row[0] and row[1]:  # Есть тег и имя
                players.append({
                    'tag': row[0],
                    'name': row[1],
                    'clan': row[2],
                    'skills': {
                        'Крафтер': row[3] if len(row) > 3 else '',
                        'Рыбалка': row[4] if len(row) > 4 else '',
                        'Шахтёр': row[5] if len(row) > 5 else '',
                        'Охота': row[6] if len(row) > 6 else '',
                        'Кулинария': row[7] if len(row) > 7 else '',
                        'Алхимия': row[8] if len(row) > 8 else '',
                        'Плавильщик': row[9] if len(row) > 9 else '',
                        'Фермер': row[10] if len(row) > 10 else '',
                    }
                })
        return players
    except Exception as e:
        print(f"Ошибка получения данных из таблицы Ремесло: {e}")
        return None

@chat_restricted
async def get_profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показывает специализации игрока из таблицы Ремесло"""

    user_tag = None
    is_self = False

    # Вариант 1: указан аргумент (@username или имя игрока)
    if context.args:
        arg = ' '.join(context.args).strip()
        if arg.startswith('@'):
            user_tag = arg
        else:
            player_data = get_player_realm_by_name(arg)
            if player_data:
                user_tag = player_data['tag']
            else:
                await update.message.reply_text(
                    f"❌ Игрок с именем '{arg}' не найден в таблице Ремесло.",
                    parse_mode="HTML"
                )
                return

    # Вариант 2: ответ на сообщение (но только если это не команда и не @l1b_b1l)
    elif update.message.reply_to_message:
        replied_user = update.message.reply_to_message.from_user

        # Проверяем, не отвечаем ли мы на проблемного пользователя
        if replied_user.username == 'l1b_b1l':
            # Если отвечаем на @l1b_b1l — игнорируем, показываем свой профиль
            sender = update.message.from_user
            if sender and sender.username:
                user_tag = f"@{sender.username}"
                is_self = True
            else:
                await update.message.reply_text(
                    "❓ Используйте /prof @username или ответьте на сообщение игрока с username",
                    parse_mode="HTML"
                )
                return
        elif replied_user and replied_user.username:
            user_tag = f"@{replied_user.username}"
        else:
            await update.message.reply_text(
                f"❌ У пользователя нет username.\n"
                f"Попросите его установить username в настройках Telegram.",
                parse_mode="HTML"
            )
            return

    # Вариант 3: без аргументов и без ответа — показываем отправителя команды
    else:
        sender = update.message.from_user
        if sender and sender.username:
            user_tag = f"@{sender.username}"
            is_self = True
        else:
            await update.message.reply_text(
                "❌ У вас нет username в Telegram.\n"
                "Установите username в настройках Telegram.",
                parse_mode="HTML"
            )
            return

    if not user_tag:
        await update.message.reply_text(
            "❌ Не удалось определить пользователя.",
            parse_mode="HTML"
        )
        return

    # Загружаем данные из таблицы Ремесло
    player_data = get_player_realm_from_sheet(user_tag)

    if not player_data:
        if is_self:
            await update.message.reply_text(
                f"❌ Ваш профиль не найден в таблице Ремесло.\n\n"
                f"📝 Чтобы добавиться: ответьте на сообщение с навыками командой /update_me",
                parse_mode="HTML"
            )
        else:
            await update.message.reply_text(
                f"❌ Профиль {user_tag} не найден в таблице Ремесло.\n\n"
                f"Возможно, игрок ещё не обновил свои навыки через /update_me",
                parse_mode="HTML"
            )
        return

    response = format_realm_profile(player_data)
    await update.message.reply_text(response, parse_mode="HTML")

def get_player_realm_by_name(player_name):
    """Ищет игрока в таблице Ремесло по имени"""
    try:
        ws = get_realm_worksheet()
        if ws is None:
            return None

        all_data = ws.get_all_values()
        for row in all_data[1:]:  # Пропускаем заголовки
            if len(row) > 1 and row[1].lower() == player_name.lower():
                return {
                    'tag': row[0],
                    'name': row[1],
                    'clan': row[2],
                    'skills': {
                        'Крафтер': row[3] if len(row) > 3 else '',
                        'Рыбалка': row[4] if len(row) > 4 else '',
                        'Шахтёр': row[5] if len(row) > 5 else '',
                        'Охота': row[6] if len(row) > 6 else '',
                        'Кулинария': row[7] if len(row) > 7 else '',
                        'Алхимия': row[8] if len(row) > 8 else '',
                        'Плавильщик': row[9] if len(row) > 9 else '',
                        'Фермер': row[10] if len(row) > 10 else '',
                    },
                    'updated': row[11] if len(row) > 11 else ''
                }
        return None
    except Exception as e:
        print(f"Ошибка поиска игрока по имени {player_name}: {e}")
        return None

def get_player_realm_from_sheet(user_tag):
    """Получает данные игрока из таблицы Ремесло по тегу"""
    try:
        ws = get_realm_worksheet()
        if ws is None:
            print("❌ Не удалось подключиться к таблице Ремесло")
            return None

        # Ищем строку с тегом
        cell = ws.find(user_tag)
        if not cell:
            return None

        # Получаем всю строку
        row = ws.row_values(cell.row)

        return {
            'tag': row[0] if len(row) > 0 else '',
            'name': row[1] if len(row) > 1 else '',
            'clan': row[2] if len(row) > 2 else '',
            'skills': {
                'Крафтер': row[3] if len(row) > 3 else '',
                'Рыбалка': row[4] if len(row) > 4 else '',
                'Шахтёр': row[5] if len(row) > 5 else '',
                'Охота': row[6] if len(row) > 6 else '',
                'Кулинария': row[7] if len(row) > 7 else '',
                'Алхимия': row[8] if len(row) > 8 else '',
                'Плавильщик': row[9] if len(row) > 9 else '',
                'Фермер': row[10] if len(row) > 10 else '',
            },
            'updated': row[11] if len(row) > 11 else ''
        }
    except Exception as e:
        print(f"Ошибка получения данных игрока {user_tag}: {e}")
        return None


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

def format_specializations_for_profile(row, headers):
    """Форматирует специализации игрока для красивого вывода (как в /f, но для одного игрока)"""
    if not row or len(row) < 2:
        return "❌ Нет данных"

    # Первая колонка — это тег (@username), вторая — имя игрока
    tag = row[0].strip() if len(row) > 0 else "?"
    name = row[1].strip() if len(row) > 1 and row[1] else "Неизвестно"

    # Названия специализаций (заголовки)
    spec_names = headers[2:] if len(headers) > 2 else []

    response = f"🤟🏼 <b>{name}</b>\n"
    response += f"📱 {tag}\n\n"
    response += "<b>📋 Специализации:</b>\n"

    for i, spec in enumerate(spec_names):
        if i + 2 < len(row) and row[i + 2]:
            value = row[i + 2].strip()
            if value and value != '-':
                response += f"  • {spec}: <b>{value}</b>\n"

    return response


def get_specializations_data():
    """Загружает данные из таблицы специализаций (лист CW_SHEET_GID)"""
    try:
        url = f'https://docs.google.com/spreadsheets/d/e/2PACX-1vQhxznVeD5jD268Xb5x9crTJe0Di5Ra0OeSfqn_O_GA0plGpQHd8RFUg1GLlAnHgQx45XlklE1IVub9/pub?gid={CW_SHEET_GID}&output=csv'
        response = requests.get(url, timeout=15)
        response.raise_for_status()
        response.encoding = 'utf-8'

        csv_file = StringIO(response.text)
        reader = csv.reader(csv_file)
        data = list(reader)

        if not data:
            return None, None, "❌ Таблица пуста"

        # Заголовки — первая строка
        headers = data[0]

        # Данные — все остальные строки
        result = []
        for row in data[1:]:
            if any(cell and cell.strip() for cell in row):
                result.append(row)

        return result, headers, None
    except Exception as e:
        return None, None, f"❌ Ошибка: {e}"


# Словарь для преобразования уровней
LEVEL_MAP = {
    'Подмастерье': 'ПМ',
    'Ученик': 'У',
    'Грандмастер': 'ГМ',
    'Мастер': 'М',
    'Эксперт': 'Э'
}


def parse_skills_from_text(text):
    """Извлекает и преобразует навыки из текста сообщения"""
    skills = {}

    patterns = {
        'Крафтер': r'[⚒]*\s*[Нн]авык\s*[Кк]рафтер[а]?\s*:\s*([^\s▫️]+(?:\s+[^\s▫️]+)?)',
        'Рыбалка': r'[🎣]*\s*[Нн]авык\s*[Рр]ыбалк[иа]\s*:\s*([^\s▫️]+(?:\s+[^\s▫️]+)?)',
        'Шахтёр': r'[⛏]*\s*[Нн]авык\s*[Шш]ахт[её]р[а]?\s*:\s*([^\s▫️]+(?:\s+[^\s▫️]+)?)',
        'Охота': r'[🏹]*\s*[Нн]авык\s*[Оо]хот[ыа]\s*:\s*([^\s▫️]+(?:\s+[^\s▫️]+)?)',
        'Кулинария': r'[🥨]*\s*[Нн]авык\s*[Кк]улинари[яи]\s*:\s*([^\s▫️]+(?:\s+[^\s▫️]+)?)',
        'Алхимия': r'[🧪🌡]*\s*[Нн]авык\s*[Аа]лхими[яи]\s*:\s*([^\s▫️]+(?:\s+[^\s▫️]+)?)',
        'Плавильщик': r'[🪔]*\s*[Нн]авык\s*[Пп]лавильщик[а]?\s*:\s*([^\s▫️]+(?:\s+[^\s▫️]+)?)',
        'Фермер': r'[🌽]*\s*[Нн]авык\s*[Фф]ермер[а]?\s*:\s*([^\s▫️]+(?:\s+[^\s▫️]+)?)',
    }

    for skill, pattern in patterns.items():
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            level_text = match.group(1).strip()
            converted_level = convert_level(level_text)
            skills[skill] = converted_level

    return skills


def convert_level(level_text):
    """Преобразует текстовый уровень в короткий код"""
    # Примеры: "Подмастерье 2" -> "ПМ2", "Грандмастер 5" -> "ГМ5"
    for full_name, short_code in LEVEL_MAP.items():
        if full_name in level_text:
            # Извлекаем число
            numbers = re.findall(r'\d+', level_text)
            number = numbers[0] if numbers else ''
            return f"{short_code}{number}"

    # Если не нашли известный уровень, возвращаем как есть
    return level_text


def update_player_realm(user_tag, player_name, clan, skills, update_time):
    """Обновляет или добавляет запись о навыках игрока"""
    try:
        ws = get_realm_worksheet()
        if ws is None:
            print("❌ get_realm_worksheet вернул None")
            return False

        now = update_time.strftime('%Y-%m-%d %H:%M:%S')

        # Подготавливаем строку данных (ключи БЕЗ эмодзи)
        row_data = [
            user_tag,
            player_name,
            clan,
            skills.get('Крафтер', ''),
            skills.get('Рыбалка', ''),
            skills.get('Шахтёр', ''),
            skills.get('Охота', ''),
            skills.get('Кулинария', ''),
            skills.get('Алхимия', ''),
            skills.get('Плавильщик', ''),
            skills.get('Фермер', ''),
            now
        ]

        # Ищем, есть ли уже такой игрок по тегу
        try:
            cell = ws.find(user_tag)
        except:
            cell = None

        if cell:
            # Обновляем существующую строку
            row_num = cell.row
            update_range = f'A{row_num}:L{row_num}'
            ws.update(range_name=update_range, values=[row_data])
            print(f"✅ Обновлена строка {row_num} для {user_tag}")
        else:
            # Добавляем новую строку
            ws.append_row(row_data)
            print(f"✅ Добавлена новая строка для {user_tag}")

        return True
    except Exception as e:
        print(f"❌ Ошибка записи навыков: {e}")
        import traceback
        traceback.print_exc()
        return False


async def update_realm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Шаг 1: получение навыков, запрос ника"""

    # Если команда не в ответ на сообщение — показываем инструкцию
    if not update.message.reply_to_message:
        await update.message.reply_text(
            "❌ <b>Как использовать /update_me</b>\n\n"
            "1️⃣ Отправьте в чат сообщение со своими навыками (скопируйте из игры)\n"
            "2️⃣ Нажмите «ответить» на это сообщение\n"
            "3️⃣ Напишите /update_me\n\n"
            "📝 <b>Пример сообщения с навыками:</b>\n"
            "⚒ Навык Крафтера: Подмастерье 2\n"
            "🎣 Навык Рыбалки: Подмастерье 1\n"
            "...",
            parse_mode="HTML"
        )
        return

    skills_text = update.message.reply_to_message.text
    skills = parse_skills_from_text(skills_text)

    if not skills:
        await update.message.reply_text(
            "❌ Не удалось распознать навыки.\n\n"
            "Убедитесь, что сообщение содержит строки вида:\n"
            "«Навык Крафтера: Подмастерье 2»",
            parse_mode="HTML"
        )
        return

    user = update.effective_user
    user_tag = f"@{user.username}" if user.username else None

    if not user_tag:
        await update.message.reply_text(
            "❌ У вас нет username в Telegram.\n\n"
            "Установите username в настройках Telegram.",
            parse_mode="HTML"
        )
        return

    # Сохраняем сессию
    user_sessions[user.id] = {
        'skills': skills,
        'user_tag': user_tag,
        'telegram_name': user.first_name,
        'skills_text': skills_text
    }

    # Шаг 2: просим ввести игровой ник
    await update.message.reply_text(
        "🤟🏼 <b>Введите ваш игровой ник</b>\n\n"
        "Например: Jango, Crazyrain34, Giz\n\n"
        "Просто напишите его в ответ на это сообщение.",
        parse_mode="HTML"
    )


async def handle_nickname(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Шаг 2: получаем игровой ник от пользователя"""

    # Игнорируем команды
    if update.message.text and update.message.text.startswith('/'):
        return

    user_id = update.effective_user.id

    if user_id not in user_sessions:
        # Не показываем ошибку, если сессии нет — просто игнорируем
        return

    nickname = update.message.text.strip()
    if not nickname:
        await update.message.reply_text("❌ Ник не может быть пустым. Попробуйте ещё раз.")
        return

    # Сохраняем ник
    user_sessions[user_id]['nickname'] = nickname

    # Шаг 3: показываем выбор клана
    keyboard = [
        [InlineKeyboardButton("🤟 Анархия", callback_data="clan_anarchy")],
        [InlineKeyboardButton("🤟🏾️ Наследие Анархии", callback_data="clan_legacy")],
        [InlineKeyboardButton("🤟🏼 Крылья Анархии", callback_data="clan_wings")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        "🏛️ <b>Выберите ваш клан</b>",
        parse_mode="HTML",
        reply_markup=reply_markup
    )


async def clan_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Шаг 3: получаем выбор клана и сохраняем всё в таблицу"""
    query = update.callback_query
    await query.answer()

    user_id = update.effective_user.id

    if user_id not in user_sessions:
        await query.edit_message_text(
            "❌ Сессия истекла или данные уже сохранены.\n\n"
            "Если данные не сохранились, начните заново: /update_me"
        )
        return

    clan_map = {
        'clan_anarchy': 'Анархия',
        'clan_legacy': 'Наследие Анархии',
        'clan_wings': 'Крылья Анархии'
    }
    clan = clan_map.get(query.data, 'Анархия')

    data = user_sessions.pop(user_id)
    nickname = data['nickname']
    skills = data['skills']
    user_tag = data['user_tag']

    # Сохраняем в таблицу
    moscow_tz = pytz.timezone('Europe/Moscow')
    now_moscow = datetime.now(moscow_tz)
    success = update_player_realm(user_tag, nickname, clan, skills, now_moscow)

    if success:
        response = f"✅ <b>Навыки сохранены!</b>\n\n"
        response += f"🎮 <b>Игровой ник:</b> {nickname}\n"
        response += f"🏛️ <b>Клан:</b> {clan}\n\n"
        response += f"⚒️ <b>Крафтер:</b> {skills.get('Крафтер', '—')}\n"
        response += f"🎣 <b>Рыбалка:</b> {skills.get('Рыбалка', '—')}\n"
        response += f"⛏️ <b>Шахтёр:</b> {skills.get('Шахтёр', '—')}\n"
        response += f"🏹 <b>Охота:</b> {skills.get('Охота', '—')}\n"
        response += f"🥨 <b>Кулинария:</b> {skills.get('Кулинария', '—')}\n"
        response += f"🧪 <b>Алхимия:</b> {skills.get('Алхимия', '—')}\n"
        response += f"🪔 <b>Плавильщик:</b> {skills.get('Плавильщик', '—')}\n"
        response += f"🌽 <b>Фермер:</b> {skills.get('Фермер', '—')}\n"
        response += f"\n📅 <b>Дата:</b> {now_moscow.strftime('%Y-%m-%d %H:%M:%S')}"

        await query.edit_message_text(response, parse_mode="HTML")
    else:
        # Если ошибка, возвращаем сессию обратно
        user_sessions[user_id] = data
        await query.edit_message_text(
            "❌ Ошибка сохранения. Попробуйте ещё раз /update_me"
        )

def get_realm_worksheet():
    """Подключается к таблице с навыками"""
    try:
        scope = ['https://www.googleapis.com/auth/spreadsheets',
                 'https://www.googleapis.com/auth/drive']
        creds = Credentials.from_service_account_file(CREDENTIALS_FILE, scopes=scope)
        client = gspread.authorize(creds)
        sheet = client.open_by_key(REALM_SHEET_ID).worksheet(REALM_SHEET_NAME)
        return sheet
    except Exception as e:
        print(f"Ошибка подключения к таблице навыков: {e}")
        return None

async def chat_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показывает ID текущего чата"""
    chat = update.effective_chat
    await update.message.reply_text(
        f"📋 <b>Информация о чате</b>\n\n"
        f"🆔 ID чата: <code>{chat.id}</code>\n"
        f"📝 Название: {chat.title or 'Личный чат'}\n"
        f"📌 Тип: {chat.type}",
        parse_mode="HTML"
    )

# Хранилище сессий CW
cw_sessions = {}

async def start_cw(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    # Проверка: уже в режиме
    if user_id in cw_sessions:
        await update.message.reply_text(
            "❌ Ты уже в режиме советника.\n"
            "Используй /stop_cw, чтобы выйти."
        )
        return

    # Проверка: указан ли ник
    if not context.args:
        await update.message.reply_text(
            "❌ Укажи свой игровой ник.\n"
            "Пример: /start_cw Jango"
        )
        return

    player_nick = context.args[0].strip()

    # Создаём сессию
    cw_sessions[user_id] = {
        'player_nick': player_nick,
        'last_turn': 0,
        'logs': [],
        'stats': {},
        'started_at': datetime.now(),
    }

    await update.message.reply_text(
        f"✅ Режим советника активирован!\n"
        f"Игрок: {player_nick}\n\n"
        f"Присылай логи боя, содержащие слово «Ход».\n"
        f"Я буду анализировать их по порядку."
    )


async def stop_cw(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    if user_id not in cw_sessions:
        await update.message.reply_text(
            "❌ Ты не в режиме советника.\n"
            "Используй /start_cw <ник>, чтобы начать."
        )
        return

    # Удаляем сессию
    del cw_sessions[user_id]

    await update.message.reply_text(
        "❌ Режим советника завершён.\n"
        "До новых боёв!"
    )

def is_log(text):
    """Проверяет, похоже ли сообщение на лог боя"""
    return "Ход" in text

def parse_turn(text):
    match = re.search(r'Ход\s*(\d+)', text)
    if match:
        return int(match.group(1))
    return None

def parse_team(line):
    match = re.search(r'([^:]+)\s*💔\s*\((\d+)/(\d+)\)', line)
    if match:
        return {
            'name': match.group(1).strip(),
            'hp': int(match.group(2)),
            'max_hp': int(match.group(3)),
        }
    return None

def parse_player(line):
    # Пример: "1. 💝🤟🏾 🧝‍♂️️kiot 🔸33 ❤️(5699/5699)"
    match = re.search(
        r'^\d+\.\s*([^\s]+)\s+([^\s]+?)([А-Яа-яA-Za-z0-9_]+)\s*🔸(\d+)\s*❤️\((\d+)/(\d+)\)',
        line
    )
    if match:
        return {
            'emoji_prefix': match.group(1),   # 💝🤟🏾
            'role_emoji': match.group(2),     # 🧝‍♂️️
            'name': match.group(3),           # kiot
            'level': int(match.group(4)),     # 33
            'hp': int(match.group(5)),        # 5699
            'max_hp': int(match.group(6)),    # 5699
        }
    return None

def parse_next_fight(text):
    fights = []
    in_next = False
    for line in text.split('\n'):
        if 'Следующий ход:' in line:
            in_next = True
            continue
        if in_next and line.strip():
            # Сохраняем всю строку целиком
            fights.append(line.strip())
        if in_next and not line.strip():
            break
    return fights

def get_enemy_from_next_fight(fights, player_nick):
    """Возвращает полную строку соперника из первой пары, где есть player_nick"""
    for line in fights:
        parts = line.split(' vs ')
        if len(parts) == 2:
            player1 = parts[0].strip()
            player2 = parts[1].strip()
            if player_nick in player1:
                return player2
            elif player_nick in player2:
                return player1
    return None

def parse_player_actions(text, enemy_name):
    result = {
        'combos': [],
        'hits': [],       # список словарей: {'part': 'грудь', 'block': False/True}
        'received': [],   # список словарей: {'part': 'грудь', 'block': False/True}
        'blocks': [],     # пока не используем, можно убрать
    }

    lines = text.split('\n')
    for line in lines:
        # 1. Приёмы
        if enemy_name in line and 'использует комбинацию' in line:
            result['combos'].append(line.strip())
            continue

        # 2. Удары соперника (ОН бьёт)
        if enemy_name in line and 'бьет в' in line:
            if 'по' in line:
                parts = line.split('по')
                if len(parts) > 0 and enemy_name in parts[0]:
                    match = re.search(r'бьет в ([^,\.]+?)(?:\s|,|\.|по)', line)
                    if match:
                        # Проверяем, был ли блок
                        is_block = 'попадает в блок' in line or 'блок' in line
                        result['hits'].append({
                            'part': match.group(1).strip(),
                            'block': is_block
                        })
                        continue
            else:
                match = re.search(r'бьет в ([^,\.]+?)(?:\s|,|\.|по)', line)
                if match:
                    is_block = 'попадает в блок' in line or 'блок' in line
                    result['hits'].append({
                        'part': match.group(1).strip(),
                        'block': is_block
                    })
                    continue

        # 3. Полученные удары (в НЕГО бьют)
        if enemy_name in line and 'по' in line and 'бьет в' in line:
            parts = line.split('по')
            if len(parts) > 1 and enemy_name in parts[1]:
                match = re.search(r'бьет в ([^,\.]+?)(?:\s|,|\.|по)', line)
                if match:
                    # Проверяем, был ли блок
                    is_block = 'попадает в блок' in line or 'блок' in line
                    result['received'].append({
                        'part': match.group(1).strip(),
                        'block': is_block
                    })
                continue

    return result

def extract_player_name(line):
    """Извлекает чистое имя игрока из полной строки"""
    match = re.search(r'([А-Яа-яA-Za-z0-9_]+)\s*🔸', line)
    if match:
        return match.group(1)
    return None

async def test_parse(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Проверяем, есть ли ответ на сообщение
    if not update.message.reply_to_message:
        await update.message.reply_text(
            "❌ Ответь на сообщение с логом боя командой /test_parse"
        )
        return

    text = update.message.reply_to_message.text
    if not text:
        await update.message.reply_text("❌ В сообщении нет текста.")
        return

    # Получаем ник из сессии
    user_id = update.effective_user.id
    session = cw_sessions.get(user_id)
    if not session:
        await update.message.reply_text(
            "❌ Ты не в режиме советника. Используй /start_cw <ник>"
        )
        return

    player_nick = session['player_nick']

    # Парсим номер хода
    turn = parse_turn(text)
    msg = f"🔍 Номер хода: {turn}\n\n"

    # Парсим команды
    for line in text.split('\n'):
        if 'Нападающие' in line or 'Защитники' in line:
            team = parse_team(line)
            if team:
                msg += f"📊 {team['name']}: ❤️ {team['hp']}/{team['max_hp']}\n"

    if turn is None and not any('Нападающие' in line or 'Защитники' in line for line in text.split('\n')):
        msg += "\n⚠️ Не удалось распознать номер хода или команды."

    # Парсинг игроков
    players = []
    for line in text.split('\n'):
        player = parse_player(line)
        if player:
            players.append(player)

    if players:
        msg += "\n👥 Игроки:\n"
        for p in players[:4]:
            msg += f"  {p['emoji_prefix']} {p['role_emoji']}{p['name']} (ур. {p['level']}) ❤️ {p['hp']}/{p['max_hp']}\n"

    fights = parse_next_fight(text)
    if fights:
        enemy_line = get_enemy_from_next_fight(fights, player_nick)
        if enemy_line:
            # Извлекаем чистое имя соперника
            enemy_name = extract_player_name(enemy_line)
            msg += f"\n⚔️ Следующий ход соперника: {enemy_line}\n"

    # Парсинг деталей соперника
    actions = parse_player_actions(text, enemy_name)
    if actions:
        if actions['combos']:
            msg += "\n📋 Использованные приёмы:\n"
            for combo in actions['combos']:
                msg += f"  {combo}\n"
        # Удары соперника (ОН бьёт)
        if actions['hits']:
            msg += "\n🎯 Удары соперника:\n"
            for i, hit in enumerate(actions['hits'], 1):
                icon = "🛡" if hit['block'] else "🗡"
                msg += f"  {i}) {hit['part']} ({icon})\n"

        # Полученные удары (в НЕГО бьют)
        if actions['received']:
            msg += "\n🛡️ Полученные удары:\n"
            for i, rec in enumerate(actions['received'], 1):
                icon = "🛡" if rec['block'] else "🗡"
                msg += f"  {i}) {rec['part']} ({icon})\n"

    await update.message.reply_text(msg)



async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показывает список всех команд бота"""
    help_text = """
📖 <b>Помощь — список команд бота</b>

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

📊 <b>Основная таблица (актуальная таблица)</b>
  • <code>/get_data</code> — показать данные из таблицы
  • <code>/stats</code> — статистика (очки, монеты, итог)
  • <code>/find &lt;текст&gt;</code> — поиск по таблице
    <i>Пример: /find pa3ym</i>

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

🛠️ <b>Специализации игроков</b>
  • <code>/f &lt;специализация&gt;</code> — поиск с группировкой

  <b>Доступные специализации и синонимы:</b>
  • крафтер / крафт / <b>к</b>
  • рыбалка / рыба / <b>р</b>
  • шахтёр / шахта / <b>ш</b>
  • охота / охотник / <b>о</b>
  • кулинария / еда / кухня / <b>кул</b>
  • алхимия / алхим / алх / <b>а</b>
  • плавильщик / плавка / <b>пл</b>
  • фермер / ферма / <b>ф</b>

  <i>Примеры: /f а, /f алхимия, /f еда, /f ф</i>

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

ℹ️ <b>Другие команды</b>
  • <code>/start</code> — приветственное сообщение
  • <code>/help</code> — это сообщение

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

💡 Данные берутся из публичной Google Таблицы.
    Обновления происходят автоматически.
"""
    await update.message.reply_text(help_text, parse_mode="HTML")


# ==================== ЗАПУСК БОТА ====================

def main():
    print("🟢 Запуск бота...")
    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    # Основные команды
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))

    # Команды для основной таблицы
    app.add_handler(CommandHandler("get_data", get_data))
    app.add_handler(CommandHandler("stats", stats))
    app.add_handler(CommandHandler("find", find))

    # Команды для специализаций
    app.add_handler(CommandHandler("f", spec_search))

    # Инлайн-обработчик
    app.add_handler(InlineQueryHandler(inline_query))

    app.add_handler(CommandHandler("prof", get_profile))

    # Новая команда для обновления навыков
    app.add_handler(CommandHandler("update_me", update_realm))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_nickname))

    # Callback обработчики: сначала специфичный, потом общий
    app.add_handler(CallbackQueryHandler(clan_callback, pattern="^clan_"))
    app.add_handler(CallbackQueryHandler(button_callback))  # без паттерна - обрабатывает всё остальное

    app.add_handler(CommandHandler("chat_id", chat_id))

    app.add_handler(CommandHandler("start_cw", start_cw))
    app.add_handler(CommandHandler("stop_cw", stop_cw))
    app.add_handler(CommandHandler("test_parse", test_parse))

    print("✅ Бот запущен и готов к работе!")
    app.run_polling()


if __name__ == '__main__':
    # Запускаем Flask в отдельном потоке для healthcheck
    threading.Thread(target=run_flask, daemon=True).start()
    # Запускаем бота
    main()
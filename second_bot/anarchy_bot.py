import os
import csv
import re
import requests
from datetime import datetime
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
import re
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
from utils.table_search import get_combined_table_data
from utils.spec_table import show_specializations
from utils.realm_skills import parse_skills_from_text
from utils.realm_update import user_sessions, update_realm, handle_nickname, clan_callback
from utils.realm_sheet import (
    get_player_realm_by_name,
    get_player_realm_from_sheet,
    update_player_realm,
    get_realm_worksheet,
)

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

    combined_data = get_combined_table_data(
        MAIN_SHEET_GID, SECOND_SHEET_GID, THIRD_SHEET_GID
    )

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
    await show_specializations(update, context, CW_SHEET_GID)


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
        levels[level].append({
            'name': player['name'],
            'tag': player['tag']
        })

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
        players = sorted(levels[level], key=lambda p: p['name'].lower())

        # Формируем список с гиперссылками
        links = []
        for p in players:
            name = p['name']
            tag = p['tag']  # это @username
            if tag and tag.startswith('@'):
                username = tag[1:]  # убираем @
                links.append(f'<a href="https://t.me/{username}">{name}</a>')
            else:
                links.append(name)

        response += f"<b>{level}</b> ({len(players)}): {', '.join(links)}\n"

        if len(response) > 4000:
            await update.message.reply_text(response, parse_mode="HTML", disable_web_page_preview=True)
            response = ""

    if response:
        await update.message.reply_text(response, parse_mode="HTML", disable_web_page_preview=True)

@chat_restricted
async def get_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /get — открывает inline-поиск по карточкам крафта."""
    await update.message.reply_text(
        "🔎 <b>Поиск предмета</b>\n\nНажми кнопку и начни вводить название.",
        parse_mode="HTML",
        reply_markup=get_search_keyboard()
    )







from utils.inline_search import inline_query

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


async def cmd_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показывает команды для игрока, на чьё сообщение отвечаем"""

    if not update.message.reply_to_message:
        await update.message.reply_text(
            "❌ Ответьте на сообщение игрока командой /cmd",
            parse_mode="HTML"
        )
        return

    user = update.message.reply_to_message.from_user
    user_tag = f"@{user.username}" if user.username else None

    if not user_tag:
        await update.message.reply_text(
            "❌ У пользователя нет username в Telegram.",
            parse_mode="HTML"
        )
        return

    player_data = get_player_realm_from_sheet(user_tag)

    if not player_data:
        await update.message.reply_text(
            f"❌ Игрок с тегом {user_tag} не найден в таблице Ремесло.",
            parse_mode="HTML"
        )
        return

    player_name = player_data['name']

    # Формируем ответ с командами в HTML-блоках
    response = f"<b>Команды для игрока в Epsilion {player_name}:</b>\n"
    response += f"<code>/trade {player_name}</code>\n"
    response += f"<code>/getplayer {player_name}</code>\n"
    response += f"<code>/use_k {player_name}</code>\n\n"
    response += f"<b>Команды для игрока в Анархии {player_name}:</b>\n"
    response += f"<code>/find {player_name}</code>\n"
    response += f"<code>/prof {player_name}</code>\n"
    await update.message.reply_text(response, parse_mode="HTML")


@chat_restricted
async def trade_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показывает команду /trade для игрока, на чьё сообщение отвечаем"""

    # Игнорируем, если после /trade есть текст (аргументы)
    if context.args:
        return

    reply = update.message.reply_to_message

    # Игнорируем, если нет reply, нет автора, или это сервисное сообщение топика
    if not reply or not reply.from_user or reply.forum_topic_created:
        return

    user = reply.from_user
    user_tag = f"@{user.username}" if user.username else None

    if not user_tag:
        await update.message.reply_text(
            "❌ У пользователя нет username в Telegram.",
            parse_mode="HTML"
        )
        return

    player_data = get_player_realm_from_sheet(user_tag)

    if not player_data:
        await update.message.reply_text(
            f"❌ Игрок с тегом {user_tag} не найден в таблице Ремесло.",
            parse_mode="HTML"
        )
        return

    player_name = player_data['name']

    response = f"<code>/trade {player_name}</code>"

    await update.message.reply_text(response, parse_mode="HTML")



# ==================== ЗАТОЧКА ЭКИПИРОВКИ (/enchant) ====================

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



@chat_restricted
async def craft_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /craft — меню выбора раздела"""
    if not craft_base.get('grades'):
        await update.message.reply_text(
            "❌ База крафта не загружена.",
            parse_mode="HTML"
        )
        return

    keyboard = [
        [
            InlineKeyboardButton(f"🎒 Экипировка ({count_all_equipment(craft_base)})", callback_data="craft_section:equip"),
            InlineKeyboardButton(f"⚒️ Инструменты ({count_all_instruments(craft_base)})", callback_data="craft_section:instr"),
        ],
        [
            InlineKeyboardButton(f"🥨 Кулинария ({count_all_cooking(craft_base)})", callback_data="craft_section:cook"),
            InlineKeyboardButton(f"🧪 Алхимия ({count_all_alchemy(craft_base)})", callback_data="craft_section:alchemy"),
        ]
    ]
    await update.message.reply_text(
        "⚒️ <b>Крафт — выбери раздел:</b>",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def craft_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обёртка для callback-кнопок /craft."""
    await handle_craft_callback(update, context, craft_base)


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

🛠️ <b>Специализации игроков (таблица «Ремесло»)</b>
  • <code>/f &lt;специализация&gt; [уровень]</code> — поиск игроков
    <i>Примеры: /f а, /f алхимия, /f крафтер ГМ4</i>
  • <code>/prof</code> — профиль игрока
    <i>Без аргументов — свой профиль</i>
    <i>Ответом на сообщение — профиль автора</i>
    <i>С аргументом — /prof @username или /prof Ник</i>
  • <code>/update_me</code> — обновить свои навыки
    <i>Ответом на сообщение с навыками из игры</i>

  <b>Доступные специализации и синонимы:</b>
  • крафтер / крафт / <b>к</b>
  • рыбалка / рыба / <b>р</b>
  • шахтёр / шахта / <b>ш</b>
  • охота / охотник / <b>о</b>
  • кулинария / еда / кухня / <b>кул</b>
  • алхимия / алхим / алх / <b>а</b>
  • плавильщик / плавка / <b>пл</b>
  • фермер / ферма / <b>ф</b>

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

⚔️ <b>Команды для игры</b>
  • <code>/trade</code> — команда /trade для игрока
    <i>Ответом на сообщение игрока</i>
  • <code>/cmd</code> — все игровые команды для игрока
    <i>Ответом на сообщение игрока</i>

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

ℹ️ <b>Другие команды</b>
  • <code>/start</code> — приветственное сообщение
  • <code>/help</code> — это сообщение
  • <code>/chat_id</code> — ID текущего чата

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

💡 Данные берутся из публичной Google Таблицы.
    Обновления происходят автоматически.
"""
    await update.message.reply_text(help_text, parse_mode="HTML")


# ==================== ЗАПУСК БОТА ====================


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
    app.add_handler(CallbackQueryHandler(craft_callback, pattern="^craft_"))  # ← новый
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
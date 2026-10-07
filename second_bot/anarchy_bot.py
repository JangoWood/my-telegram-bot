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
import threading
from telegram import InlineQueryResultArticle, InputTextMessageContent
from telegram.ext import InlineQueryHandler
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CallbackQueryHandler
import gspread
from google.oauth2.service_account import Credentials
import pytz
from telegram.ext import MessageHandler, filters
from utils.realm_profile import format_realm_profile, format_specializations_for_profile
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
# Хранилище сессий для /help_cw
help_cw_sessions = {}

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
    build_alchemy_category_keyboard, build_classes_keyboard, build_class_items_keyboard
,
    build_instrument_items_keyboard, build_cooking_items_keyboard
)
from utils.craft_calculator import build_calculator_text, build_calculator_buttons
from utils.callback_handlers import handle_button_callback
from utils.table_data import get_table_data, get_table_data_by_gid, get_table_data_by_gid_with_fallback
from utils.table_search import get_combined_table_data
from utils.spec_table import show_specializations

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







@chat_restricted
async def inline_query(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обрабатывает инлайн-запросы (@bot_name текст) — сразу показываем результат"""

    raw_query = update.inline_query.query.strip()
    query = raw_query.lower()

    # /get использует тот же inline-хендлер, но полностью изолирован префиксом "get ".
    if query == "get" or query.startswith("get "):
        craft_query = raw_query[3:].strip().lower()
        items = get_all_craft_search_items(craft_base)

        if not craft_query:
            results = [InlineQueryResultArticle(
                id="get_help",
                title="🔍 Введите название предмета",
                description=f"Поиск по {len(items)} карточкам крафта",
                input_message_content=InputTextMessageContent(
                    "🔎 Начни вводить название предмета для поиска."
                )
            )]
            await update.inline_query.answer(results, cache_time=0, is_personal=True)
            return

        found = []
        for index, (item, section) in enumerate(items):
            title = item.get('title', '')
            if craft_query in title.lower():
                context.user_data.setdefault('craft_calc_back', {})[str(item.get('id'))] = '__get__'
                found.append(InlineQueryResultArticle(
                    id=f"craft_get_{index}",
                    title=title[:64],
                    description=section[:128],
                    input_message_content=InputTextMessageContent(
                        build_get_card_text(item),
                        parse_mode="HTML"
                    ),
                    reply_markup=build_calculator_buttons(item.get('id'), 1)
                ))
                if len(found) >= 20:
                    break

        if not found:
            found = [InlineQueryResultArticle(
                id="craft_get_not_found",
                title=f"❌ Не найдено: {craft_query}",
                description="Попробуйте другое название",
                input_message_content=InputTextMessageContent(
                    f"❌ Предмет «{craft_query}» не найден."
                )
            )]

        await update.inline_query.answer(found, cache_time=0, is_personal=True)
        return

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
        'enemy_stats_by_name': {},  # ← теперь словарь по имени
        'enemy_hits_by_name': {},  # ← теперь словарь по имени
        'enemy_received_by_name': {},  # ← теперь словарь по имени
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
    match = re.search(
        r'^\d+\.\s*([^\s]+)\s+([^\s]+?)([А-Яа-яA-Za-z0-9_]+)\s*🔸(\d+)\s*❤️\((\d+)/(\d+)\)',
        line
    )
    if match:
        return {
            'emoji_prefix': match.group(1),
            'role_emoji': match.group(2),
            'name': match.group(3),
            'full_id': f"{match.group(1)} {match.group(2)}{match.group(3)} 🔸{match.group(4)}",
            'level': int(match.group(4)),
            'hp': int(match.group(5)),
            'max_hp': int(match.group(6)),
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
    for line in fights:
        # Убираем номер в начале (например, "1. " или "2. ")
        clean_line = re.sub(r'^\d+\.\s*', '', line)
        parts = clean_line.split(' vs ')
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
        'skills': [],
        'hits': [],
        'received': [],
        'missed_turns': [],
    }

    lines = text.split('\n')
    for line in lines:
        if enemy_name not in line:
            continue

        # 1. Пропуск хода
        if 'пропускает удар' in line:
            result['missed_turns'].append(line.strip())
            continue

        # 2. Приёмы (сокращённый вид)
        if 'использует комбинацию' in line and enemy_name in line:
            # Извлекаем название приёма после "комбинацию"
            match = re.search(r'использует комбинацию\s+([^(]+)', line)
            if match:
                combo_name = match.group(1).strip()
            else:
                combo_name = line.strip()

            usage = ""
            for next_line in lines[lines.index(line) + 1:]:
                if 'Кол-во использований:' in next_line:
                    usage_match = re.search(r'Кол-во использований:\s*(\d+/\d+)', next_line)
                    if usage_match:
                        usage = usage_match.group(1)
                    break
                if not next_line.strip() or 'использует комбинацию' in next_line or 'бьет' in next_line:
                    break

            # Сохраняем полную строку для фильтрации
            result['combos'].append({
                'name': combo_name,
                'usage': usage,
                'full_line': line.strip()  # сохраняем для проверки принадлежности
            })
            continue

        # 3. Навыки (с 💫) — с подсчётом использований
        if '💫' in line and enemy_name in line:
            # Извлекаем название навыка после 💫
            match = re.search(r'💫\s*([^,\n]+)', line)
            if match:
                skill_name = match.group(1).strip()
            else:
                skill_name = line.strip()

            result['skills'].append({
                'name': skill_name,
                'full_line': line.strip()
            })
            continue
        # 4. Удары и полученные удары
        if 'бьет' in line:
            parts = line.split('бьет')
            if len(parts) < 2:
                continue

            left = parts[0].strip()   # кто бьёт
            right = parts[1].strip()  # кого бьют + часть тела

            # Определяем часть тела по ключевым словам
            part = "неизвестно"
            body_parts = ['голову', 'голова', 'грудь', 'живот', 'пояс', 'ноги']
            for bp in body_parts:
                if bp in right:
                    part = bp
                    break

            # Определяем результат
            is_block = 'попадает в блок' in line or 'блок' in line or 'Противник заблокировал' in line
            is_crit = 'критическим ударом' in line
            is_evade = 'увернулся' in line
            is_counter = 'контрудар' in line

            # Если соперник в левой части — он бьёт
            if enemy_name in left:
                result['hits'].append({
                    'part': part,
                    'block': is_block,
                    'crit': is_crit,
                    'evade': is_evade,
                    'counter': is_counter,
                })

            # Если соперник в правой части — по нему бьют
            if enemy_name in right and not is_counter:
                result['received'].append({
                    'part': part,
                    'block': is_block,
                    'crit': is_crit,
                    'evade': is_evade,
                    'counter': is_counter,
                })

    return result

def extract_player_name(line):
    """Извлекает чистое имя игрока из полной строки"""
    match = re.search(r'([А-Яа-яA-Za-z0-9_]+)\s*🔸', line)
    if match:
        return match.group(1)
    return None

def parse_enemy_stats(text, enemy_name):
    """
    Собирает статистику для соперника за текущий ход:
    🗡 — попадания (удары не в блок)
    🛡 — блоки
    🥊 — критические удары
    ⚡️ — уклонения
    🤺 — контрудары
    🌬 — промахи / попадания в блок
    """
    stats = {
        'swords': 0,
        'shields': 0,
        'crits': 0,
        'evades': 0,
        'counters': 0,
        'misses': 0,
    }

    lines = text.split('\n')
    for line in lines:
        if enemy_name not in line:
            continue

        # 🗡 Попадания (только когда соперник сам бьёт)
        if 'бьет' in line and 'наносит' in line:
            # Проверяем, что enemy_name находится до того, как появляется "бьет"
            # или enemy_name является субъектом действия
            parts = line.split('бьет')
            if len(parts) > 0 and enemy_name in parts[0]:
                # Это удар соперника
                if 'блок' not in line and 'попадает в блок' not in line:
                    stats['swords'] += 1

        # 🛡 Блоки (соперник ставит блок)
        if 'попадает в блок' in line and 'бьет' in line:
            stats['shields'] += 1

        # 🥊 Критические удары
        if 'критическим ударом' in line:
            stats['crits'] += 1

        # ⚡️ Уклонения
        if 'увернулся' in line:
            stats['evades'] += 1

        # 🤺 Контрудары
        if 'контрудар' in line:
            stats['counters'] += 1

        # 🌬 Промахи / блоки (когда удар соперника попал в блок)
        if 'бьет' in line and ('блок' in line or 'попадает в блок' in line):
            parts = line.split('бьет')
            if len(parts) > 0 and enemy_name in parts[0]:
                stats['misses'] += 1

    return stats

def subtract_combo_resources(stats, resources):
    """Вычитает ресурсы из статистики игрока"""
    if not resources:
        return

    # Ищем 🗡N, 🛡N, 🥊N, ⚡️N, 🤺N, 🌬N
    swords = re.search(r'🗡(\d+)', resources)
    shields = re.search(r'🛡(\d+)', resources)
    crits = re.search(r'🥊(\d+)', resources)
    evades = re.search(r'⚡️(\d+)', resources)
    counters = re.search(r'🤺(\d+)', resources)
    misses = re.search(r'🌬(\d+)', resources)

    if swords:
        stats['swords'] -= int(swords.group(1))
    if shields:
        stats['shields'] -= int(shields.group(1))
    if crits:
        stats['crits'] -= int(crits.group(1))
    if evades:
        stats['evades'] -= int(evades.group(1))
    if counters:
        stats['counters'] -= int(counters.group(1))
    if misses:
        stats['misses'] -= int(misses.group(1))

    # Не даём уйти в минус
    for key in stats:
        if stats[key] < 0:
            stats[key] = 0

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

    # Парсим защитников и нападающих
    defenders = []
    attackers = []
    current_team = None

    for line in text.split('\n'):
        if 'Следующий ход:' in line:
            break
        if 'Защитники' in line:
            current_team = 'defenders'
            continue
        if 'Нападающие' in line:
            current_team = 'attackers'
            continue
        if current_team and '❤️' in line and '🔸' in line:
            player = parse_player(line)
            if player:
                if current_team == 'defenders':
                    defenders.append(player)
                else:
                    attackers.append(player)

    # === НАХОДИМ FULL_ID НАШЕГО ИГРОКА ===
    player_full_id = player_nick  # запасной вариант
    all_players = defenders + attackers
    for player in all_players:
        if player['name'] == player_nick:
            player_full_id = player['full_id']
            break

    # Вывод защитников
    if defenders:
        msg += "\n🛡️ Защитники:\n"
        for p in defenders:
            hp_percent = round(p['hp'] / p['max_hp'] * 100)
            msg += f"  {p['emoji_prefix']} {p['role_emoji']}{p['name']} 🔸{p['level']} ❤️({p['hp']}/{p['max_hp']}) {hp_percent}%\n"
            stats = session['enemy_stats_by_name'].get(p['name'], {})
            if stats:
                msg += f"<blockquote>🗡{stats.get('swords', 0)}🛡{stats.get('shields', 0)}🥊{stats.get('crits', 0)}⚡️{stats.get('evades', 0)}🤺{stats.get('counters', 0)}🌬{stats.get('misses', 0)}</blockquote>\n"

    # Вывод нападающих
    if attackers:
        msg += "\n⚔️ Нападающие:\n"
        for p in attackers:
            hp_percent = round(p['hp'] / p['max_hp'] * 100)
            msg += f"  {p['emoji_prefix']} {p['role_emoji']}{p['name']} 🔸{p['level']} ❤️({p['hp']}/{p['max_hp']}) {hp_percent}%\n"
            stats = session['enemy_stats_by_name'].get(p['name'], {})
            if stats:
                msg += f"<blockquote>🗡{stats.get('swords', 0)}🛡{stats.get('shields', 0)}🥊{stats.get('crits', 0)}⚡️{stats.get('evades', 0)}🤺{stats.get('counters', 0)}🌬{stats.get('misses', 0)}</blockquote>\n"

    # Следующий ход
    fights = parse_next_fight(text)
    if fights:
        enemy_line = get_enemy_from_next_fight(fights, player_nick)
        if enemy_line:
            enemy_name = extract_player_name(enemy_line)
            msg += f"\n⚔️ Следующий ход соперника: {enemy_line}\n"

            # === ДИАГНОСТИКА ДЛЯ ПОЛУЧЕННЫХ УДАРОВ ===
            msg += "\n🔍 Диагностика полученных ударов:\n"
            for line in text.split('\n'):
                if 'бьет' in line and enemy_name in line:
                    msg += f"  Строка: {line[:120]}\n"
                    if 'по' in line:
                        parts = line.split('по')
                        msg += f"    'по' есть в строке\n"
                        msg += f"    enemy_name в parts[0]: {enemy_name in parts[0]}\n"
                        msg += f"    enemy_name в parts[1]: {enemy_name in parts[1] if len(parts) > 1 else False}\n"
                    else:
                        msg += f"    'по' НЕТ в строке\n"
                    # Проверяем, есть ли часть тела
                    match = re.search(r'бьет\s+[^,\.]+\s+в\s+([^,\.]+?)(?:\s|,|\.|по)', line)
                    if match:
                        msg += f"    Часть тела: {match.group(1)}\n"
                    else:
                        msg += f"    Часть тела НЕ найдена\n"
                    msg += f"    enemy_name в строке: {enemy_name in line}\n"
                    msg += f"    'бьет' в строке: {'бьет' in line}\n"

            # === ПАРСИМ ДЕЙСТВИЯ СОПЕРНИКА ===
            actions = parse_player_actions(text, enemy_name)

            # === ВЫВОД ПРИЁМОВ (только для текущего соперника) ===
            enemy_combos = []
            for combo in actions.get('combos', []):
                # Проверяем, что приём принадлежит текущему сопернику
                if isinstance(combo, dict) and combo.get('full_line'):
                    if enemy_name in combo['full_line']:
                        enemy_combos.append(combo)

            if enemy_combos:
                msg += "\n📋 Использованные приемы:\n"
                for combo in enemy_combos:
                    msg += f"  {combo['name']} : {combo['usage']}\n"

            # === ВЫВОД НАВЫКОВ (только для текущего соперника) ===
            enemy_skills = []
            skill_count = {}

            for skill in actions.get('skills', []):
                if isinstance(skill, dict) and skill.get('full_line'):
                    if enemy_name in skill['full_line']:
                        skill_name = skill['name']
                        # Считаем, сколько раз встречается навык
                        if skill_name not in skill_count:
                            skill_count[skill_name] = 0
                        skill_count[skill_name] += 1
                        # Добавляем только один раз в список (для уникальности)
                        if skill_name not in [s['name'] for s in enemy_skills]:
                            enemy_skills.append(skill)

            if enemy_skills:
                msg += "\n💫 Использованные навыки:\n"
                for skill in enemy_skills:
                    count = skill_count.get(skill['name'], 0)
                    msg += f"  {skill['name']} ({count})\n"

            # === СОХРАНЯЕМ ДЕЙСТВИЯ ДЛЯ ВСЕХ ИГРОКОВ ===
            all_players = defenders + attackers

            for player in all_players:
                player_name = player['name']

                if player_name not in session['enemy_hits_by_name']:
                    session['enemy_hits_by_name'][player_name] = []
                if player_name not in session['enemy_received_by_name']:
                    session['enemy_received_by_name'][player_name] = []
                if player_name not in session['enemy_stats_by_name']:
                    session['enemy_stats_by_name'][player_name] = {
                        'swords': 0, 'shields': 0, 'crits': 0,
                        'evades': 0, 'counters': 0, 'misses': 0,
                    }

                player_actions = parse_player_actions(text, player_name)
                player_stats = parse_enemy_stats(text, player_name)

                if player_actions.get('hits'):
                    session['enemy_hits_by_name'][player_name].extend(player_actions['hits'])
                if player_actions.get('received'):
                    session['enemy_received_by_name'][player_name].extend(player_actions['received'])

                # Сохраняем статистику
                if player_stats:
                    stats = session['enemy_stats_by_name'][player_name]
                    stats['swords'] += player_stats['swords']
                    stats['shields'] += player_stats['shields']
                    stats['crits'] += player_stats['crits']
                    stats['evades'] += player_stats['evades']
                    stats['counters'] += player_stats['counters']
                    stats['misses'] += player_stats['misses']

            # === ВЫЧИТАЕМ РЕСУРСЫ ИЗ СТАТИСТИКИ ТЕКУЩЕГО СОПЕРНИКА ===
            if enemy_name in session['enemy_stats_by_name']:
                stats = session['enemy_stats_by_name'][enemy_name]
                for combo in actions.get('combos', []):
                    if isinstance(combo, dict) and combo.get('resources'):
                        subtract_combo_resources(stats, combo['resources'])

            # === ДИАГНОСТИКА: проверяем, что сохранилось в сессии ===
            msg += "\n🔍 Диагностика сессии:\n"
            all_players = defenders + attackers
            for player in all_players:
                pname = player['name']
                hits = session['enemy_hits_by_name'].get(pname, [])
                received = session['enemy_received_by_name'].get(pname, [])
                msg += f"  {pname}: hits={len(hits)}, received={len(received)}\n"
                if hits:
                    msg += f"    hits: {hits}\n"
                if received:
                    msg += f"    received: {received}\n"

            # === ВЫВОД ДЛЯ ТЕКУЩЕГО СОПЕРНИКА ===
            if enemy_name in session['enemy_hits_by_name']:
                msg += f"\n🎯 Удары соперника ({enemy_name}):\n"
                for i, hit in enumerate(session['enemy_hits_by_name'][enemy_name], 1):
                    icon = "🛡" if hit['block'] else "🗡"
                    msg += f"  {i}) {hit['part']} ({icon})\n"

            if enemy_name in session['enemy_received_by_name']:
                msg += f"\n🛡️ Полученные удары ({enemy_name}):\n"
                for i, rec in enumerate(session['enemy_received_by_name'][enemy_name], 1):
                    icon = "🛡" if rec['block'] else "🗡"
                    msg += f"  {i}) {rec['part']} ({icon})\n"

            if enemy_name in session['enemy_stats_by_name']:
                stats = session['enemy_stats_by_name'][enemy_name]
                msg += f"\n📊 Накопленная статистика соперника ({enemy_name}):\n"
                msg += f"  🗡 {stats['swords']}  🛡 {stats['shields']}  🥊 {stats['crits']}  ⚡️ {stats['evades']}  🤺 {stats['counters']}  🌬 {stats['misses']}\n"

    # Разбиваем сообщение на части по 4000 символов
    if len(msg) > 4000:
        parts = [msg[i:i + 4000] for i in range(0, len(msg), 4000)]
        for part in parts:
            await update.message.reply_text(part, parse_mode="HTML")
    else:
        await update.message.reply_text(msg, parse_mode="HTML")

# ХЕЛП на КВ
async def help_cw(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Начинает сессию отслеживания противников"""
    user_id = update.effective_user.id

    # Проверка: уже в режиме
    if user_id in help_cw_sessions:
        await update.message.reply_text(
            "❌ Ты уже в режиме отслеживания противников.\n"
            "Используй /stop_help_cw, чтобы выйти."
        )
        return

    # Проверка: указан ли клан
    if not context.args:
        await update.message.reply_text(
            "❌ Укажи название своего клана.\n"
            "Пример: /help_cw Анархия"
        )
        return

    clan_name = ' '.join(context.args).strip()

    # Создаём сессию
    help_cw_sessions[user_id] = {
        'my_clan': clan_name,
        'enemy_clan': None,          # будет заполнено из первого лога
        'enemy_players': {},          # {имя_игрока: {'swords': 0, 'shields': 0, ...}}
        'last_turn': 0,
        'logs': [],
        'combos_used': {},            # {имя_игрока: [список использованных приёмов]}
        'started_at': datetime.now(),
    }

    await update.message.reply_text(
        f"✅ Режим отслеживания противников активирован!\n"
        f"Твой клан: {clan_name}\n\n"
        f"Присылай логи боя, содержащие слово «Ход».\n"
        f"Я буду отслеживать накопленные очки действий противников."
    )


# ==================== КОМАНДА /craft ====================

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
    """Обработчик всех callback-кнопок /craft"""
    query = update.callback_query
    await query.answer()

    data = query.data
    parts = data.split(':')

    # ==================== ВЫБОР РАЗДЕЛА ====================
    if parts[0] == 'craft_section' and len(parts) == 2:
        if parts[1] == 'equip':
            await query.edit_message_text(
                "🎒 <b>Экипировка — выбери грейд:</b>",
                parse_mode="HTML",
                reply_markup=build_grades_keyboard(craft_base)
            )
            return
        elif parts[1] == 'instr':
            await query.edit_message_text(
                "⚒️ <b>Инструменты — выбери тип:</b>",
                parse_mode="HTML",
                reply_markup=build_instruments_keyboard(craft_base)
            )
            return
        elif parts[1] == 'cook':
            await query.edit_message_text(
                "🥨 <b>Кулинария — выбери раздел:</b>",
                parse_mode="HTML",
                reply_markup=build_cooking_keyboard(craft_base)
            )
            return

    # ==================== АЛХИМИЯ ====================
    if parts[0] == 'craft_section' and len(parts) == 2 and parts[1] == 'alchemy':
        alchemy = craft_base.get('alchemy', {})
        if not alchemy:
            await query.edit_message_text(
                "❌ Алхимия не найдена в craft_base.json.",
                parse_mode="HTML"
            )
            return

        await query.edit_message_text(
            "🧪 <b>Алхимия — выбери раздел:</b>",
            parse_mode="HTML",
            reply_markup=build_alchemy_keyboard(craft_base)
        )
        return

    # ==================== ВЫБОР КАТЕГОРИИ АЛХИМИИ ====================
    if parts[0] == 'craft_ag' and len(parts) == 2:
        try:
            category_idx = int(parts[1])
        except ValueError:
            await query.edit_message_text("❌ Некорректные данные.")
            return

        alchemy = craft_base.get('alchemy', {})
        categories = list(alchemy.keys())
        if not (0 <= category_idx < len(categories)):
            await query.edit_message_text("❌ Категория не найдена.")
            return

        markup, category, has_subgroups, icon = build_alchemy_category_keyboard(
            craft_base, category_idx
        )
        if has_subgroups:
            text = f"{icon} <b>{category} — выбери подгруппу:</b>"
        else:
            text = f"🧪 <b>{category}</b> — выбери рецепт:"

        await query.edit_message_text(
            text,
            parse_mode="HTML",
            reply_markup=markup
        )
        return

    # ==================== ПОДГРУППА АЛХИМИИ ====================
    if parts[0] == 'craft_as' and len(parts) == 3:
        try:
            category_idx = int(parts[1])
        except ValueError:
            await query.edit_message_text("❌ Некорректные данные.")
            return

        alchemy = craft_base.get('alchemy', {})
        categories = list(alchemy.keys())
        if not (0 <= category_idx < len(categories)):
            await query.edit_message_text("❌ Категория не найдена.")
            return

        category = categories[category_idx]
        items = alchemy.get(category, [])
        subgroups = []
        seen_subgroups = set()
        for item in items:
            subcategory = item.get('subcategory')
            if subcategory and subcategory not in seen_subgroups:
                seen_subgroups.add(subcategory)
                subgroups.append(subcategory)

        sub_idx = parts[2]
        if sub_idx == 'ungrouped':
            selected_items = [(i, item) for i, item in enumerate(items) if not item.get('subcategory')]
            subgroup_title = 'Прочие ресурсы'
        else:
            try:
                sub_idx_int = int(sub_idx)
            except ValueError:
                await query.edit_message_text("❌ Подгруппа не найдена.")
                return
            if not (0 <= sub_idx_int < len(subgroups)):
                await query.edit_message_text("❌ Подгруппа не найдена.")
                return
            subgroup_title = subgroups[sub_idx_int]
            selected_items = [(i, item) for i, item in enumerate(items) if item.get('subcategory') == subgroup_title]

        subgroup_icons = {
            'Таланты': '💟',
            'Очищение камня': '🌡🎆',
            'Элексиры здоровья': '🧪',
            'Антидоты': '🧪',
            'Усиление': '🌡',
            'Заточки': '🔖',
            'Телепорты': '🗞',
            'Трансмутация': '📜',
            'Алхимия [IV+]': '🧪',
            'Алхимия [IV]': '🧪',
            'Алхимия [III+]': '🧪',
            'Алхимия [III]': '🧪',
            'Материя': 'Ⓜ️',
        }

        buttons = []
        for item_idx, item in selected_items:
            buttons.append([InlineKeyboardButton(
                item.get('title', 'Без названия')[:60],
                callback_data=f"craft_ai:{category_idx}:{item_idx}"
            )])

        buttons.append([InlineKeyboardButton(
            "⬅️ Назад",
            callback_data=f"craft_ag:{category_idx}"
        )])

        await query.edit_message_text(
            f"{subgroup_icons.get(subgroup_title, '🧪')} <b>{subgroup_title}</b> — выбери рецепт:",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(buttons)
        )
        return

    # ==================== РЕЦЕПТ АЛХИМИИ ====================
    if parts[0] == 'craft_ai' and len(parts) == 3:
        try:
            category_idx = int(parts[1])
            item_idx = int(parts[2])
        except ValueError:
            await query.edit_message_text("❌ Некорректные данные.")
            return

        alchemy = craft_base.get('alchemy', {})
        categories = list(alchemy.keys())
        if not (0 <= category_idx < len(categories)):
            await query.edit_message_text("❌ Категория не найдена.")
            return

        category = categories[category_idx]
        items = alchemy.get(category, [])
        if not (0 <= item_idx < len(items)):
            await query.edit_message_text("❌ Рецепт не найден.")
            return

        item = items[item_idx]
        text = f"<b>{item.get('title', 'Без названия')}</b>\n\n"

        if item.get('where'):
            text += f"📍 <b>Где:</b> {item['where']}\n\n"

        if item.get('craft_block'):
            text += "<b>Ресурсы для крафта:</b>\n"
            text += item['craft_block'] + "\n\n"

        if item.get('resources_block'):
            text += "<b>📊 Все необходимые ресурсы для крафта:</b>\n"
            text += f"<blockquote expandable>{item['resources_block']}</blockquote>\n\n"

        if item.get('energy'):
            text += f"<b>{item['energy']}</b>"

        # Возврат должен вести в ту подгруппу, из которой открыт рецепт.
        # Например, «Антидот архонта» → 🧪 Антидоты, а не общий раздел «Зелья».
        subcategory = item.get('subcategory')
        if subcategory:
            subgroups = []
            seen_subgroups = set()
            for candidate in items:
                candidate_subcategory = candidate.get('subcategory')
                if candidate_subcategory and candidate_subcategory not in seen_subgroups:
                    seen_subgroups.add(candidate_subcategory)
                    subgroups.append(candidate_subcategory)

            if subcategory in subgroups:
                back_cb = f"craft_as:{category_idx}:{subgroups.index(subcategory)}"
            else:
                back_cb = f"craft_ag:{category_idx}"
        else:
            back_cb = f"craft_ag:{category_idx}"

        context.user_data.setdefault('craft_calc_back', {})[str(item.get('id'))] = back_cb
        buttons = build_calculator_buttons(item.get('id'), 1, back_cb).inline_keyboard

        if len(text) > 4000:
            text = text[:3997] + "..."

        await query.edit_message_text(
            text,
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(buttons)
        )
        return

    # ==================== ВЫБОР ГРУППЫ ИНСТРУМЕНТОВ ====================
    if parts[0] == 'craft_ig' and len(parts) == 2:
        try:
            group_idx = int(parts[1])
        except ValueError:
            await query.edit_message_text("❌ Некорректные данные.")
            return

        instruments = craft_base.get('instruments', {})
        groups = instruments.get('groups', [])
        if not (0 <= group_idx < len(groups)):
            await query.edit_message_text("❌ Группа не найдена.")
            return

        group = groups[group_idx]

        await query.edit_message_text(
            f"⚒️ <b>{group['name']}</b>\n\nВыбери инструмент:",
            parse_mode="HTML",
            reply_markup=build_instrument_items_keyboard(group, group_idx)
        )
        return

    # ==================== ВЫБОР ИНСТРУМЕНТА ====================
    if parts[0] == 'craft_ii' and len(parts) == 3:
        try:
            group_idx = int(parts[1])
            item_idx = int(parts[2])
        except ValueError:
            await query.edit_message_text("❌ Некорректные данные.")
            return

        instruments = craft_base.get('instruments', {})
        groups = instruments.get('groups', [])
        if not (0 <= group_idx < len(groups)):
            await query.edit_message_text("❌ Группа не найдена.")
            return

        group = groups[group_idx]
        items = group.get('items', [])
        if not (0 <= item_idx < len(items)):
            await query.edit_message_text("❌ Инструмент не найден.")
            return

        item = items[item_idx]

        # Формируем сообщение (у инструментов нет resources_block)
        text = f"<b>{item['title']}</b>\n\n"

        if item.get('craft_block'):
            text += "<b>Ресурсы для крафта:</b>\n"
            text += item['craft_block'] + "\n\n"

        if item.get('energy'):
            text += f"<b>{item['energy']}</b>"

        back_cb = f"craft_ig:{group_idx}"
        context.user_data.setdefault('craft_calc_back', {})[str(item.get('id'))] = back_cb
        buttons = build_calculator_buttons(item.get('id'), 1, back_cb).inline_keyboard

        if len(text) > 4000:
            text = text[:3997] + "..."

        await query.edit_message_text(
            text,
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(buttons)
        )
        return

    # ==================== ВЫБОР ГРЕЙДА ====================
    if parts[0] == 'craft_g' and len(parts) == 2:
        try:
            grade_idx = int(parts[1])
        except ValueError:
            await query.edit_message_text("❌ Некорректные данные.")
            return

        grade = get_grade_by_idx(grade_idx, craft_base)
        if not grade:
            await query.edit_message_text("❌ Грейд не найден.")
            return

        classes = grade.get('classes', [])
        if not classes:
            await query.edit_message_text(
                f"🎒 <b>{grade['name']}</b>\n\nВ этом грейде пока нет классов.",
                parse_mode="HTML"
            )
            return

        buttons = build_classes_keyboard(classes, grade_idx)

        await query.edit_message_text(
            f"🎒 <b>{grade['name']}</b>\n\nВыбери класс:",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(buttons)
        )
        return

    # ==================== ВЫБОР КЛАССА ====================
    if parts[0] == 'craft_c' and len(parts) == 3:
        try:
            grade_idx = int(parts[1])
            class_idx = int(parts[2])
        except ValueError:
            await query.edit_message_text("❌ Некорректные данные.")
            return

        grade = get_grade_by_idx(grade_idx, craft_base)
        cls = get_class_by_idx(grade_idx, class_idx, craft_base)
        if not grade or not cls:
            await query.edit_message_text("❌ Класс не найден.")
            return

        buttons = build_class_items_keyboard(cls, grade_idx, class_idx)

        await query.edit_message_text(
            f"🎒 <b>{grade['name']}</b>\n📁 <b>{cls['name']}</b>\n\nВыбери:",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(buttons)
        )
        return

    # ==================== НАЗАД К ГЛАВНОМУ МЕНЮ ====================
    if parts[0] == 'craft_back' and len(parts) == 2 and parts[1] == 'main':
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
        await query.edit_message_text(
            "⚒️ <b>Крафт — выбери раздел:</b>",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return

    # ==================== НАЗАД К ГРЕЙДАМ ====================
    if parts[0] == 'craft_back' and len(parts) == 2 and parts[1] == 'grades':
        await query.edit_message_text(
            "🎒 <b>Экипировка — выбери грейд:</b>",
            parse_mode="HTML",
            reply_markup=build_grades_keyboard(craft_base)
        )
        return

    # ==================== ВЫБОР ГРУППЫ ====================
    if parts[0] == 'craft_gr' and len(parts) == 4:
        try:
            grade_idx = int(parts[1])
            class_idx = int(parts[2])
            group_idx = int(parts[3])
        except ValueError:
            await query.edit_message_text("❌ Некорректные данные.")
            return

        grade = get_grade_by_idx(grade_idx, craft_base)
        cls = get_class_by_idx(grade_idx, class_idx, craft_base)
        if not grade or not cls or 'groups' not in cls:
            await query.edit_message_text("❌ Группа не найдена.")
            return

        groups = cls['groups']
        if not (0 <= group_idx < len(groups)):
            await query.edit_message_text("❌ Группа не найдена.")
            return

        group = groups[group_idx]
        buttons = []
        row = []

        # Сначала подгруппы (если есть)
        subgroups = group.get('subgroups', [])
        for i, subgroup in enumerate(subgroups):
            row.append(InlineKeyboardButton(
                f"{subgroup['name']} ({len(subgroup.get('items', []))})",
                callback_data=f"craft_sg:{grade_idx}:{class_idx}:{group_idx}:{i}"
            ))
            if len(row) == 2:
                buttons.append(row)
                row = []
        if row:
            buttons.append(row)
            row = []

        # Затем прямые предметы группы
        items = group.get('items', [])
        for i, item in enumerate(items):
            label = item['title'][:60]
            buttons.append([InlineKeyboardButton(
                label,
                callback_data=f"craft_i:{grade_idx}:{class_idx}:{group_idx}:-1:{i}"
            )])

        # Кнопка «Назад» на класс
        buttons.append([InlineKeyboardButton(
            "⬅️ Назад",
            callback_data=f"craft_c:{grade_idx}:{class_idx}"
        )])

        await query.edit_message_text(
            f"🎒 <b>{grade['name']}</b>\n📁 <b>{cls['name']}</b>\n📂 <b>{group['name']}</b>\n\nВыбери:",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(buttons)
        )
        return

    # ==================== ВЫБОР ПОДГРУППЫ ====================
    if parts[0] == 'craft_sg' and len(parts) == 5:
        try:
            grade_idx = int(parts[1])
            class_idx = int(parts[2])
            group_idx = int(parts[3])
            subgroup_idx = int(parts[4])
        except ValueError:
            await query.edit_message_text("❌ Некорректные данные.")
            return

        grade = get_grade_by_idx(grade_idx, craft_base)
        cls = get_class_by_idx(grade_idx, class_idx, craft_base)
        if not grade or not cls or 'groups' not in cls:
            await query.edit_message_text("❌ Подгруппа не найдена.")
            return

        groups = cls['groups']
        if not (0 <= group_idx < len(groups)):
            await query.edit_message_text("❌ Подгруппа не найдена.")
            return

        group = groups[group_idx]
        subgroups = group.get('subgroups', [])
        if not (0 <= subgroup_idx < len(subgroups)):
            await query.edit_message_text("❌ Подгруппа не найдена.")
            return

        subgroup = subgroups[subgroup_idx]
        items = subgroup.get('items', [])

        buttons = []
        for i, item in enumerate(items):
            label = item['title'][:60]
            buttons.append([InlineKeyboardButton(
                label,
                callback_data=f"craft_i:{grade_idx}:{class_idx}:{group_idx}:{subgroup_idx}:{i}"
            )])

        # Кнопка «Назад» на группу
        buttons.append([InlineKeyboardButton(
            "⬅️ Назад",
            callback_data=f"craft_gr:{grade_idx}:{class_idx}:{group_idx}"
        )])

        await query.edit_message_text(
            f"🎒 <b>{grade['name']}</b>\n📁 <b>{cls['name']}</b>\n📂 <b>{group['name']}</b>\n📄 <b>{subgroup['name']}</b>\n\nВыбери предмет:",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(buttons)
        )
        return

    # ==================== ВЫБОР ПРЕДМЕТА ====================
    if parts[0] == 'craft_i' and len(parts) == 6:
        try:
            grade_idx = int(parts[1])
            class_idx = int(parts[2])
            group_idx = int(parts[3])
            subgroup_idx = int(parts[4])
            item_idx = int(parts[5])
        except ValueError:
            await query.edit_message_text("❌ Некорректные данные.")
            return

        grade = get_grade_by_idx(grade_idx, craft_base)
        cls = get_class_by_idx(grade_idx, class_idx, craft_base)
        if not grade or not cls:
            await query.edit_message_text("❌ Предмет не найден.")
            return

        item = None

        # Определяем путь
        if group_idx == -1:
            # Плоский класс
            items = cls.get('items', [])
            if 0 <= item_idx < len(items):
                item = items[item_idx]
        else:
            # С группами
            groups = cls.get('groups', [])
            if not (0 <= group_idx < len(groups)):
                await query.edit_message_text("❌ Группа не найдена.")
                return
            group = groups[group_idx]

            if subgroup_idx == -1:
                # Прямой предмет группы
                items = group.get('items', [])
                if 0 <= item_idx < len(items):
                    item = items[item_idx]
            else:
                # Предмет подгруппы
                subgroups = group.get('subgroups', [])
                if not (0 <= subgroup_idx < len(subgroups)):
                    await query.edit_message_text("❌ Подгруппа не найдена.")
                    return
                subgroup = subgroups[subgroup_idx]
                items = subgroup.get('items', [])
                if 0 <= item_idx < len(items):
                    item = items[item_idx]

        if not item:
            await query.edit_message_text("❌ Предмет не найден.")
            return

        # Формируем сообщение
        text = f"<b>{item['title']}</b>\n\n"

        if item.get('craft_block'):
            text += "<b>Ресурсы для крафта:</b>\n"
            text += item['craft_block'] + "\n\n"

        if item.get('resources_block'):
            text += "<b>📊 Все необходимые ресурсы для крафта:</b>\n"
            text += f"<blockquote expandable>{item['resources_block']}</blockquote>\n\n"

        if item.get('energy'):
            text += f"<b>{item['energy']}</b>"

        # Кнопка «Назад»
        if group_idx == -1:
            back_cb = f"craft_c:{grade_idx}:{class_idx}"
        elif subgroup_idx == -1:
            back_cb = f"craft_gr:{grade_idx}:{class_idx}:{group_idx}"
        else:
            back_cb = f"craft_sg:{grade_idx}:{class_idx}:{group_idx}:{subgroup_idx}"

        # Для раздела «Экипировка» калькулятор отключён.
        buttons = [[InlineKeyboardButton("⬅️ Назад", callback_data=back_cb)]]

        # Telegram ограничивает 4096 символов, режем если больше
        if len(text) > 4000:
            text = text[:3997] + "..."

        await query.edit_message_text(
            text,
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(buttons)
        )
        return
    # ==================== ВЫБОР ГРУППЫ КУЛИНАРИИ ====================
    if parts[0] == 'craft_cg' and len(parts) == 2:
        try:
            group_idx = int(parts[1])
        except ValueError:
            await query.edit_message_text("❌ Некорректные данные.")
            return

        cooking = craft_base.get('cooking', {})
        groups = cooking.get('groups', [])
        if not (0 <= group_idx < len(groups)):
            await query.edit_message_text("❌ Группа не найдена.")
            return

        group = groups[group_idx]

        await query.edit_message_text(
            f"🥨 <b>{group['name']}</b>\n\nВыбери блюдо:",
            parse_mode="HTML",
            reply_markup=build_cooking_items_keyboard(group, group_idx)
        )
        return

    # ==================== ВЫБОР БЛЮДА ====================
    if parts[0] == 'craft_ci' and len(parts) == 3:
        try:
            group_idx = int(parts[1])
            item_idx = int(parts[2])
        except ValueError:
            await query.edit_message_text("❌ Некорректные данные.")
            return

        cooking = craft_base.get('cooking', {})
        groups = cooking.get('groups', [])
        if not (0 <= group_idx < len(groups)):
            await query.edit_message_text("❌ Группа не найдена.")
            return

        group = groups[group_idx]
        items = group.get('items', [])
        if not (0 <= item_idx < len(items)):
            await query.edit_message_text("❌ Блюдо не найдено.")
            return

        item = items[item_idx]

        text = f"<b>{item['title']}</b>\n\n"

        if item.get('craft_block'):
            text += "<b>Ресурсы для крафта:</b>\n"
            text += item['craft_block'] + "\n\n"

        if item.get('resources_block'):
            text += "<b>📊 Все необходимые ресурсы для крафта:</b>\n"
            text += f"<blockquote expandable>{item['resources_block']}</blockquote>\n\n"

        if item.get('energy'):
            text += f"<b>{item['energy']}</b>"

        back_cb = f"craft_cg:{group_idx}"
        context.user_data.setdefault('craft_calc_back', {})[str(item.get('id'))] = back_cb
        buttons = build_calculator_buttons(item.get('id'), 1, back_cb).inline_keyboard

        if len(text) > 4000:
            text = text[:3997] + "..."

        await query.edit_message_text(
            text,
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(buttons)
        )
        return

    # ==================== ЗАГЛУШКА ====================
    await query.edit_message_text("⏳ В разработке.")



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

    app.add_handler(CommandHandler("start_cw", start_cw))
    app.add_handler(CommandHandler("stop_cw", stop_cw))

    app.add_handler(CommandHandler("help_cw", help_cw))

    app.add_handler(CommandHandler("test_parse", test_parse))
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
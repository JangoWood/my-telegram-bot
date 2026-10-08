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


@chat_restricted
async def find(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Ищет игрока в объединённых данных с трёх листов."""
    if not context.args:
        await update.message.reply_text(
            "ℹ️ Укажите имя игрока для поиска. Пример: /find pa3ym",
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
        await update.message.reply_text("❌ Нет данных для поиска")
        return

    if not found_items:
        await update.message.reply_text(f"❌ Игрок '{search}' не найден")
        return

    response = f"🔎 <b>Найдено {len(found_items)} результатов:</b>\n\n"

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

from utils.inline_search import inline_query

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


async def craft_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обёртка для callback-кнопок /craft."""
    await handle_craft_callback(update, context, craft_base)


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
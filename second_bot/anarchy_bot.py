import os
import csv
import requests
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
from dotenv import load_dotenv
from pathlib import Path
from io import StringIO
from flask import Flask
import threading
from telegram import InlineQueryResultArticle, InputTextMessageContent
from telegram.ext import InlineQueryHandler

# Загружаем переменные из .env в корне проекта
env_path = Path(__file__).parent.parent / '.env'
load_dotenv(env_path)

TELEGRAM_BOT_TOKEN = os.getenv('SECOND_BOT_TOKEN')
CSV_URL = 'https://docs.google.com/spreadsheets/d/e/2PACX-1vQhxznVeD5jD268Xb5x9crTJe0Di5Ra0OeSfqn_O_GA0plGpQHd8RFUg1GLlAnHgQx45XlklE1IVub9/pub?output=csv'
CW_SHEET_GID = '279368796'  # GID листа со специализациями

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

async def get_data(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data, headers, error = get_table_data()
    if error:
        await update.message.reply_text(error)
        return

    if not data:
        await update.message.reply_text("❌ Нет данных")
        return

    response = "📊 <b>Актуальная таблица</b>\n\n"
    for row in data:
        formatted = format_table_row(row, headers)
        if formatted:
            response += formatted + "\n"
            if len(response) > 4000:
                await update.message.reply_text(response, parse_mode="HTML")
                response = ""

    if response:
        await update.message.reply_text(response, parse_mode="HTML")


async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data, headers, error = get_table_data()
    if error:
        await update.message.reply_text(error)
        return

    if not data:
        await update.message.reply_text("❌ Нет данных")
        return

    date_start = headers[1].strip() if len(headers) > 1 else "??"
    date_end = headers[2].strip() if len(headers) > 2 else "??"

    total_points = 0
    total_coins = 0
    total_hand_coins = 0

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
        except ValueError:
            continue

        total_points += points
        total_coins += coins
        total_hand_coins += hand_coins

    response = f"📊 <b>Статистика таблицы</b>\n\n"
    response += f"📅 <b>Период:</b> {date_start} – {date_end}\n\n"
    response += f"⚔️ <b>Сумма очков:</b> {total_points:,.2f}\n"
    response += f"💰 <b>Сумма монет:</b> {total_coins:,.2f}\n"
    response += f"💎 <b>Монет на руках:</b> {total_hand_coins:,.2f}\n"

    await update.message.reply_text(response, parse_mode="HTML")


async def find(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("ℹ️ Укажите текст для поиска. Пример: /find pa3ym")
        return

    search = ' '.join(context.args).lower()
    data, headers, error = get_table_data()
    if error:
        await update.message.reply_text(error)
        return

    if not data:
        await update.message.reply_text("❌ Нет данных для поиска")
        return

    found_rows = []
    for row in data:
        if not row:
            continue
        row_text = ' '.join(row).lower()
        if search in row_text:
            found_rows.append(row)
            if len(found_rows) >= 20:
                break

    if not found_rows:
        await update.message.reply_text(f"❌ Ничего не найдено для '{search}'")
        return

    response = f"🔎 <b>Найдено {len(found_rows)} результатов:</b>\n\n"
    for row in found_rows:
        formatted = format_table_row(row, headers)
        if formatted:
            response += formatted + "\n"
        if len(response) > 4000:
            await update.message.reply_text(response, parse_mode="HTML")
            response = ""

    if response:
        await update.message.reply_text(response, parse_mode="HTML")


# ==================== СПЕЦИАЛИЗАЦИИ (лист с GID 279368796) ====================

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


async def inline_query(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обрабатывает инлайн-запросы (@bot_name текст) — сразу показываем результат"""
    query = update.inline_query.query.strip().lower()

    if not query:
        # Если запрос пустой, показываем подсказку
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

        # Проверяем, содержит ли имя поисковую строку
        if query in name.lower():
            # Формируем красивый ответ для отправки
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

            # Создаём результат
            result = InlineQueryResultArticle(
                id=f"player_{name}",
                title=f"🤟🏼 {name}",
                description=f"⚔️ {points} очков, 💰 {coins} монет",
                input_message_content=InputTextMessageContent(text, parse_mode="HTML")
            )
            found.append(result)

            if len(found) >= 20:
                break

    # Если ничего не найдено
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

    # Отправляем результаты
    await update.inline_query.answer(found, cache_time=0)

async def spec_search(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Поиск игроков по специализации с группировкой по уровням (/f)"""
    if not context.args:
        await update.message.reply_text(
            "🔍 <b>Поиск по специализации</b>\n\n"
            "Примеры:\n"
            "  /f алхимия\n"
            "  /f кулинария\n"
            "  /f крафтер\n\n"
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

    search_input = ' '.join(context.args).lower()

    synonyms = {
        'крафтер': 1, 'крафт': 1, 'к': 1,
        'рыбалка': 2, 'рыба': 2, 'р': 2,
        'шахтёр': 3, 'шахта': 3, 'ш': 3,
        'охота': 4, 'охотник': 4, 'о': 4,
        'кулинария': 5, 'еда': 5, 'кухня': 5, 'кул': 5,
        'алхимия': 6, 'алхим': 6, 'алх': 6, 'а': 6,
        'плавильщик': 7, 'плавка': 7, 'пл': 7,
        'фермер': 8, 'ферма': 8, 'ф': 8,
    }

    col_index = None
    for key, index in synonyms.items():
        if search_input == key or (len(search_input) > 1 and key.startswith(search_input)):
            col_index = index
            break

    spec_names = {
        1: 'КРАФТЕР',
        2: 'РЫБАЛКА',
        3: 'ШАХТЁР',
        4: 'ОХОТА',
        5: 'КУЛИНАРИЯ',
        6: 'АЛХИМИЯ',
        7: 'ПЛАВИЛЬЩИК',
        8: 'ФЕРМЕР'
    }

    if col_index is None:
        await update.message.reply_text(
            f"❌ Специализация '{search_input}' не найдена.\n\n"
            f"📋 <b>Доступные синонимы:</b>\n"
            f"  • крафтер / крафт / к\n"
            f"  • рыбалка / рыба / р\n"
            f"  • шахтёр / шахта / ш\n"
            f"  • охота / охотник / о\n"
            f"  • кулинария / еда / кухня / кул\n"
            f"  • алхимия / алхим / алх / а\n"
            f"  • плавильщик / плавка / пл\n"
            f"  • фермер / ферма / ф",
            parse_mode="HTML"
        )
        return

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

        levels = {}

        for row in data[1:]:
            if not row or len(row) < col_index + 1:
                continue

            name = row[0].strip()
            if not name:
                continue

            level = row[col_index].strip() if row[col_index] else "—"
            if not level or level == "-":
                continue

            if level not in levels:
                levels[level] = []
            levels[level].append(name)

        if not levels:
            await update.message.reply_text(f"❌ Нет данных по специализации '{spec_names[col_index]}'")
            return

        def sort_key(level):
            order = {'ГМ': 1, 'ПМ': 2, 'М': 3, 'У': 4}
            prefix = level[:2] if level[:2] in order else level[:1] if level[:1] in order else 'Я'
            num = int(level[2:]) if len(level) > 2 and level[2:].isdigit() else 0
            return (order.get(prefix, 99), -num)

        sorted_levels = sorted(levels.keys(), key=sort_key)

        response = f"🔍 <b>Поиск по специализации: {spec_names[col_index]}</b>\n\n"

        for level in sorted_levels:
            players = sorted(levels[level], key=str.lower)
            response += f"<b>{level}</b> ({len(players)}): {', '.join(players)}\n"

            if len(response) > 4000:
                await update.message.reply_text(response, parse_mode="HTML")
                response = ""

        if response:
            await update.message.reply_text(response, parse_mode="HTML")

    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {e}")


async def get_profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показывает специализации игрока по тегу из ответа на сообщение"""

    # Проверяем, есть ли ответ на сообщение
    if not update.message.reply_to_message:
        await update.message.reply_text(
            "ℹ️ <b>Как использовать:</b>\n"
            "1. Нажмите 'ответить' на сообщение игрока\n"
            "2. Отправьте команду /prof\n\n"
            "Бот найдёт игрока по его Telegram тегу и покажет специализации",
            parse_mode="HTML"
        )
        return

    # Получаем автора исходного сообщения
    user = update.message.reply_to_message.from_user
    user_tag = f"@{user.username}" if user.username else None

    if not user_tag:
        await update.message.reply_text(
            "❌ У пользователя нет username в Telegram.\n"
            "Попросите его установить username в настройках Telegram."
        )
        return

    # Загружаем данные специализаций
    data, headers, error = get_specializations_data()

    if error or not data:
        await update.message.reply_text("❌ Не удалось загрузить данные специализаций")
        return

    # Ищем строку с тегом
    found_row = None
    for row in data:
        if row and len(row) > 0 and row[0].strip().lower() == user_tag.lower():
            found_row = row
            break

    if not found_row:
        await update.message.reply_text(
            f"❌ Игрок с тегом {user_tag} не найден в таблице специализаций.\n\n"
            f"Возможно, в таблице указан другой тег или имя не совпадает."
        )
        return

    # Форматируем вывод специализаций
    response = format_specializations_for_profile(found_row, headers)
    await update.message.reply_text(response, parse_mode="HTML")

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
    # app.add_handler(CommandHandler("s", spec))  ← ЗАКОММЕНТИРОВАЛИ или УДАЛИЛИ
    app.add_handler(CommandHandler("f", spec_search))

    # Инлайн-обработчик
    app.add_handler(InlineQueryHandler(inline_query))

    app.add_handler(CommandHandler("prof", get_profile))

    print("✅ Бот запущен и готов к работе!")
    app.run_polling()


if __name__ == '__main__':
    # Запускаем Flask в отдельном потоке для healthcheck
    threading.Thread(target=run_flask, daemon=True).start()
    # Запускаем бота
    main()
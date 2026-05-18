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
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CallbackQueryHandler

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


async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обрабатывает нажатия на кнопки выбора грейда"""
    print("🔔 1. button_callback ВЫЗВАН")
    query = update.callback_query
    print(f"🔔 2. Данные кнопки: {query.data}")

    try:
        await query.answer()
        print("🔔 3. query.answer() выполнен")
    except Exception as e:
        print(f"❌ Ошибка при answer: {e}")

    print(f"DEBUG: Нажата кнопка с данными: {query.data}")

    grade_map = {
        'get_data_t4+': ('0', 'T4+'),
        'get_data_t4': ('296213375', 'T4'),
        'get_data_t3+': ('677729120', 'T3+'),
    }

    if query.data in grade_map:
        gid, name = grade_map[query.data]
        print(f"DEBUG: Загружаем данные для GID {gid}")

        try:
            data, headers = get_table_data_by_gid(gid)
            print(f"DEBUG: Получено {len(data) if data else 0} строк")
        except Exception as e:
            print(f"❌ Ошибка get_table_data_by_gid: {e}")
            await query.edit_message_text(f"❌ Ошибка загрузки данных: {e}")
            return

        if not data:
            await query.edit_message_text(f"❌ Нет данных для грейда {name}")
            return

        date_start = headers[1].strip() if headers and len(headers) > 1 else "??"
        date_end = headers[2].strip() if headers and len(headers) > 2 else "??"

        response = f"📊 <b>Актуальная таблица {name}</b>\n"
        response += f"📅 <b>Период:</b> {date_start} – {date_end}\n\n"

        for row in data[:20]:
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

        if len(data) > 20:
            response += f"\n📌 <i>Показано 20 из {len(data)} строк</i>"

        try:
            await query.edit_message_text(response, parse_mode="HTML")
            print("✅ Сообщение успешно обновлено")
        except Exception as e:
            print(f"❌ Ошибка при edit_message_text: {e}")
    else:
        print(f"DEBUG: Неизвестный callback: {query.data}")


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
    """Объединяет данные с трёх листов для поиска (/find)"""
    # Загружаем данные с основного листа
    main_data, main_headers = get_table_data_by_gid(MAIN_SHEET_GID)

    # Загружаем данные со второго листа
    second_data, second_headers = get_table_data_by_gid(SECOND_SHEET_GID)

    # Загружаем данные с третьего листа (новый)
    third_data, third_headers = get_table_data_by_gid(THIRD_SHEET_GID)

    # Объединяем строки
    combined_data = []
    if main_data:
        combined_data.extend(main_data)
    if second_data:
        combined_data.extend(second_data)
    if third_data:
        combined_data.extend(third_data)

    print(f"📊 Всего строк для поиска: {len(combined_data)}")

    # Для заголовков используем первый непустой (с основного листа)
    headers = main_headers if main_headers else (second_headers if second_headers else third_headers)

    return combined_data, headers

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
    """Ищет игрока в объединённых данных с двух листов"""
    if not context.args:
        await update.message.reply_text(
            "ℹ️ Укажите имя игрока для поиска. Пример: /find pa3ym",
            parse_mode="HTML"
        )
        return

    search = ' '.join(context.args).lower().strip()

    # Используем объединённые данные с двух листов
    data, headers = get_combined_table_data()

    if not data:
        await update.message.reply_text("❌ Нет данных для поиска")
        return

    # Поиск только в первом столбце (имя игрока)
    found_rows = []
    for row in data:
        if not row:
            continue
        name = row[0].strip().lower() if row[0] else ""
        if not name:
            continue

        if search in name:
            found_rows.append(row)
            if len(found_rows) >= 20:
                break

    if not found_rows:
        await update.message.reply_text(f"❌ Игрок '{search}' не найден")
        return

    # Определяем даты (если есть, иначе стандартные)
    date_start = headers[1].strip() if headers and len(headers) > 1 else "??"
    date_end = headers[2].strip() if headers and len(headers) > 2 else "??"

    response = f"🔎 <b>Найдено {len(found_rows)} результатов:</b>\n\n"

    for row in found_rows:
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
    """Поиск игроков по специализации с возможностью фильтрации по уровню"""
    if not context.args:
        await update.message.reply_text(
            "🔍 <b>Поиск по специализации</b>\n\n"
            "Примеры:\n"
            "  /f алхимия — все алхимики\n"
            "  /f алхимия ГМ4 — только ГМ4\n"
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
        'крафтер': 2, 'крафт': 2, 'к': 2,
        'рыбалка': 3, 'рыба': 3, 'р': 3,
        'шахтёр': 4, 'шахта': 4, 'ш': 4,
        'охота': 5, 'охотник': 5, 'о': 5,
        'кулинария': 6, 'еда': 6, 'кухня': 6, 'кул': 6,
        'алхимия': 7, 'алхим': 7, 'алх': 7, 'а': 7,
        'плавильщик': 8, 'плавка': 8, 'пл': 8,
        'фермер': 9, 'ферма': 9, 'ф': 9,
    }

    col_index = None
    for key, index in synonyms.items():
        if search_input == key or (len(search_input) > 1 and key.startswith(search_input)):
            col_index = index
            break

    spec_names = {
        2: 'КРАФТЕР',
        3: 'РЫБАЛКА',
        4: 'ШАХТЁР',
        5: 'ОХОТА',
        6: 'КУЛИНАРИЯ',
        7: 'АЛХИМИЯ',
        8: 'ПЛАВИЛЬЩИК',
        9: 'ФЕРМЕР'
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
        url = f'https://docs.google.com/spreadsheets/d/e/2PACX-1vQhxznVeD5jD268Xb5x9crTJe0Di5Ra0OeSfqn_O_GA0plGpQHd8RFUg1GLlAnHgQx45XlklE1IVub9/pub?gid={CW_SHEET_GID}&output=csv'
        response = requests.get(url, timeout=15)
        response.raise_for_status()
        response.encoding = 'utf-8'

        csv_file = StringIO(response.text)
        reader = csv.reader(csv_file)
        data = list(reader)

        if not data:
            await update.message.reply_text("❌ Нет данных")
            return

        # Группируем игроков по уровню
        levels = {}

        for row in data[1:]:  # Пропускаем заголовки
            if not row or len(row) < col_index + 1:
                continue

            name = row[1].strip() if len(row) > 1 else ""  # Имя в колонке 1
            if not name:
                continue

            level = row[col_index].strip() if row[col_index] else "—"
            if not level or level == "-":
                continue

            if level_filter and level.upper() != level_filter:
                continue

            if level not in levels:
                levels[level] = []
            levels[level].append(name)

        if not levels:
            filter_text = f" с уровнем {level_filter}" if level_filter else ""
            await update.message.reply_text(
                f"❌ Нет игроков по специализации '{spec_names[col_index]}'{filter_text}"
            )
            return

        # Сортировка уровней: Э > ГМ > М > ПМ > У, внутри группы по убыванию номера
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

            return (order[prefix], -num)

        sorted_levels = sorted(levels.keys(), key=sort_key)

        spec_name = spec_names[col_index]
        filter_text = f" {level_filter}" if level_filter else ""
        response = f"🔍 <b>Поиск по специализации: {spec_name}{filter_text}</b>\n\n"

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
    """Показывает специализации игрока"""

    # Загружаем данные специализаций
    data, headers, error = get_specializations_data()
    if error or not data:
        await update.message.reply_text("❌ Не удалось загрузить данные специализаций")
        return

    # Определяем, чей тег искать
    user_tag = None
    is_self = True
    use_reply = False

    # Если команда в ответ на сообщение — пробуем взять автора
    if update.message.reply_to_message:
        replied_user = update.message.reply_to_message.from_user
        replied_tag = f"@{replied_user.username}" if replied_user.username else None

        # Проверяем, есть ли этот тег в таблице
        if replied_tag:
            for row in data:
                if row and len(row) > 0 and row[0].strip().lower() == replied_tag.lower():
                    use_reply = True
                    user_tag = replied_tag
                    is_self = (replied_user.id == update.effective_user.id)
                    break

    # Если не используем ответ (нет тега в таблице или нет ответа) — берём отправителя
    if not use_reply:
        user = update.effective_user
        user_tag = f"@{user.username}" if user.username else None
        is_self = True

    if not user_tag:
        await update.message.reply_text(
            "❌ У пользователя нет username в Telegram.\n"
            "Попросите его установить username в настройках Telegram."
        )
        return

    # Ищем строку с тегом
    found_row = None
    for row in data:
        if row and len(row) > 0 and row[0].strip().lower() == user_tag.lower():
            found_row = row
            break

    if found_row:
        response = format_specializations_for_profile(found_row, headers)
        await update.message.reply_text(response, parse_mode="HTML")
        return

    # Если не нашли
    if is_self:
        await update.message.reply_text(
            f"❌ Игрок с тегом {user_tag} не найден в таблице специализаций.\n\n"
            f"📝 <b>Чтобы добавиться в таблицу:</b>\n"
            f"1. Напишите администратору\n"
            f"2. Сообщите ваш игровой ник и специализации\n\n"
            f"💡 После добавления команда /prof начнёт работать для вас автоматически.",
            parse_mode="HTML"
        )
    else:
        await update.message.reply_text(
            f"❌ Игрок с тегом {user_tag} не найден в таблице специализаций.\n\n"
            f"Возможно, в таблице указан другой тег или игрок ещё не добавлен.",
            parse_mode="HTML"
        )

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
    app.add_handler(CallbackQueryHandler(button_callback))
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
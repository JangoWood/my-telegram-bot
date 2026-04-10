import os
import json
import logging
import threading
from flask import Flask
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
import gspread
from google.oauth2.service_account import Credentials

# ===== НАСТРОЙКИ =====
# Все секреты — из переменных окружения Render
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
GOOGLE_SHEET_ID = os.getenv('GOOGLE_SHEET_ID')
SHEET_NAME = os.getenv('SHEET_NAME', 'Кулинария и склад')

# ДИАПАЗОН ДАННЫХ (можно тоже вынести в переменные, если нужно)
START_ROW = 5
END_ROW = 26
COLUMN_AF = 'AF'
COLUMN_AG = 'AG'
# =====================

logging.basicConfig(level=logging.INFO)

# --- ФЛЭШ-ПРИЛОЖЕНИЕ ДЛЯ HEALTHCHECK ---
flask_app = Flask(__name__)


@flask_app.route('/')
@flask_app.route('/health')
@flask_app.route('/healthcheck')
def health():
    return "OK", 200


def run_flask():
    """Запускает Flask-сервер на порту, который требует Render"""
    port = int(os.environ.get("PORT", 8080))
    flask_app.run(host='0.0.0.0', port=port)


# --- РАБОТА С GOOGLE SHEETS (БЕЗОПАСНАЯ ВЕРСИЯ) ---
def get_google_sheet():
    """Подключается к Google Sheets, используя JSON из переменной окружения"""
    try:
        # Получаем JSON из переменной окружения
        creds_json_str = os.getenv('GOOGLE_CREDENTIALS_JSON')

        if creds_json_str:
            # На сервере: читаем из переменной
            creds_dict = json.loads(creds_json_str)
            creds = Credentials.from_service_account_info(
                creds_dict,
                scopes=['https://www.googleapis.com/auth/spreadsheets',
                        'https://www.googleapis.com/auth/drive']
            )
        else:
            # Локальная разработка: читаем из файла
            creds = Credentials.from_service_account_file(
                'credentials.json',
                scopes=['https://www.googleapis.com/auth/spreadsheets',
                        'https://www.googleapis.com/auth/drive']
            )

        client = gspread.authorize(creds)
        sheet = client.open_by_key(GOOGLE_SHEET_ID).worksheet(SHEET_NAME)
        return sheet
    except Exception as e:
        logging.error(f"Ошибка подключения к Google Sheets: {e}")
        return None


def get_data_range(sheet):
    """Получает данные из диапазона AF5:AG26"""
    try:
        data_range = f"{COLUMN_AF}{START_ROW}:{COLUMN_AG}{END_ROW}"
        logging.info(f"Читаю диапазон: {data_range}")

        cell_values = sheet.get(data_range)

        data = []
        for row in cell_values:
            if row and any(row):
                cleaned_row = [str(cell).strip() if cell else "" for cell in row]
                data.append(cleaned_row)

        return data
    except Exception as e:
        logging.error(f"Ошибка при чтении: {e}")
        return []


# --- КОМАНДЫ БОТА ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Привет! Я бот для проверки склада.\n\n"
        "📋 Команды:\n"
        "/get_all - Показать все остатки\n"
        "/find <текст> - Найти по названию\n"
        "/stats - Показать статистику"
    )


async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    sheet = get_google_sheet()
    if sheet is None:
        await update.message.reply_text("❌ Ошибка подключения к таблице.")
        return

    data = get_data_range(sheet)

    if not data:
        await update.message.reply_text("Нет данных.")
        return

    total_sum = 0
    for row in data:
        if len(row) > 1 and row[1] and row[1].isdigit():
            total_sum += int(row[1])

    stats_msg = f"📊 <b>Статистика склада</b>\n\n"
    stats_msg += f"📍 Всего позиций: {len(data)}\n"
    stats_msg += f"📦 Общее количество: {total_sum}"

    await update.message.reply_text(stats_msg, parse_mode="HTML")


async def get_all(update: Update, context: ContextTypes.DEFAULT_TYPE):
    sheet = get_google_sheet()
    if sheet is None:
        await update.message.reply_text("❌ Ошибка подключения к таблице.")
        return

    await update.message.reply_text("⏳ Загружаю данные...")

    data = get_data_range(sheet)

    if not data:
        await update.message.reply_text("Нет данных.")
        return

    response = "<pre>"

    for row in data:
        value_af = row[0] if len(row) > 0 and row[0] else ""
        value_ag = row[1] if len(row) > 1 and row[1] else ""

        if value_af and value_ag:
            name = value_af[:40]
            spaces = " " * (40 - len(name))
            response += f"{name}{spaces}{value_ag}\n"

        if len(response) > 3900:
            response += "</pre>"
            await update.message.reply_text(response, parse_mode="HTML")
            response = "<pre>"

    response += "</pre>"

    if response != "<pre></pre>":
        await update.message.reply_text(response, parse_mode="HTML")


async def find(update: Update, context: ContextTypes.DEFAULT_TYPE):
    sheet = get_google_sheet()
    if sheet is None:
        await update.message.reply_text("❌ Ошибка подключения к таблице.")
        return

    if not context.args:
        await update.message.reply_text("ℹ️ Укажите текст для поиска. Пример: /find перец")
        return

    search_term = ' '.join(context.args).lower()

    await update.message.reply_text(f"🔍 Ищу '<b>{search_term}</b>'...", parse_mode="HTML")

    data = get_data_range(sheet)

    if not data:
        await update.message.reply_text("Нет данных для поиска.")
        return

    found = []
    for row in data:
        value_af = row[0].lower() if len(row) > 0 and row[0] else ""
        original_af = row[0] if len(row) > 0 and row[0] else ""
        original_ag = row[1] if len(row) > 1 and row[1] else ""

        if search_term in value_af:
            found.append((original_af, original_ag))

    if found:
        response = f"🔎 <b>Найдено {len(found)} результатов:</b>\n\n<pre>"

        for af, ag in found:
            name = af[:40]
            spaces = " " * (40 - len(name))
            response += f"{name}{spaces}{ag}\n"

            if len(response) > 3900:
                response += "</pre>"
                await update.message.reply_text(response, parse_mode="HTML")
                response = "<pre>"

        response += "</pre>"
        await update.message.reply_text(response, parse_mode="HTML")
    else:
        await update.message.reply_text(f"❌ Ничего не найдено по запросу '{search_term}'.")


# --- ЗАПУСК БОТА ---
def run_bot():
    """Запускает Telegram-бота"""
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("stats", stats))
    application.add_handler(CommandHandler("get_all", get_all))
    application.add_handler(CommandHandler("find", find))

    # Запускаем polling (бот сам будет забирать обновления)
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == '__main__':
    print("🚀 Бот запускается...")

    # Запускаем Flask для healthcheck в отдельном потоке
    threading.Thread(target=run_flask, daemon=True).start()

    # Запускаем бота
    run_bot()
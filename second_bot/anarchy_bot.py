import os
import requests
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
from dotenv import load_dotenv
from pathlib import Path

# Загрузка переменных окружения
env_path = Path(__file__).parent.parent / '.env'
load_dotenv(env_path)

TELEGRAM_BOT_TOKEN = os.getenv('SECOND_BOT_TOKEN')
CSV_URL = 'https://docs.google.com/spreadsheets/d/e/2PACX-1vSWZzQ4H8cNNvFc0Yxt0XQ9XHH8869jWMoC12z8DPNc1Xd02CqRlIdRx4PbqTCb0lHA9yDx8nSdqb_i/pub?output=csv'

def get_table_data():
    """Загружает CSV и возвращает список строк, находя данные под 'Актуальная таблица'"""
    try:
        response = requests.get(CSV_URL, timeout=15)
        response.raise_for_status()

        # Разбираем CSV-строку
        lines = response.text.strip().split('\n')
        # Разделяем по запятым (это простой вариант, но для Google CSV работает)
        data = [line.split(',') for line in lines]

        # Ищем строку с "Актуальная таблица"
        target_index = -1
        for i, row in enumerate(data):
            for cell in row:
                if 'Актуальная таблица' in cell:
                    target_index = i
                    break
            if target_index != -1:
                break

        if target_index == -1:
            return None, "❌ Не найдена строка 'Актуальная таблица'"

        # Берём всё, что ниже найденной строки
        result = data[target_index + 1:]

        # Убираем пустые строки в конце
        while result and not any(result[-1]):
            result.pop()

        if not result:
            return None, "❌ Под таблицей нет данных"

        return result, None
    except Exception as e:
        return None, f"❌ Ошибка загрузки: {e}"

# --- Обработчики команд (такие же, как у первого бота, но используют get_table_data) ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📊 Бот для чтения публичной CSV-таблицы\n\n"
        "Команды:\n/get_data - показать данные\n/find <текст> - поиск\n/stats - статистика"
    )

async def get_data(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data, error = get_table_data()
    if error:
        await update.message.reply_text(error)
        return

    response = "📊 Данные из таблицы:\n\n"
    for i, row in enumerate(data[:20], 1):
        response += f"{i}. {' | '.join(row)}\n"
        if len(response) > 4000:
            await update.message.reply_text(response)
            response = ""
    if response:
        await update.message.reply_text(response)

async def find(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("ℹ️ Укажите текст. Пример: /find рецепт")
        return

    search_term = ' '.join(context.args).lower()
    data, error = get_table_data()
    if error:
        await update.message.reply_text(error)
        return

    found = []
    for i, row in enumerate(data, 1):
        if any(search_term in cell.lower() for cell in row):
            found.append(f"{i}. {' | '.join(row)}")
            if len(found) >= 20:
                found.append("... и ещё строки")
                break

    if not found:
        await update.message.reply_text(f"❌ Ничего не найдено для '{search_term}'")
    else:
        await update.message.reply_text(f"🔎 Найдено:\n\n" + "\n".join(found))

async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data, error = get_table_data()
    if error:
        await update.message.reply_text(error)
        return
    await update.message.reply_text(f"📊 Всего строк с данными: {len(data)}")

def main():
    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("get_data", get_data))
    app.add_handler(CommandHandler("find", find))
    app.add_handler(CommandHandler("stats", stats))
    print("✅ Второй бот запущен")
    app.run_polling()

if __name__ == '__main__':
    main()
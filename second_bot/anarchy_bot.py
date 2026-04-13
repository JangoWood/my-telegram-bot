import os
import logging
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
import gspread
from gspread.auth import anonymous
from dotenv import load_dotenv
from pathlib import Path

# Загружаем переменные из корневого .env
env_path = Path(__file__).parent.parent / '.env'
load_dotenv(env_path)

# === НАСТРОЙКИ ===
TELEGRAM_BOT_TOKEN = os.getenv('SECOND_BOT_TOKEN')
SHEET_ID = '1ok9cZ782chtgjVRhvJPMo1Op3GNicWWVT0c_woHdF4E'
SHEET_NAME = 'Основа'
SEARCH_TEXT = 'Актуальная таблица'
# =================

logging.basicConfig(level=logging.INFO)


def get_table_data():
    """Находит ячейку 'Актуальная таблица' и возвращает данные под ней"""
    try:
        # Подключаемся к публичной таблице (без авторизации)
        gc = gspread.Client(auth=anonymous())
        sheet = gc.open_by_key(SHEET_ID)
        worksheet = sheet.worksheet(SHEET_NAME)

        # Ищем ячейку с текстом (регистр важен, но можно сделать .upper())
        cell = worksheet.find(SEARCH_TEXT)

        if not cell:
            return None, "❌ Не найдена ячейка с текстом 'Актуальная таблица'"

        # Данные начинаются со следующей строки
        start_row = cell.row + 1
        start_col = cell.col

        # Получаем все данные из таблицы
        all_data = worksheet.get_all_values()

        # Обрезаем данные: со start_row и до конца
        data_rows = all_data[start_row - 1:]  # -1 потому что индексация с 0

        # Убираем пустые строки в конце
        while data_rows and not any(data_rows[-1]):
            data_rows.pop()

        if not data_rows:
            return None, "❌ Под ячейкой 'Актуальная таблица' нет данных"

        return data_rows, None
    except Exception as e:
        logging.error(f"Ошибка: {e}")
        return None, f"❌ Ошибка доступа к таблице: {e}"


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📊 <b>Бот для чтения таблицы</b>\n\n"
        "Команды:\n"
        "/get_data - показать данные из таблицы\n"
        "/find <текст> - поиск по таблице\n"
        "/stats - статистика (кол-во строк и колонок)",
        parse_mode="HTML"
    )


async def get_data(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показывает данные из таблицы (первые 20 строк)"""
    data, error = get_table_data()

    if error:
        await update.message.reply_text(error)
        return

    if not data:
        await update.message.reply_text("❌ Нет данных для отображения")
        return

    # Формируем ответ (первые 20 строк)
    response = "📊 <b>Данные из таблицы</b>\n\n"
    response += "<pre>"

    for i, row in enumerate(data[:20], 1):
        # Показываем не больше 5 колонок для читаемости
        row_str = " | ".join([str(cell)[:30] for cell in row[:5]])
        response += f"{i:3}. {row_str}\n"

        if len(response) > 3900:
            response += "</pre>"
            await update.message.reply_text(response, parse_mode="HTML")
            response = "<pre>"

    response += "</pre>"

    if len(data) > 20:
        response += f"\n📌 <i>Показано 20 из {len(data)} строк</i>"

    await update.message.reply_text(response, parse_mode="HTML")


async def find(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Ищет текст по всем строкам таблицы"""
    if not context.args:
        await update.message.reply_text("ℹ️ Укажите текст для поиска. Пример: /find текст")
        return

    search_term = ' '.join(context.args).lower()
    data, error = get_table_data()

    if error:
        await update.message.reply_text(error)
        return

    if not data:
        await update.message.reply_text("❌ Нет данных для поиска")
        return

    # Поиск
    found = []
    for i, row in enumerate(data, 1):
        row_text = ' '.join([str(cell).lower() for cell in row])
        if search_term in row_text:
            # Показываем строку целиком
            row_str = " | ".join([str(cell)[:30] for cell in row[:5]])
            found.append(f"{i}. {row_str}")
            if len(found) >= 20:
                found.append("... и ещё строки")
                break

    if not found:
        await update.message.reply_text(f"❌ Ничего не найдено по запросу '{search_term}'")
        return

    response = f"🔎 <b>Найдено {len(found)} результатов:</b>\n\n<pre>"
    response += "\n".join(found)
    response += "</pre>"

    if len(response) > 4000:
        response = response[:4000] + "\n\n... (обрезано)"

    await update.message.reply_text(response, parse_mode="HTML")


async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показывает статистику по таблице"""
    data, error = get_table_data()

    if error:
        await update.message.reply_text(error)
        return

    if not data:
        await update.message.reply_text("❌ Нет данных")
        return

    # Определяем количество колонок (по максимальной строке)
    max_cols = max([len(row) for row in data]) if data else 0

    response = f"📊 <b>Статистика таблицы</b>\n\n"
    response += f"📋 Строк с данными: {len(data)}\n"
    response += f"📁 Колонок: {max_cols}\n"

    await update.message.reply_text(response, parse_mode="HTML")


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
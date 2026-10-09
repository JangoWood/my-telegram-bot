import os
from telegram.ext import Application, CommandHandler
from telegram.ext import InlineQueryHandler
from dotenv import load_dotenv
from pathlib import Path
import threading
from telegram.ext import CallbackQueryHandler
from telegram.ext import MessageHandler, filters

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

from utils.health import run_flask
from handlers.update_me import update_realm, handle_nickname, clan_callback
from handlers.equipment import enchant_command
from handlers.player_commands import cmd_command, trade_command
from handlers.stats import stats
from handlers.get import get_command
from handlers.get_data import get_data
from handlers.chat_id import chat_id
from handlers.help import help_command
from handlers.start import start
from handlers.craft import craft_command
from handlers.calculator_callback import calculator_callback
from handlers.profile import get_profile
from handlers.spec import spec_search
from handlers.find import find
from handlers.craft_callback import craft_callback
from services.craft_base_loader import load_craft_base
from handlers.button_callback import button_callback
from handlers.inline_search import inline_query
from handlers.war import start_war, stop_war, war_log

# ==================== ЗАГРУЗКА БАЗЫ КРАФТА ====================

CRAFT_BASE_FILE = Path(__file__).parent / 'craft_base.json'

# ==================== ЗАПУСК БОТА ====================

def main():
    print("🟢 Запуск бота...")
    craft_base, _ = load_craft_base(CRAFT_BASE_FILE)
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

    # Новый тестовый помощник по ОД. combat_war.py не используется.
    app.add_handler(CommandHandler("start_war", start_war))
    app.add_handler(CommandHandler("stop_war", stop_war))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND & filters.Regex(r"(?m)\bХод\s+\d+\s+👀"), war_log))

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
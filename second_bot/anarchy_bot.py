from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

TOKEN = "ТОКЕН_ТВОЕГО_ТЕСТОВОГО_БОТА"  # Создай через @BotFather

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Привет! Я второй бот в монорепозитории!")

app = Application.builder().token(TOKEN).build()
app.add_handler(CommandHandler("start", start))
app.run_polling()
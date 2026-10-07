from telegram import Update
from telegram.ext import ContextTypes


# Белый список чатов (ID чатов, где бот работает)
ALLOWED_CHATS = [
    -1003335956100,  # Чат 1 (например, группа "Анархия")
    -1003692246189,  # Чат 2 (например, группа "Крылья")
    -1004260632686,  # Чат 2 (например, группа "Наследие")
]

# Белый список пользователей (кто может писать боту в личку)
ALLOWED_USERS = [
    121597158,  # Твой Telegram ID (замени на реальный)
]


def is_chat_allowed(chat_id):
    """Проверяет, разрешён ли чат."""
    return chat_id in ALLOWED_CHATS


def is_user_allowed(user_id):
    """Проверяет, разрешён ли пользователь для личных сообщений."""
    return user_id in ALLOWED_USERS


def chat_restricted(func):
    """Команда работает только в разрешённых чатах или для разрешённых пользователей в личке."""

    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        # Если это инлайн-запрос — пропускаем
        if update.inline_query:
            return await func(update, context, *args, **kwargs)

        chat_id = update.effective_chat.id
        user_id = update.effective_user.id

        # Если чат в белом списке — разрешаем
        if is_chat_allowed(chat_id):
            return await func(update, context, *args, **kwargs)

        # Если это личный чат и пользователь в белом списке — разрешаем
        if update.effective_chat.type == 'private' and is_user_allowed(user_id):
            return await func(update, context, *args, **kwargs)

        # В личных сообщениях — подсказка
        if update.effective_chat.type == 'private':
            await update.message.reply_text(
                "🤖 <b>У вас нет доступа к боту в личных сообщениях.</b>\n\n"
                "Обратитесь к администратору для получения доступа.",
                parse_mode="HTML"
            )
        # В группах — игнорируем (молчим)
        return

    return wrapper

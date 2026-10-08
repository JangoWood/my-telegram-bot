"""Команда /prof — просмотр профиля игрока."""

from telegram import Update
from telegram.ext import ContextTypes

from utils.permissions import chat_restricted
from services.realm_sheet import (
    get_player_realm_by_name,
    get_player_realm_from_sheet,
)
from utils.realm_profile import format_realm_profile


@chat_restricted
async def get_profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показывает специализации игрока из таблицы Ремесло."""

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

    # Вариант 2: ответ на сообщение
    elif update.message.reply_to_message:
        replied_user = update.message.reply_to_message.from_user

        # Особый случай для @l1b_b1l
        if replied_user.username == 'l1b_b1l':
            sender = update.message.from_user

            if sender and sender.username:
                user_tag = f"@{sender.username}"
                is_self = True
            else:
                await update.message.reply_text(
                    "❓ Используйте /prof @username или "
                    "ответьте на сообщение игрока с username",
                    parse_mode="HTML"
                )
                return

        elif replied_user and replied_user.username:
            user_tag = f"@{replied_user.username}"

        else:
            await update.message.reply_text(
                "❌ У пользователя нет username.\n"
                "Попросите его установить username в настройках Telegram.",
                parse_mode="HTML"
            )
            return

    # Вариант 3: без аргументов — свой профиль
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
                "❌ Ваш профиль не найден в таблице Ремесло.\n\n"
                "📝 Чтобы добавиться: ответьте на сообщение "
                "с навыками командой /update_me",
                parse_mode="HTML"
            )
        else:
            await update.message.reply_text(
                f"❌ Профиль {user_tag} не найден в таблице Ремесло.\n\n"
                "Возможно, игрок ещё не обновил свои навыки через /update_me",
                parse_mode="HTML"
            )
        return

    response = format_realm_profile(player_data)

    await update.message.reply_text(
        response,
        parse_mode="HTML"
    )
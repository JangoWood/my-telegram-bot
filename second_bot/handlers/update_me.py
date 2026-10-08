"""Логика обновления профиля игрока через /update_me."""

from datetime import datetime

import pytz
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from services.realm_skills import parse_skills_from_text
from services.realm_sheet import update_player_realm


user_sessions = {}


async def update_realm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Шаг 1: получение навыков, запрос ника"""

    # Если команда не в ответ на сообщение — показываем инструкцию
    if not update.message.reply_to_message:
        await update.message.reply_text(
            "❌ <b>Как использовать /update_me</b>\n\n"
            "1️⃣ Отправьте в чат сообщение со своими навыками (скопируйте из игры)\n"
            "2️⃣ Нажмите «ответить» на это сообщение\n"
            "3️⃣ Напишите /update_me\n\n"
            "📝 <b>Пример сообщения с навыками:</b>\n"
            "⚒ Навык Крафтера: Подмастерье 2\n"
            "🎣 Навык Рыбалки: Подмастерье 1\n"
            "...",
            parse_mode="HTML"
        )
        return

    skills_text = update.message.reply_to_message.text
    skills = parse_skills_from_text(skills_text)

    if not skills:
        await update.message.reply_text(
            "❌ Не удалось распознать навыки.\n\n"
            "Убедитесь, что сообщение содержит строки вида:\n"
            "«Навык Крафтера: Подмастерье 2»",
            parse_mode="HTML"
        )
        return

    user = update.effective_user
    user_tag = f"@{user.username}" if user.username else None

    if not user_tag:
        await update.message.reply_text(
            "❌ У вас нет username в Telegram.\n\n"
            "Установите username в настройках Telegram.",
            parse_mode="HTML"
        )
        return

    # Сохраняем сессию
    user_sessions[user.id] = {
        'skills': skills,
        'user_tag': user_tag,
        'telegram_name': user.first_name,
        'skills_text': skills_text
    }

    # Шаг 2: просим ввести игровой ник
    await update.message.reply_text(
        "🤟🏼 <b>Введите ваш игровой ник</b>\n\n"
        "Например: Jango, Crazyrain34, Giz\n\n"
        "Просто напишите его в ответ на это сообщение.",
        parse_mode="HTML"
    )


async def handle_nickname(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Шаг 2: получаем игровой ник от пользователя"""

    # Игнорируем команды
    if update.message.text and update.message.text.startswith('/'):
        return

    user_id = update.effective_user.id

    if user_id not in user_sessions:
        # Не показываем ошибку, если сессии нет — просто игнорируем
        return

    nickname = update.message.text.strip()
    if not nickname:
        await update.message.reply_text("❌ Ник не может быть пустым. Попробуйте ещё раз.")
        return

    # Сохраняем ник
    user_sessions[user_id]['nickname'] = nickname

    # Шаг 3: показываем выбор клана
    keyboard = [
        [InlineKeyboardButton("🤟 Анархия", callback_data="clan_anarchy")],
        [InlineKeyboardButton("🤟🏾️ Наследие Анархии", callback_data="clan_legacy")],
        [InlineKeyboardButton("🤟🏼 Крылья Анархии", callback_data="clan_wings")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        "🏛️ <b>Выберите ваш клан</b>",
        parse_mode="HTML",
        reply_markup=reply_markup
    )


async def clan_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Шаг 3: получаем выбор клана и сохраняем всё в таблицу"""
    query = update.callback_query
    await query.answer()

    user_id = update.effective_user.id

    if user_id not in user_sessions:
        await query.edit_message_text(
            "❌ Сессия истекла или данные уже сохранены.\n\n"
            "Если данные не сохранились, начните заново: /update_me"
        )
        return

    clan_map = {
        'clan_anarchy': 'Анархия',
        'clan_legacy': 'Наследие Анархии',
        'clan_wings': 'Крылья Анархии'
    }
    clan = clan_map.get(query.data, 'Анархия')

    data = user_sessions.pop(user_id)
    nickname = data['nickname']
    skills = data['skills']
    user_tag = data['user_tag']

    # Сохраняем в таблицу
    moscow_tz = pytz.timezone('Europe/Moscow')
    now_moscow = datetime.now(moscow_tz)
    success = update_player_realm(user_tag, nickname, clan, skills, now_moscow)

    if success:
        response = f"✅ <b>Навыки сохранены!</b>\n\n"
        response += f"🎮 <b>Игровой ник:</b> {nickname}\n"
        response += f"🏛️ <b>Клан:</b> {clan}\n\n"
        response += f"⚒️ <b>Крафтер:</b> {skills.get('Крафтер', '—')}\n"
        response += f"🎣 <b>Рыбалка:</b> {skills.get('Рыбалка', '—')}\n"
        response += f"⛏️ <b>Шахтёр:</b> {skills.get('Шахтёр', '—')}\n"
        response += f"🏹 <b>Охота:</b> {skills.get('Охота', '—')}\n"
        response += f"🥨 <b>Кулинария:</b> {skills.get('Кулинария', '—')}\n"
        response += f"🧪 <b>Алхимия:</b> {skills.get('Алхимия', '—')}\n"
        response += f"🪔 <b>Плавильщик:</b> {skills.get('Плавильщик', '—')}\n"
        response += f"🌽 <b>Фермер:</b> {skills.get('Фермер', '—')}\n"
        response += f"\n📅 <b>Дата:</b> {now_moscow.strftime('%Y-%m-%d %H:%M:%S')}"

        await query.edit_message_text(response, parse_mode="HTML")
    else:
        # Если ошибка, возвращаем сессию обратно
        user_sessions[user_id] = data
        await query.edit_message_text(
            "❌ Ошибка сохранения. Попробуйте ещё раз /update_me"
        )



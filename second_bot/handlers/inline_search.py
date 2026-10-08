"""Inline-поиск игроков и карточек крафта."""

from telegram import Update
from telegram.ext import ContextTypes
from telegram import InlineQueryResultArticle, InputTextMessageContent

from utils.permissions import chat_restricted
from utils.get_craft import get_all_craft_search_items, build_get_card_text
from utils.craft_calculator import build_calculator_buttons
from utils.table_data import get_table_data


@chat_restricted
async def inline_query(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обрабатывает инлайн-запросы (@bot_name текст) — сразу показываем результат"""

    raw_query = update.inline_query.query.strip()
    query = raw_query.lower()

    # /get использует тот же inline-хендлер, но полностью изолирован префиксом "get ".
    if query == "get" or query.startswith("get "):
        craft_query = raw_query[3:].strip().lower()
        items = get_all_craft_search_items(context.application.bot_data.get("craft_base", {}))

        if not craft_query:
            results = [InlineQueryResultArticle(
                id="get_help",
                title="🔍 Введите название предмета",
                description=f"Поиск по {len(items)} карточкам крафта",
                input_message_content=InputTextMessageContent(
                    "🔎 Начни вводить название предмета для поиска."
                )
            )]
            await update.inline_query.answer(results, cache_time=0, is_personal=True)
            return

        found = []
        for index, (item, section) in enumerate(items):
            title = item.get('title', '')
            if craft_query in title.lower():
                context.user_data.setdefault('craft_calc_back', {})[str(item.get('id'))] = '__get__'
                found.append(InlineQueryResultArticle(
                    id=f"craft_get_{index}",
                    title=title[:64],
                    description=section[:128],
                    input_message_content=InputTextMessageContent(
                        build_get_card_text(item),
                        parse_mode="HTML"
                    ),
                    reply_markup=build_calculator_buttons(item.get('id'), 1)
                ))
                if len(found) >= 20:
                    break

        if not found:
            found = [InlineQueryResultArticle(
                id="craft_get_not_found",
                title=f"❌ Не найдено: {craft_query}",
                description="Попробуйте другое название",
                input_message_content=InputTextMessageContent(
                    f"❌ Предмет «{craft_query}» не найден."
                )
            )]

        await update.inline_query.answer(found, cache_time=0, is_personal=True)
        return

    if not query:
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

        if query in name.lower():
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

            result = InlineQueryResultArticle(
                id=f"player_{name}",
                title=f"🤟🏼 {name}",
                description=f"⚔️ {points} очков, 💰 {coins} монет",
                input_message_content=InputTextMessageContent(text, parse_mode="HTML")
            )
            found.append(result)

            if len(found) >= 20:
                break

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

    await update.inline_query.answer(found, cache_time=0)


import os
import json
import logging
import threading
from flask import Flask
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
import gspread
from google.oauth2.service_account import Credentials
from recipes import RECIPES, get_recipe, get_all_recipes
from telegram.ext import Application, CommandHandler
from telegram import BotCommand

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


def get_all_data(sheet):
    """Получает ВСЕ данные из колонок AF и AG, начиная со строки 5"""
    try:
        # Получаем все значения из колонки AF (начиная с 5 строки)
        all_af = sheet.col_values(32)  # AF = 32-я колонка
        all_ag = sheet.col_values(33)  # AG = 33-я колонка

        # Начинаем с 5 строки (индексы в Python: 0,1,2,3,4 -> строка 5)
        data = []
        for i in range(4, len(all_af)):  # i=4 это строка 5
            af_value = all_af[i].strip() if i < len(all_af) and all_af[i] else ""
            ag_value = all_ag[i].strip() if i < len(all_ag) and all_ag[i] else ""

            # Добавляем только строки, где есть значение в AF
            if af_value:
                data.append([af_value, ag_value])

        return data
    except Exception as e:
        print(f"Ошибка: {e}")
        return []


# --- КОМАНДЫ БОТА ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🍳 <b>Кулинарный помощник</b>\n\n"
        "Я помогу вам готовить блюда и следить за остатками на складе!\n\n"
        "📋 <b>Основные команды:</b>\n"
        "• /help — полный справочник команд\n"
        "• /cook <блюдо> <количество> — рассчитать ингредиенты\n"
        "• /get_all — посмотреть остатки на складе\n"
        "• /recipes — список всех рецептов\n\n"
        "🔍 <b>Попробуйте прямо сейчас:</b>\n"
        "<code>/cook рыба т1 5</code>\n\n"
        "📖 Отправьте /help для подробной инструкции",
        parse_mode="HTML"
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


def get_all_data(sheet):
    """Получает ВСЕ данные из колонок AF и AG (начиная со строки 5)"""
    try:
        # AF = колонка 32, AG = колонка 33
        all_af = sheet.col_values(32)  # Все строки колонки AF
        all_ag = sheet.col_values(33)  # Все строки колонки AG

        data = []
        # Начинаем с 4 индекса (что соответствует строке 5)
        for i in range(4, len(all_af)):
            af_value = all_af[i].strip() if i < len(all_af) and all_af[i] else ""
            ag_value = all_ag[i].strip() if i < len(all_ag) and all_ag[i] else ""

            # Добавляем только строки, где есть название товара
            if af_value:
                data.append([af_value, ag_value])
            else:
                # Если встретили пустую строку в AF — останавливаемся
                # (предполагаем, что данные идут подряд без пропусков)
                if len(data) > 0:
                    break

        print(f"✅ Найдено {len(data)} строк с данными")
        return data
    except Exception as e:
        print(f"❌ Ошибка при чтении: {e}")
        return []


async def get_all(update: Update, context: ContextTypes.DEFAULT_TYPE):
    sheet = get_google_sheet()
    if sheet is None:
        await update.message.reply_text("❌ Ошибка подключения к таблице.")
        return

    await update.message.reply_text("⏳ Загружаю данные...")

    data = get_all_data(sheet)

    if not data:
        await update.message.reply_text("Нет данных в таблице.")
        return

    response = "<pre>"

    for row in data:
        value_af = row[0] if len(row) > 0 else ""
        value_ag = row[1] if len(row) > 1 else ""

        if value_af:
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

    data = get_all_data(sheet)

    if not data:
        await update.message.reply_text("Нет данных для поиска.")
        return

    found = []
    for row in data:
        value_af = row[0].lower() if len(row) > 0 else ""
        original_af = row[0] if len(row) > 0 else ""
        original_ag = row[1] if len(row) > 1 else ""

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


async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    sheet = get_google_sheet()
    if sheet is None:
        await update.message.reply_text("❌ Ошибка подключения к таблице.")
        return

    data = get_all_data(sheet)

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


async def cook(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Рассчитывает ингредиенты для приготовления блюда"""
    if not context.args:
        await update.message.reply_text(
            "🍳 <b>Как пользоваться командой /cook</b>\n\n"
            "Отправьте: /cook <название блюда> <количество>\n\n"
            "📋 <b>Доступные блюда:</b>\n"
            "• Блюдо из рыбы [I]\n"
            "• Блюдо из мяса [I]\n"
            "• Аквельский обед [I]\n"
            "• Блюдо из рыбы [III]\n"
            "• Блюдо из мяса [III]\n"
            "• Аквельский обед [III]\n"
            "• Пастуший хлеб [I]\n"
            "• Чесночная похлебка [I]\n"
            "• Луковый суп [I]\n"
            "• Острый лечо [I]\n"
            "• Питательный салат\n\n"
            "Пример: <code>/cook Блюдо из рыбы [I] 5</code>",
            parse_mode="HTML"
        )
        return

    # Парсим команду
    command_text = ' '.join(context.args).lower()

    # Ищем количество
    parts = command_text.rsplit(' ', 1)
    if len(parts) == 2 and parts[1].isdigit():
        quantity = int(parts[1])
        recipe_name = parts[0].strip()
    else:
        quantity = 1
        recipe_name = command_text.strip()

    # Ищем рецепт
    recipe = get_recipe(recipe_name)

    if not recipe:
        await update.message.reply_text(
            f"❌ Рецепт '{recipe_name}' не найден.\n"
            f"Используйте /recipes для просмотра всех рецептов.",
            parse_mode="HTML"
        )
        return

    # Курс конвертации соли в золото
    SALT_TO_GOLD_RATIO = 10

    # Рассчитываем ингредиенты
    total_ingredients = {}
    for ingredient, amount in recipe["ingredients"].items():
        total_ingredients[ingredient] = amount * quantity

    # Формируем ответ
    response = f"🍳 <b>{recipe['name']}</b> — {quantity} шт.\n\n"
    response += "<b>📋 Требуемые ингредиенты:</b>\n"
    response += "<pre>\n"

    total_gold_cost = 0

    for ingredient, amount in total_ingredients.items():
        name = ingredient[:25]
        spaces = " " * (25 - len(name))

        # Если это соль — показываем альтернативу в золоте
        if "соль" in ingredient.lower():
            gold_cost = amount * SALT_TO_GOLD_RATIO
            total_gold_cost += gold_cost
            response += f"{name}{spaces}{amount}  (или 💰 {gold_cost} зол.)\n"
        else:
            response += f"{name}{spaces}{amount}\n"

    response += "</pre>"

    if total_gold_cost > 0:
        response += f"\n💰 <b>Альтернатива:</b> вместо соли можно потратить {total_gold_cost} золота\n"

    # Проверка наличия на складе
    sheet = get_google_sheet()
    if sheet:
        stock_data = get_all_data(sheet)
        stock_dict = {row[0]: int(row[1]) if row[1].isdigit() else 0 for row in stock_data if row[0]}

        response += "\n<b>✅ Проверка наличия:</b>\n"
        missing = []
        for ingredient, needed in total_ingredients.items():
            available = stock_dict.get(ingredient, 0)
            if available >= needed:
                response += f"  ✅ {ingredient}: {available} (достаточно)\n"
            else:
                response += f"  ❌ {ingredient}: {available} (нужно {needed})\n"
                missing.append(ingredient)

        if missing:
            response += f"\n⚠️ <b>Не хватает:</b> {', '.join(missing)}"

    await update.message.reply_text(response, parse_mode="HTML")


async def recipes_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показывает список доступных рецептов с синонимами"""
    response = "📖 <b>Доступные рецепты:</b>\n\n"

    for recipe in get_all_recipes():
        response += f"• <b>{recipe['name']}</b>\n"

        # Показываем синонимы, если есть
        if recipe.get("aliases"):
            aliases_str = ", ".join(recipe["aliases"])
            response += f"  └ <i>Синонимы:</i> {aliases_str}\n"

        # Показываем ингредиенты
        ingredients_list = ', '.join([f"{name} ({amount})" for name, amount in recipe["ingredients"].items()])
        response += f"  └ {ingredients_list}\n\n"

        if len(response) > 3500:
            await update.message.reply_text(response, parse_mode="HTML")
            response = ""

    if response:
        await update.message.reply_text(response, parse_mode="HTML")


def get_cw_data(sheet):
    """Получает данные для клановых войн из разных диапазонов"""
    try:
        cw_data = {
            "🍲 Готовая еда": [],
            "⭐ Таланты": [],
            "🧪 Зелья усиления": [],
            "🍎 Фрукты": [],
            "📦 Прочее": []
        }

        # Диапазоны для чтения
        ranges = {
            "🍲 Готовая еда": "E37:H47",
            "⭐ Таланты": "E51:H55",
            "🧪 Зелья усиления": "E57:H65",
            "🍎 Фрукты": "E68:H72",
            "📦 Прочее": "E75:H76"
        }

        # Список слов-маркеров, которые нужно пропускать
        skip_words = ["Еда", "Таланты", "Зелья", "Фрукты", "Прочее",
                      "Есть в КХ", "Нужно", "Не хватает", "Название"]

        for category, cell_range in ranges.items():
            data = sheet.get(cell_range)
            for row in data:
                if row and len(row) >= 4 and row[0]:  # Проверяем, что есть название
                    name = row[0].strip() if row[0] else ""

                    # Пропускаем строки-заголовки и пустые строки
                    if not name:
                        continue
                    if any(skip_word in name for skip_word in skip_words):
                        continue
                    if name in ["Еда", "Таланты", "Зелья", "Фрукты", "Прочее"]:
                        continue

                    # Получаем значения
                    in_stock = row[1].strip() if len(row) > 1 and row[1] else "0"
                    needed = row[2].strip() if len(row) > 2 and row[2] else "0"
                    missing = row[3].strip() if len(row) > 3 and row[3] else "0"

                    # Преобразуем в числа, если возможно
                    if in_stock == "" or in_stock == "-":
                        in_stock = "0"
                    if needed == "" or needed == "-":
                        needed = "0"
                    if missing == "" or missing == "-":
                        missing = "0"

                    item = {
                        "name": name,
                        "in_stock": in_stock,
                        "needed": needed,
                        "missing": missing
                    }
                    cw_data[category].append(item)

        return cw_data
    except Exception as e:
        print(f"Ошибка при чтении CW данных: {e}")
        return None


async def cw(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показывает информацию для клановых войн"""
    sheet = get_google_sheet()
    if sheet is None:
        await update.message.reply_text("❌ Ошибка подключения к таблице.")
        return

    await update.message.reply_text("⏳ Загружаю данные для клановых войн...")

    cw_data = get_cw_data(sheet)

    if not cw_data:
        await update.message.reply_text("❌ Не удалось загрузить данные. Проверьте структуру таблицы.")
        return

    response = "⚔️ <b>КЛАНОВЫЕ ВОЙНЫ</b> ⚔️\n"
    response += "📊 <b>Готовность ресурсов</b>\n"
    response += "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"

    for category, items in cw_data.items():
        if not items:
            continue

        response += f"<b>{category}</b>\n"
        response += "<pre>\n"
        # Увеличил ширину колонок для лучшего отображения
        response += f"{'Название':<30} {'В наличии':<10} {'Нужно':<8} {'Не хватает':<10}\n"
        response += "-" * 58 + "\n"

        for item in items:
            name = item["name"][:28]  # Увеличил до 28 символов
            spaces = " " * (28 - len(name))
            response += f"{name}{spaces} {item['in_stock']:<10} {item['needed']:<8} {item['missing']:<10}\n"

        response += "</pre>\n\n"

        # Защита от слишком длинных сообщений
        if len(response) > 3500:
            await update.message.reply_text(response, parse_mode="HTML")
            response = ""

    if response:
        await update.message.reply_text(response, parse_mode="HTML")


async def cw_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показывает краткую статистику готовности к КВ"""
    sheet = get_google_sheet()
    if sheet is None:
        await update.message.reply_text("❌ Ошибка подключения к таблице.")
        return

    cw_data = get_cw_data(sheet)

    if not cw_data:
        await update.message.reply_text("❌ Не удалось загрузить данные.")
        return

    response = "⚔️ <b>КВ: Сводка готовности</b> ⚔️\n\n"

    total_missing = 0
    total_needed = 0

    for category, items in cw_data.items():
        if not items:
            continue

        category_missing = 0
        category_needed = 0

        for item in items:
            needed = int(item["needed"]) if item["needed"].isdigit() else 0
            missing = int(item["missing"]) if item["missing"].isdigit() else 0
            category_needed += needed
            category_missing += missing

        total_needed += category_needed
        total_missing += category_missing

        # Определяем статус категории
        if category_missing == 0:
            status = "✅ ГОТОВО"
        elif category_missing <= category_needed * 0.3:
            status = "⚠️ ПОЧТИ ГОТОВО"
        else:
            status = "❌ НЕ ГОТОВО"

        response += f"<b>{category}</b>\n"
        response += f"  📦 Нужно всего: {category_needed}\n"
        response += f"  ❌ Не хватает: {category_missing}\n"
        response += f"  📊 Статус: {status}\n\n"

    response += "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
    response += f"<b>📊 ИТОГО:</b>\n"
    response += f"  📦 Нужно всего: {total_needed}\n"
    response += f"  ❌ Не хватает: {total_missing}\n"

    if total_missing == 0:
        response += "\n🎉 <b>ВСЁ ГОТОВО! Можно воевать!</b> 🎉"
    else:
        percent = int((total_needed - total_missing) / total_needed * 100) if total_needed > 0 else 0
        response += f"\n📈 <b>Готовность: {percent}%</b>"

    await update.message.reply_text(response, parse_mode="HTML")


async def cw_check(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показывает только то, чего не хватает для КВ"""
    sheet = get_google_sheet()
    if sheet is None:
        await update.message.reply_text("❌ Ошибка подключения к таблице.")
        return

    cw_data = get_cw_data(sheet)

    if not cw_data:
        await update.message.reply_text("❌ Не удалось загрузить данные.")
        return

    response = "⚠️ <b>ЧЕГО НЕ ХВАТАЕТ ДЛЯ КВ</b> ⚠️\n"
    response += "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"

    has_missing = False

    for category, items in cw_data.items():
        missing_items = [item for item in items if int(item["missing"]) > 0]

        if missing_items:
            has_missing = True
            response += f"<b>{category}</b>\n"
            response += "<pre>\n"
            response += f"{'Название':<30} {'Не хватает':<10}\n"
            response += "-" * 42 + "\n"

            for item in missing_items:
                name = item["name"][:28]
                spaces = " " * (28 - len(name))
                response += f"{name}{spaces} {item['missing']:<10}\n"

            response += "</pre>\n\n"

    if not has_missing:
        response += "🎉 <b>ВСЁ ЕСТЬ! Ничего не хватает!</b> 🎉"

    await update.message.reply_text(response, parse_mode="HTML")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показывает справочник всех команд бота"""
    help_text = """
🍳 <b>Кулинарный помощник — справочник команд</b>

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

📦 <b>Склад и остатки</b>

• <code>/get_all</code> — показать все остатки на складе
• <code>/find &lt;текст&gt;</code> — найти товар на складе
• <code>/stats</code> — статистика склада

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

🍳 <b>Приготовление блюд</b>

• <code>/cook &lt;блюдо&gt; &lt;количество&gt;</code> — рассчитать ингредиенты
• <code>/recipes</code> — список всех рецептов

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

⚔️ <b>Клановые войны</b>

• <code>/cw</code> — полная таблица готовности к КВ
• <code>/cw_stats</code> — краткая сводка готовности к КВ

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

📝 <b>Доступные рецепты и синонимы</b>

🐟 Рыба т1 / рыба 1 — Блюдо из рыбы [I]
🐟 Рыба т3 / рыба 3 — Блюдо из рыбы [III]
🥩 Мясо т1 / мясо 1 — Блюдо из мяса [I]
🥩 Мясо т3 / мясо 3 — Блюдо из мяса [III]
🍲 Аквел т1 / аквел 1 — Аквельский обед [I]
🍲 Аквел т3 / аквел 3 — Аквельский обед [III]
🍞 Хлеб — Пастуший хлеб [I]
🧄 Чеснок — Чесночная похлебка [I]
🧅 Суп / лук — Луковый суп [I]
🌶 Лечо — Острый лечо [I]
🥗 Салат — Питательный салат

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

💡 <b>Советы:</b>
• Количество можно не указывать — будет 1 порция
• Вместо соли можно использовать золото (1 соль = 10 зол.)
• Бот показывает наличие на складе автоматически
• /cw_stats покажет общую готовность к КВ
"""
    await update.message.reply_text(help_text, parse_mode="HTML")


# --- ЗАПУСК БОТА ---
def run_bot():
    """Запускает Telegram-бота"""
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    # ... настройка меню команд ...

    # Добавляем обработчики команд
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("stats", stats))
    application.add_handler(CommandHandler("get_all", get_all))
    application.add_handler(CommandHandler("find", find))
    application.add_handler(CommandHandler("recipes", recipes_list))
    application.add_handler(CommandHandler("cook", cook))

    # НОВЫЕ КОМАНДЫ
    application.add_handler(CommandHandler("cw", cw))
    application.add_handler(CommandHandler("cw_stats", cw_stats))
    application.add_handler(CommandHandler("cw_check", cw_check))

    # Запускаем polling
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == '__main__':
    print("🚀 Бот запускается...")

    # Запускаем Flask для healthcheck в отдельном потоке
    threading.Thread(target=run_flask, daemon=True).start()

    # Запускаем бота
    run_bot()

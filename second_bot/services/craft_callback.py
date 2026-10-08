"""Обработчик callback-кнопок команды /craft.

Логика вынесена из anarchy_bot.py без изменения поведения.
"""

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from services.craft_menu import (
    get_grade_by_idx,
    get_class_by_idx,
    count_all_equipment,
    count_all_instruments,
    count_all_cooking,
    count_all_alchemy,
    build_grades_keyboard,
    build_instruments_keyboard,
    build_cooking_keyboard,
    build_alchemy_keyboard,
    build_classes_keyboard,
    build_class_items_keyboard,
    build_instrument_items_keyboard,
    build_cooking_items_keyboard,
    build_alchemy_category_keyboard,
)
from services.craft_calculator import build_calculator_buttons


async def handle_craft_callback(update: Update, context: ContextTypes.DEFAULT_TYPE, craft_base):
    """Обработчик всех callback-кнопок /craft"""
    query = update.callback_query
    await query.answer()

    data = query.data
    parts = data.split(':')

    # ==================== ВЫБОР РАЗДЕЛА ====================
    if parts[0] == 'craft_section' and len(parts) == 2:
        if parts[1] == 'equip':
            await query.edit_message_text(
                "🎒 <b>Экипировка — выбери грейд:</b>",
                parse_mode="HTML",
                reply_markup=build_grades_keyboard(craft_base)
            )
            return
        elif parts[1] == 'instr':
            await query.edit_message_text(
                "⚒️ <b>Инструменты — выбери тип:</b>",
                parse_mode="HTML",
                reply_markup=build_instruments_keyboard(craft_base)
            )
            return
        elif parts[1] == 'cook':
            await query.edit_message_text(
                "🥨 <b>Кулинария — выбери раздел:</b>",
                parse_mode="HTML",
                reply_markup=build_cooking_keyboard(craft_base)
            )
            return

    # ==================== АЛХИМИЯ ====================
    if parts[0] == 'craft_section' and len(parts) == 2 and parts[1] == 'alchemy':
        alchemy = craft_base.get('alchemy', {})
        if not alchemy:
            await query.edit_message_text(
                "❌ Алхимия не найдена в craft_base.json.",
                parse_mode="HTML"
            )
            return

        await query.edit_message_text(
            "🧪 <b>Алхимия — выбери раздел:</b>",
            parse_mode="HTML",
            reply_markup=build_alchemy_keyboard(craft_base)
        )
        return

    # ==================== ВЫБОР КАТЕГОРИИ АЛХИМИИ ====================
    if parts[0] == 'craft_ag' and len(parts) == 2:
        try:
            category_idx = int(parts[1])
        except ValueError:
            await query.edit_message_text("❌ Некорректные данные.")
            return

        alchemy = craft_base.get('alchemy', {})
        categories = list(alchemy.keys())
        if not (0 <= category_idx < len(categories)):
            await query.edit_message_text("❌ Категория не найдена.")
            return

        markup, category, has_subgroups, icon = build_alchemy_category_keyboard(
            craft_base, category_idx
        )
        if has_subgroups:
            text = f"{icon} <b>{category} — выбери подгруппу:</b>"
        else:
            text = f"🧪 <b>{category}</b> — выбери рецепт:"

        await query.edit_message_text(
            text,
            parse_mode="HTML",
            reply_markup=markup
        )
        return

    # ==================== ПОДГРУППА АЛХИМИИ ====================
    if parts[0] == 'craft_as' and len(parts) == 3:
        try:
            category_idx = int(parts[1])
        except ValueError:
            await query.edit_message_text("❌ Некорректные данные.")
            return

        alchemy = craft_base.get('alchemy', {})
        categories = list(alchemy.keys())
        if not (0 <= category_idx < len(categories)):
            await query.edit_message_text("❌ Категория не найдена.")
            return

        category = categories[category_idx]
        items = alchemy.get(category, [])
        subgroups = []
        seen_subgroups = set()
        for item in items:
            subcategory = item.get('subcategory')
            if subcategory and subcategory not in seen_subgroups:
                seen_subgroups.add(subcategory)
                subgroups.append(subcategory)

        sub_idx = parts[2]
        if sub_idx == 'ungrouped':
            selected_items = [(i, item) for i, item in enumerate(items) if not item.get('subcategory')]
            subgroup_title = 'Прочие ресурсы'
        else:
            try:
                sub_idx_int = int(sub_idx)
            except ValueError:
                await query.edit_message_text("❌ Подгруппа не найдена.")
                return
            if not (0 <= sub_idx_int < len(subgroups)):
                await query.edit_message_text("❌ Подгруппа не найдена.")
                return
            subgroup_title = subgroups[sub_idx_int]
            selected_items = [(i, item) for i, item in enumerate(items) if item.get('subcategory') == subgroup_title]

        subgroup_icons = {
            'Таланты': '💟',
            'Очищение камня': '🌡🎆',
            'Элексиры здоровья': '🧪',
            'Антидоты': '🧪',
            'Усиление': '🌡',
            'Заточки': '🔖',
            'Телепорты': '🗞',
            'Трансмутация': '📜',
            'Алхимия [IV+]': '🧪',
            'Алхимия [IV]': '🧪',
            'Алхимия [III+]': '🧪',
            'Алхимия [III]': '🧪',
            'Материя': 'Ⓜ️',
        }

        buttons = []
        for item_idx, item in selected_items:
            buttons.append([InlineKeyboardButton(
                item.get('title', 'Без названия')[:60],
                callback_data=f"craft_ai:{category_idx}:{item_idx}"
            )])

        buttons.append([InlineKeyboardButton(
            "⬅️ Назад",
            callback_data=f"craft_ag:{category_idx}"
        )])

        await query.edit_message_text(
            f"{subgroup_icons.get(subgroup_title, '🧪')} <b>{subgroup_title}</b> — выбери рецепт:",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(buttons)
        )
        return

    # ==================== РЕЦЕПТ АЛХИМИИ ====================
    if parts[0] == 'craft_ai' and len(parts) == 3:
        try:
            category_idx = int(parts[1])
            item_idx = int(parts[2])
        except ValueError:
            await query.edit_message_text("❌ Некорректные данные.")
            return

        alchemy = craft_base.get('alchemy', {})
        categories = list(alchemy.keys())
        if not (0 <= category_idx < len(categories)):
            await query.edit_message_text("❌ Категория не найдена.")
            return

        category = categories[category_idx]
        items = alchemy.get(category, [])
        if not (0 <= item_idx < len(items)):
            await query.edit_message_text("❌ Рецепт не найден.")
            return

        item = items[item_idx]
        text = f"<b>{item.get('title', 'Без названия')}</b>\n\n"

        if item.get('where'):
            text += f"📍 <b>Где:</b> {item['where']}\n\n"

        if item.get('craft_block'):
            text += "<b>Ресурсы для крафта:</b>\n"
            text += item['craft_block'] + "\n\n"

        if item.get('resources_block'):
            text += "<b>📊 Все необходимые ресурсы для крафта:</b>\n"
            text += f"<blockquote expandable>{item['resources_block']}</blockquote>\n\n"

        if item.get('energy'):
            text += f"<b>{item['energy']}</b>"

        # Возврат должен вести в ту подгруппу, из которой открыт рецепт.
        # Например, «Антидот архонта» → 🧪 Антидоты, а не общий раздел «Зелья».
        subcategory = item.get('subcategory')
        if subcategory:
            subgroups = []
            seen_subgroups = set()
            for candidate in items:
                candidate_subcategory = candidate.get('subcategory')
                if candidate_subcategory and candidate_subcategory not in seen_subgroups:
                    seen_subgroups.add(candidate_subcategory)
                    subgroups.append(candidate_subcategory)

            if subcategory in subgroups:
                back_cb = f"craft_as:{category_idx}:{subgroups.index(subcategory)}"
            else:
                back_cb = f"craft_ag:{category_idx}"
        else:
            back_cb = f"craft_ag:{category_idx}"

        context.user_data.setdefault('craft_calc_back', {})[str(item.get('id'))] = back_cb
        buttons = build_calculator_buttons(item.get('id'), 1, back_cb).inline_keyboard

        if len(text) > 4000:
            text = text[:3997] + "..."

        await query.edit_message_text(
            text,
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(buttons)
        )
        return

    # ==================== ВЫБОР ГРУППЫ ИНСТРУМЕНТОВ ====================
    if parts[0] == 'craft_ig' and len(parts) == 2:
        try:
            group_idx = int(parts[1])
        except ValueError:
            await query.edit_message_text("❌ Некорректные данные.")
            return

        instruments = craft_base.get('instruments', {})
        groups = instruments.get('groups', [])
        if not (0 <= group_idx < len(groups)):
            await query.edit_message_text("❌ Группа не найдена.")
            return

        group = groups[group_idx]

        await query.edit_message_text(
            f"⚒️ <b>{group['name']}</b>\n\nВыбери инструмент:",
            parse_mode="HTML",
            reply_markup=build_instrument_items_keyboard(group, group_idx)
        )
        return

    # ==================== ВЫБОР ИНСТРУМЕНТА ====================
    if parts[0] == 'craft_ii' and len(parts) == 3:
        try:
            group_idx = int(parts[1])
            item_idx = int(parts[2])
        except ValueError:
            await query.edit_message_text("❌ Некорректные данные.")
            return

        instruments = craft_base.get('instruments', {})
        groups = instruments.get('groups', [])
        if not (0 <= group_idx < len(groups)):
            await query.edit_message_text("❌ Группа не найдена.")
            return

        group = groups[group_idx]
        items = group.get('items', [])
        if not (0 <= item_idx < len(items)):
            await query.edit_message_text("❌ Инструмент не найден.")
            return

        item = items[item_idx]

        # Формируем сообщение (у инструментов нет resources_block)
        text = f"<b>{item['title']}</b>\n\n"

        if item.get('craft_block'):
            text += "<b>Ресурсы для крафта:</b>\n"
            text += item['craft_block'] + "\n\n"

        if item.get('energy'):
            text += f"<b>{item['energy']}</b>"

        back_cb = f"craft_ig:{group_idx}"
        context.user_data.setdefault('craft_calc_back', {})[str(item.get('id'))] = back_cb
        buttons = build_calculator_buttons(item.get('id'), 1, back_cb).inline_keyboard

        if len(text) > 4000:
            text = text[:3997] + "..."

        await query.edit_message_text(
            text,
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(buttons)
        )
        return

    # ==================== ВЫБОР ГРЕЙДА ====================
    if parts[0] == 'craft_g' and len(parts) == 2:
        try:
            grade_idx = int(parts[1])
        except ValueError:
            await query.edit_message_text("❌ Некорректные данные.")
            return

        grade = get_grade_by_idx(grade_idx, craft_base)
        if not grade:
            await query.edit_message_text("❌ Грейд не найден.")
            return

        classes = grade.get('classes', [])
        if not classes:
            await query.edit_message_text(
                f"🎒 <b>{grade['name']}</b>\n\nВ этом грейде пока нет классов.",
                parse_mode="HTML"
            )
            return

        buttons = build_classes_keyboard(classes, grade_idx)

        await query.edit_message_text(
            f"🎒 <b>{grade['name']}</b>\n\nВыбери класс:",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(buttons)
        )
        return

    # ==================== ВЫБОР КЛАССА ====================
    if parts[0] == 'craft_c' and len(parts) == 3:
        try:
            grade_idx = int(parts[1])
            class_idx = int(parts[2])
        except ValueError:
            await query.edit_message_text("❌ Некорректные данные.")
            return

        grade = get_grade_by_idx(grade_idx, craft_base)
        cls = get_class_by_idx(grade_idx, class_idx, craft_base)
        if not grade or not cls:
            await query.edit_message_text("❌ Класс не найден.")
            return

        buttons = build_class_items_keyboard(cls, grade_idx, class_idx)

        await query.edit_message_text(
            f"🎒 <b>{grade['name']}</b>\n📁 <b>{cls['name']}</b>\n\nВыбери:",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(buttons)
        )
        return

    # ==================== НАЗАД К ГЛАВНОМУ МЕНЮ ====================
    if parts[0] == 'craft_back' and len(parts) == 2 and parts[1] == 'main':
        keyboard = [
            [
                InlineKeyboardButton(f"🎒 Экипировка ({count_all_equipment(craft_base)})", callback_data="craft_section:equip"),
                InlineKeyboardButton(f"⚒️ Инструменты ({count_all_instruments(craft_base)})", callback_data="craft_section:instr"),
            ],
            [
                InlineKeyboardButton(f"🥨 Кулинария ({count_all_cooking(craft_base)})", callback_data="craft_section:cook"),
                InlineKeyboardButton(f"🧪 Алхимия ({count_all_alchemy(craft_base)})", callback_data="craft_section:alchemy"),
            ]
        ]
        await query.edit_message_text(
            "⚒️ <b>Крафт — выбери раздел:</b>",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return

    # ==================== НАЗАД К ГРЕЙДАМ ====================
    if parts[0] == 'craft_back' and len(parts) == 2 and parts[1] == 'grades':
        await query.edit_message_text(
            "🎒 <b>Экипировка — выбери грейд:</b>",
            parse_mode="HTML",
            reply_markup=build_grades_keyboard(craft_base)
        )
        return

    # ==================== ВЫБОР ГРУППЫ ====================
    if parts[0] == 'craft_gr' and len(parts) == 4:
        try:
            grade_idx = int(parts[1])
            class_idx = int(parts[2])
            group_idx = int(parts[3])
        except ValueError:
            await query.edit_message_text("❌ Некорректные данные.")
            return

        grade = get_grade_by_idx(grade_idx, craft_base)
        cls = get_class_by_idx(grade_idx, class_idx, craft_base)
        if not grade or not cls or 'groups' not in cls:
            await query.edit_message_text("❌ Группа не найдена.")
            return

        groups = cls['groups']
        if not (0 <= group_idx < len(groups)):
            await query.edit_message_text("❌ Группа не найдена.")
            return

        group = groups[group_idx]
        buttons = []
        row = []

        # Сначала подгруппы (если есть)
        subgroups = group.get('subgroups', [])
        for i, subgroup in enumerate(subgroups):
            row.append(InlineKeyboardButton(
                f"{subgroup['name']} ({len(subgroup.get('items', []))})",
                callback_data=f"craft_sg:{grade_idx}:{class_idx}:{group_idx}:{i}"
            ))
            if len(row) == 2:
                buttons.append(row)
                row = []
        if row:
            buttons.append(row)
            row = []

        # Затем прямые предметы группы
        items = group.get('items', [])
        for i, item in enumerate(items):
            label = item['title'][:60]
            buttons.append([InlineKeyboardButton(
                label,
                callback_data=f"craft_i:{grade_idx}:{class_idx}:{group_idx}:-1:{i}"
            )])

        # Кнопка «Назад» на класс
        buttons.append([InlineKeyboardButton(
            "⬅️ Назад",
            callback_data=f"craft_c:{grade_idx}:{class_idx}"
        )])

        await query.edit_message_text(
            f"🎒 <b>{grade['name']}</b>\n📁 <b>{cls['name']}</b>\n📂 <b>{group['name']}</b>\n\nВыбери:",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(buttons)
        )
        return

    # ==================== ВЫБОР ПОДГРУППЫ ====================
    if parts[0] == 'craft_sg' and len(parts) == 5:
        try:
            grade_idx = int(parts[1])
            class_idx = int(parts[2])
            group_idx = int(parts[3])
            subgroup_idx = int(parts[4])
        except ValueError:
            await query.edit_message_text("❌ Некорректные данные.")
            return

        grade = get_grade_by_idx(grade_idx, craft_base)
        cls = get_class_by_idx(grade_idx, class_idx, craft_base)
        if not grade or not cls or 'groups' not in cls:
            await query.edit_message_text("❌ Подгруппа не найдена.")
            return

        groups = cls['groups']
        if not (0 <= group_idx < len(groups)):
            await query.edit_message_text("❌ Подгруппа не найдена.")
            return

        group = groups[group_idx]
        subgroups = group.get('subgroups', [])
        if not (0 <= subgroup_idx < len(subgroups)):
            await query.edit_message_text("❌ Подгруппа не найдена.")
            return

        subgroup = subgroups[subgroup_idx]
        items = subgroup.get('items', [])

        buttons = []
        for i, item in enumerate(items):
            label = item['title'][:60]
            buttons.append([InlineKeyboardButton(
                label,
                callback_data=f"craft_i:{grade_idx}:{class_idx}:{group_idx}:{subgroup_idx}:{i}"
            )])

        # Кнопка «Назад» на группу
        buttons.append([InlineKeyboardButton(
            "⬅️ Назад",
            callback_data=f"craft_gr:{grade_idx}:{class_idx}:{group_idx}"
        )])

        await query.edit_message_text(
            f"🎒 <b>{grade['name']}</b>\n📁 <b>{cls['name']}</b>\n📂 <b>{group['name']}</b>\n📄 <b>{subgroup['name']}</b>\n\nВыбери предмет:",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(buttons)
        )
        return

    # ==================== ВЫБОР ПРЕДМЕТА ====================
    if parts[0] == 'craft_i' and len(parts) == 6:
        try:
            grade_idx = int(parts[1])
            class_idx = int(parts[2])
            group_idx = int(parts[3])
            subgroup_idx = int(parts[4])
            item_idx = int(parts[5])
        except ValueError:
            await query.edit_message_text("❌ Некорректные данные.")
            return

        grade = get_grade_by_idx(grade_idx, craft_base)
        cls = get_class_by_idx(grade_idx, class_idx, craft_base)
        if not grade or not cls:
            await query.edit_message_text("❌ Предмет не найден.")
            return

        item = None

        # Определяем путь
        if group_idx == -1:
            # Плоский класс
            items = cls.get('items', [])
            if 0 <= item_idx < len(items):
                item = items[item_idx]
        else:
            # С группами
            groups = cls.get('groups', [])
            if not (0 <= group_idx < len(groups)):
                await query.edit_message_text("❌ Группа не найдена.")
                return
            group = groups[group_idx]

            if subgroup_idx == -1:
                # Прямой предмет группы
                items = group.get('items', [])
                if 0 <= item_idx < len(items):
                    item = items[item_idx]
            else:
                # Предмет подгруппы
                subgroups = group.get('subgroups', [])
                if not (0 <= subgroup_idx < len(subgroups)):
                    await query.edit_message_text("❌ Подгруппа не найдена.")
                    return
                subgroup = subgroups[subgroup_idx]
                items = subgroup.get('items', [])
                if 0 <= item_idx < len(items):
                    item = items[item_idx]

        if not item:
            await query.edit_message_text("❌ Предмет не найден.")
            return

        # Формируем сообщение
        text = f"<b>{item['title']}</b>\n\n"

        if item.get('craft_block'):
            text += "<b>Ресурсы для крафта:</b>\n"
            text += item['craft_block'] + "\n\n"

        if item.get('resources_block'):
            text += "<b>📊 Все необходимые ресурсы для крафта:</b>\n"
            text += f"<blockquote expandable>{item['resources_block']}</blockquote>\n\n"

        if item.get('energy'):
            text += f"<b>{item['energy']}</b>"

        # Кнопка «Назад»
        if group_idx == -1:
            back_cb = f"craft_c:{grade_idx}:{class_idx}"
        elif subgroup_idx == -1:
            back_cb = f"craft_gr:{grade_idx}:{class_idx}:{group_idx}"
        else:
            back_cb = f"craft_sg:{grade_idx}:{class_idx}:{group_idx}:{subgroup_idx}"

        # Для раздела «Экипировка» калькулятор отключён.
        buttons = [[InlineKeyboardButton("⬅️ Назад", callback_data=back_cb)]]

        # Telegram ограничивает 4096 символов, режем если больше
        if len(text) > 4000:
            text = text[:3997] + "..."

        await query.edit_message_text(
            text,
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(buttons)
        )
        return
    # ==================== ВЫБОР ГРУППЫ КУЛИНАРИИ ====================
    if parts[0] == 'craft_cg' and len(parts) == 2:
        try:
            group_idx = int(parts[1])
        except ValueError:
            await query.edit_message_text("❌ Некорректные данные.")
            return

        cooking = craft_base.get('cooking', {})
        groups = cooking.get('groups', [])
        if not (0 <= group_idx < len(groups)):
            await query.edit_message_text("❌ Группа не найдена.")
            return

        group = groups[group_idx]

        await query.edit_message_text(
            f"🥨 <b>{group['name']}</b>\n\nВыбери блюдо:",
            parse_mode="HTML",
            reply_markup=build_cooking_items_keyboard(group, group_idx)
        )
        return

    # ==================== ВЫБОР БЛЮДА ====================
    if parts[0] == 'craft_ci' and len(parts) == 3:
        try:
            group_idx = int(parts[1])
            item_idx = int(parts[2])
        except ValueError:
            await query.edit_message_text("❌ Некорректные данные.")
            return

        cooking = craft_base.get('cooking', {})
        groups = cooking.get('groups', [])
        if not (0 <= group_idx < len(groups)):
            await query.edit_message_text("❌ Группа не найдена.")
            return

        group = groups[group_idx]
        items = group.get('items', [])
        if not (0 <= item_idx < len(items)):
            await query.edit_message_text("❌ Блюдо не найдено.")
            return

        item = items[item_idx]

        text = f"<b>{item['title']}</b>\n\n"

        if item.get('craft_block'):
            text += "<b>Ресурсы для крафта:</b>\n"
            text += item['craft_block'] + "\n\n"

        if item.get('resources_block'):
            text += "<b>📊 Все необходимые ресурсы для крафта:</b>\n"
            text += f"<blockquote expandable>{item['resources_block']}</blockquote>\n\n"

        if item.get('energy'):
            text += f"<b>{item['energy']}</b>"

        back_cb = f"craft_cg:{group_idx}"
        context.user_data.setdefault('craft_calc_back', {})[str(item.get('id'))] = back_cb
        buttons = build_calculator_buttons(item.get('id'), 1, back_cb).inline_keyboard

        if len(text) > 4000:
            text = text[:3997] + "..."

        await query.edit_message_text(
            text,
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(buttons)
        )
        return

    # ==================== ЗАГЛУШКА ====================
    await query.edit_message_text("⏳ В разработке.")


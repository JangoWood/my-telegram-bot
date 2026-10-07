from telegram import InlineKeyboardButton, InlineKeyboardMarkup

def get_grade_by_idx(idx, craft_base):
    """Возвращает грейд по индексу"""
    grades = craft_base.get('grades', [])
    if 0 <= idx < len(grades):
        return grades[idx]
    return None


def get_class_by_idx(grade_idx, class_idx, craft_base):
    """Возвращает класс по индексам"""
    grade = get_grade_by_idx(grade_idx, craft_base)
    if not grade:
        return None
    classes = grade.get('classes', [])
    if 0 <= class_idx < len(classes):
        return classes[class_idx]
    return None


def count_grade_items(grade):
    """Количество рецептов/предметов в грейде."""
    total = len(grade.get('items', []))
    for cls in grade.get('classes', []):
        total += len(cls.get('items', []))
        for group in cls.get('groups', []):
            total += len(group.get('items', []))
    return total


def count_instrument_items(group):
    return len(group.get('items', []))


def count_cooking_items(group):
    return len(group.get('items', []))


def count_group_items(group):
    """Количество предметов в группе, включая её подгруппы."""
    total = len(group.get('items', []))
    for subgroup in group.get('subgroups', []):
        total += len(subgroup.get('items', []))
    return total


def count_class_items(cls):
    """Количество предметов в классе, включая группы и подгруппы."""
    if cls.get('groups'):
        return sum(count_group_items(group) for group in cls.get('groups', []))
    return len(cls.get('items', []))


def count_all_equipment(craft_base):
    return sum(count_grade_items(grade) for grade in craft_base.get('grades', []))


def count_all_instruments(craft_base):
    return sum(count_instrument_items(group) for group in craft_base.get('instruments', {}).get('groups', []))


def count_all_cooking(craft_base):
    return sum(count_cooking_items(group) for group in craft_base.get('cooking', {}).get('groups', []))


def count_all_alchemy(craft_base):
    return sum(len(items) for items in craft_base.get('alchemy', {}).values())


def build_grades_keyboard(craft_base):
    """Кнопки выбора грейда (по 2 в ряд)"""
    grades = craft_base.get('grades', [])
    buttons = []
    row = []
    for i, grade in enumerate(grades):
        row.append(InlineKeyboardButton(
            f"🎒 {grade['name']} ({count_grade_items(grade)})",
            callback_data=f"craft_g:{i}"
        ))
        if len(row) == 2:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    buttons.append([InlineKeyboardButton(
        "⬅️ Назад",
        callback_data="craft_back:main"
    )])
    return InlineKeyboardMarkup(buttons)

def build_instruments_keyboard(craft_base):
    """Кнопки выбора группы инструментов (по 2 в ряд)"""
    instruments = craft_base.get('instruments', {})
    groups = instruments.get('groups', [])
    buttons = []
    row = []
    for i, group in enumerate(groups):
        row.append(InlineKeyboardButton(
            f"{group['name']} ({count_instrument_items(group)})",
            callback_data=f"craft_ig:{i}"
        ))
        if len(row) == 2:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    buttons.append([InlineKeyboardButton(
        "⬅️ Назад",
        callback_data="craft_back:main"
    )])
    return InlineKeyboardMarkup(buttons)



def build_cooking_keyboard(craft_base):
    """Кнопки выбора группы кулинарии (по 2 в ряд)."""
    cooking = craft_base.get('cooking', {})
    groups = cooking.get('groups', [])
    buttons = []
    row = []
    for i, group in enumerate(groups):
        row.append(InlineKeyboardButton(
            f"{group['name']} ({count_cooking_items(group)})",
            callback_data=f"craft_cg:{i}"
        ))
        if len(row) == 2:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    buttons.append([InlineKeyboardButton(
        "⬅️ Назад",
        callback_data="craft_back:main"
    )])
    return InlineKeyboardMarkup(buttons)


def build_alchemy_keyboard(craft_base):
    """Кнопки выбора категории алхимии."""
    alchemy = craft_base.get('alchemy', {})
    buttons = []
    category_icons = {
        'Зелья': '🧪',
        'Свитки': '📜',
        'Ресурсы': '♻️',
        'Прочее': '🧩',
    }
    categories = list(alchemy.keys())
    for category_idx, category in enumerate(categories):
        icon = category_icons.get(category, '🧪')
        buttons.append([InlineKeyboardButton(
            f"{icon} {category} ({len(alchemy[category])})",
            callback_data=f"craft_ag:{category_idx}"
        )])
    buttons.append([InlineKeyboardButton(
        "⬅️ Назад",
        callback_data="craft_back:main"
    )])
    return InlineKeyboardMarkup(buttons)


def build_classes_keyboard(classes, grade_idx):
    """Кнопки выбора класса в грейде."""
    buttons = []
    row = []
    for i, cls in enumerate(classes):
        row.append(InlineKeyboardButton(
            f"{cls['name']} ({count_class_items(cls)})",
            callback_data=f"craft_c:{grade_idx}:{i}"
        ))
        if len(row) == 2:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    buttons.append([InlineKeyboardButton(
        "⬅️ Назад",
        callback_data="craft_back:grades"
    )])
    return buttons


def build_class_items_keyboard(cls, grade_idx, class_idx):
    """Кнопки содержимого класса: группы или плоские предметы."""
    buttons = []
    row = []

    if cls.get('groups'):
        for i, group in enumerate(cls['groups']):
            row.append(InlineKeyboardButton(
                f"{group['name']} ({count_group_items(group)})",
                callback_data=f"craft_gr:{grade_idx}:{class_idx}:{i}"
            ))
            if len(row) == 2:
                buttons.append(row)
                row = []
        if row:
            buttons.append(row)
    elif cls.get('items'):
        for i, item in enumerate(cls['items']):
            buttons.append([InlineKeyboardButton(
                item['title'][:60],
                callback_data=f"craft_i:{grade_idx}:{class_idx}:-1:-1:{i}"
            )])

    buttons.append([InlineKeyboardButton(
        "⬅️ Назад",
        callback_data=f"craft_g:{grade_idx}"
    )])
    return buttons

def build_instrument_items_keyboard(group, group_idx):
    """Кнопки выбора инструмента в группе."""
    buttons = []
    for i, item in enumerate(group.get('items', [])):
        buttons.append([InlineKeyboardButton(
            item['title'][:60],
            callback_data=f"craft_ii:{group_idx}:{i}"
        )])
    buttons.append([InlineKeyboardButton(
        "⬅️ Назад",
        callback_data="craft_section:instr"
    )])
    return InlineKeyboardMarkup(buttons)


def build_cooking_items_keyboard(group, group_idx):
    """Кнопки выбора блюда в группе."""
    buttons = []
    for i, item in enumerate(group.get('items', [])):
        buttons.append([InlineKeyboardButton(
            item['title'][:60],
            callback_data=f"craft_ci:{group_idx}:{i}"
        )])
    buttons.append([InlineKeyboardButton(
        "⬅️ Назад",
        callback_data="craft_section:cook"
    )])
    return InlineKeyboardMarkup(buttons)

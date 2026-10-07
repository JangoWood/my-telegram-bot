def get_all_craft_search_items(craft_base):
    """Возвращает плоский список всех карточек из craft_base.json только для /get."""
    result = []

    def add(item, section):
        if isinstance(item, dict) and item.get('title'):
            result.append((item, section))

    for grade in craft_base.get('grades', []):
        grade_name = grade.get('name', '')
        for cls in grade.get('classes', []):
            class_name = cls.get('name', '')
            for item in cls.get('items', []):
                add(item, f"🎒 {grade_name} • {class_name}")
            for group in cls.get('groups', []):
                group_name = group.get('name', '')
                for item in group.get('items', []):
                    add(item, f"🎒 {grade_name} • {class_name} • {group_name}")
                for subgroup in group.get('subgroups', []):
                    subgroup_name = subgroup.get('name', '')
                    for item in subgroup.get('items', []):
                        add(item, f"🎒 {grade_name} • {class_name} • {group_name} • {subgroup_name}")

    for group in craft_base.get('instruments', {}).get('groups', []):
        for item in group.get('items', []):
            add(item, f"⚒️ {group.get('name', '')}")

    for group in craft_base.get('cooking', {}).get('groups', []):
        for item in group.get('items', []):
            add(item, f"🥨 {group.get('name', '')}")

    for category, items in craft_base.get('alchemy', {}).items():
        for item in items:
            section = f"🧪 {category}"
            if item.get('subcategory'):
                section += f" • {item['subcategory']}"
            add(item, section)

    return result


def build_get_card_text(item):
    """Формирует карточку /get в формате существующих карточек /craft."""
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

    return text[:3997] + "..." if len(text) > 4000 else text


def find_craft_item_by_id(item_id, craft_base):
    """Находит карточку крафта по уникальному id, не меняя структуру craft_base."""
    target = str(item_id)

    def walk(value):
        if isinstance(value, dict):
            if str(value.get('id')) == target and value.get('title'):
                return value
            for child in value.values():
                found = walk(child)
                if found:
                    return found
        elif isinstance(value, list):
            for child in value:
                found = walk(child)
                if found:
                    return found
        return None

    return walk(craft_base)

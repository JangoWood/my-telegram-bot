"""Форматирование профиля и специализаций игрока."""

def format_realm_profile(player_data):
    """Форматирует вывод профиля из таблицы Ремесло"""
    name = player_data['name']
    tag = player_data['tag']
    clan = player_data['clan']
    skills = player_data['skills']
    updated = player_data['updated']

    response = f"🤟🏼 <b>{name}</b>\n"
    response += f"📱 {tag}\n"
    response += f"🏛️ {clan}\n\n"
    response += "<b>📋 Специализации:</b>\n"

    # Эмодзи для каждой специализации
    emojis = {
        'Крафтер': '⚒️',
        'Рыбалка': '🎣',
        'Шахтёр': '⛏️',
        'Охота': '🏹',
        'Кулинария': '🥨',
        'Алхимия': '🧪',
        'Плавильщик': '🪔',
        'Фермер': '🌽'
    }

    for skill, value in skills.items():
        if value:
            emoji = emojis.get(skill, '•')
            response += f"  {emoji} {skill}: <b>{value}</b>\n"
        else:
            response += f"  • {skill}: —\n"

    if updated:
        response += f"\n📅 <i>Обновлено: {updated}</i>"

    return response

def format_specializations_for_profile(row, headers):
    """Форматирует специализации игрока для красивого вывода (как в /f, но для одного игрока)"""
    if not row or len(row) < 2:
        return "❌ Нет данных"

    # Первая колонка — это тег (@username), вторая — имя игрока
    tag = row[0].strip() if len(row) > 0 else "?"
    name = row[1].strip() if len(row) > 1 and row[1] else "Неизвестно"

    # Названия специализаций (заголовки)
    spec_names = headers[2:] if len(headers) > 2 else []

    response = f"🤟🏼 <b>{name}</b>\n"
    response += f"📱 {tag}\n\n"
    response += "<b>📋 Специализации:</b>\n"

    for i, spec in enumerate(spec_names):
        if i + 2 < len(row) and row[i + 2]:
            value = row[i + 2].strip()
            if value and value != '-':
                response += f"  • {spec}: <b>{value}</b>\n"

    return response


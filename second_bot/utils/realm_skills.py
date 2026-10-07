"""Парсинг и преобразование навыков игроков."""

import re


LEVEL_MAP = {
    'Подмастерье': 'ПМ',
    'Ученик': 'У',
    'Грандмастер': 'ГМ',
    'Мастер': 'М',
    'Эксперт': 'Э'
}


def parse_skills_from_text(text):
    """Извлекает и преобразует навыки из текста сообщения."""
    skills = {}

    patterns = {
        'Крафтер': r'[⚒]*\s*[Нн]авык\s*[Кк]рафтер[а]?\s*:\s*([^\s▫️]+(?:\s+[^\s▫️]+)?)',
        'Рыбалка': r'[🎣]*\s*[Нн]авык\s*[Рр]ыбалк[иа]\s*:\s*([^\s▫️]+(?:\s+[^\s▫️]+)?)',
        'Шахтёр': r'[⛏]*\s*[Нн]авык\s*[Шш]ахт[её]р[а]?\s*:\s*([^\s▫️]+(?:\s+[^\s▫️]+)?)',
        'Охота': r'[🏹]*\s*[Нн]авык\s*[Оо]хот[ыа]\s*:\s*([^\s▫️]+(?:\s+[^\s▫️]+)?)',
        'Кулинария': r'[🥨]*\s*[Нн]авык\s*[Кк]улинари[яи]\s*:\s*([^\s▫️]+(?:\s+[^\s▫️]+)?)',
        'Алхимия': r'[🧪🌡]*\s*[Нн]авык\s*[Аа]лхими[яи]\s*:\s*([^\s▫️]+(?:\s+[^\s▫️]+)?)',
        'Плавильщик': r'[🪔]*\s*[Нн]авык\s*[Пп]лавильщик[а]?\s*:\s*([^\s▫️]+(?:\s+[^\s▫️]+)?)',
        'Фермер': r'[🌽]*\s*[Нн]авык\s*[Фф]ермер[а]?\s*:\s*([^\s▫️]+(?:\s+[^\s▫️]+)?)',
    }

    for skill, pattern in patterns.items():
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            level_text = match.group(1).strip()
            converted_level = convert_level(level_text)
            skills[skill] = converted_level

    return skills


def convert_level(level_text):
    """Преобразует текстовый уровень в короткий код."""
    for full_name, short_code in LEVEL_MAP.items():
        if full_name in level_text:
            numbers = re.findall(r'\d+', level_text)
            number = numbers[0] if numbers else ''
            return f"{short_code}{number}"

    return level_text

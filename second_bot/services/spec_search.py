"""Поиск и группировка игроков по специализациям."""


_SPECIALIZATION_SYNONYMS = {
    'крафтер': 'Крафтер', 'крафт': 'Крафтер', 'к': 'Крафтер',
    'рыбалка': 'Рыбалка', 'рыба': 'Рыбалка', 'р': 'Рыбалка',
    'шахтёр': 'Шахтёр', 'шахта': 'Шахтёр', 'ш': 'Шахтёр',
    'охота': 'Охота', 'охотник': 'Охота', 'о': 'Охота',
    'кулинария': 'Кулинария', 'еда': 'Кулинария', 'кухня': 'Кулинария', 'кул': 'Кулинария',
    'алхимия': 'Алхимия', 'алхим': 'Алхимия', 'алх': 'Алхимия', 'а': 'Алхимия',
    'плавильщик': 'Плавильщик', 'плавка': 'Плавильщик', 'пл': 'Плавильщик',
    'фермер': 'Фермер', 'ферма': 'Фермер', 'ф': 'Фермер',
}


def resolve_specialization(search_input):
    """Возвращает полное название специализации по синониму."""
    return _SPECIALIZATION_SYNONYMS.get(search_input)


def group_players_by_specialization(all_players, skill_name, level_filter=None):
    """Группирует игроков по уровню выбранной специализации."""
    levels = {}

    for player in all_players:
        level = player['skills'].get(skill_name, '')
        if not level or level == '-':
            continue

        if level_filter and level.upper() != level_filter:
            continue

        levels.setdefault(level, []).append({
            'name': player['name'],
            'tag': player['tag']
        })

    return levels

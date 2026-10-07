"""Форматирование результатов поиска по специализациям."""


def _sort_key(level):
    order = {'Э': 1, 'ГМ': 2, 'М': 3, 'ПМ': 4, 'У': 5}
    if level[:2] in order:
        prefix = level[:2]
        num_start = 2
    elif level[:1] in order:
        prefix = level[:1]
        num_start = 1
    else:
        return (99, 0)
    try:
        num = int(level[num_start:]) if len(level) > num_start else 0
    except Exception:
        num = 0
    return (order.get(prefix, 99), -num)


def build_specialization_response_chunks(levels, skill_name, level_filter=None, max_length=4000):
    """Формирует HTML-ответ /f с тем же разбиением на сообщения, что и раньше."""
    sorted_levels = sorted(levels.keys(), key=_sort_key)
    filter_text = f" {level_filter}" if level_filter else ""
    response = f"🔍 <b>Поиск по специализации: {skill_name}{filter_text}</b>\n\n"
    chunks = []

    for level in sorted_levels:
        players = sorted(levels[level], key=lambda p: p['name'].lower())

        links = []
        for player in players:
            name = player['name']
            tag = player['tag']
            if tag and tag.startswith('@'):
                username = tag[1:]
                links.append(f'<a href="https://t.me/{username}">{name}</a>')
            else:
                links.append(name)

        response += f"<b>{level}</b> ({len(players)}): {', '.join(links)}\n"

        if len(response) > max_length:
            chunks.append(response)
            response = ""

    if response:
        chunks.append(response)

    return chunks

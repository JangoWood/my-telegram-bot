"""Поиск игроков для команды /find."""

from services.table_search import get_combined_table_data


def find_players(search, main_gid, second_gid, third_gid):
    """Ищет игроков по имени в объединённых данных трёх листов.

    Возвращает список найденных записей. Если данные не загрузились,
    возвращает None.
    """
    combined_data = get_combined_table_data(
        main_gid,
        second_gid,
        third_gid
    )

    if not combined_data:
        return None

    found_items = []

    for item in combined_data:
        row = item['row']
        name = row[0].strip().lower() if row[0] else ""
        if not name:
            continue

        if search in name:
            found_items.append(item)

    return found_items

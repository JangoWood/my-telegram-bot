from .table_data import get_table_data_by_gid


def get_combined_table_data():
    """Объединяет данные с трёх листов для поиска (/find), сохраняя заголовки каждого"""
    sheets = [
        {'gid': MAIN_SHEET_GID, 'name': 'main'},
        {'gid': SECOND_SHEET_GID, 'name': 'second'},
        {'gid': THIRD_SHEET_GID, 'name': 'third'},
    ]

    combined = []

    for sheet in sheets:
        data, headers = get_table_data_by_gid(sheet['gid'])
        if data:
            for row in data:
                combined.append({
                    'row': row,
                    'headers': headers,
                    'source': sheet['name']
                })

    print(f"📊 Всего строк для поиска: {len(combined)}")
    return combined


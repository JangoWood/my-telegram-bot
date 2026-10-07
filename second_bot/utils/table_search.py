from .table_data import get_table_data_by_gid


def get_combined_table_data(main_sheet_gid, second_sheet_gid, third_sheet_gid):
    """Объединяет данные с трёх листов для поиска (/find), сохраняя заголовки каждого"""
    sheets = [
        {'gid': main_sheet_gid, 'name': 'main'},
        {'gid': second_sheet_gid, 'name': 'second'},
        {'gid': third_sheet_gid, 'name': 'third'},
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


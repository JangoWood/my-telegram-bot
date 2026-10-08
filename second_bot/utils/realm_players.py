"""Получение списка игроков из таблицы «Ремесло»."""

from services.realm_sheet import get_realm_worksheet


def get_all_players_from_realm():
    """Получает всех игроков из таблицы Ремесло."""

    try:
        ws = get_realm_worksheet()

        if ws is None:
            print("❌ Не удалось подключиться к таблице Ремесло")
            return None

        all_data = ws.get_all_values()

        if len(all_data) < 2:
            return []

        players = []

        for row in all_data[1:]:
            if not row or len(row) < 3:
                continue

            if row[0] and row[1]:
                players.append({
                    'tag': row[0],
                    'name': row[1],
                    'clan': row[2],
                    'skills': {
                        'Крафтер': row[3] if len(row) > 3 else '',
                        'Рыбалка': row[4] if len(row) > 4 else '',
                        'Шахтёр': row[5] if len(row) > 5 else '',
                        'Охота': row[6] if len(row) > 6 else '',
                        'Кулинария': row[7] if len(row) > 7 else '',
                        'Алхимия': row[8] if len(row) > 8 else '',
                        'Плавильщик': row[9] if len(row) > 9 else '',
                        'Фермер': row[10] if len(row) > 10 else '',
                    }
                })

        return players

    except Exception as e:
        print(f"Ошибка получения данных из таблицы Ремесло: {e}")
        return None
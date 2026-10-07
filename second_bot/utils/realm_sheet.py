"""Работа с таблицей Ремесло (профили и навыки игроков)."""

import os

import gspread
from google.oauth2.service_account import Credentials


CREDENTIALS_FILE = "credentials.json"
REALM_SHEET_ID = os.getenv("REALM_SHEET_ID")
REALM_SHEET_NAME = "Ремесло"


def get_player_realm_by_name(player_name):
    """Ищет игрока в таблице Ремесло по имени"""
    try:
        ws = get_realm_worksheet()
        if ws is None:
            return None

        all_data = ws.get_all_values()
        for row in all_data[1:]:  # Пропускаем заголовки
            if len(row) > 1 and row[1].lower() == player_name.lower():
                return {
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
                    },
                    'updated': row[11] if len(row) > 11 else ''
                }
        return None
    except Exception as e:
        print(f"Ошибка поиска игрока по имени {player_name}: {e}")
        return None

def get_player_realm_from_sheet(user_tag):
    """Получает данные игрока из таблицы Ремесло по тегу"""
    try:
        ws = get_realm_worksheet()
        if ws is None:
            print("❌ Не удалось подключиться к таблице Ремесло")
            return None

        # Ищем строку с тегом
        cell = ws.find(user_tag)
        if not cell:
            return None

        # Получаем всю строку
        row = ws.row_values(cell.row)

        return {
            'tag': row[0] if len(row) > 0 else '',
            'name': row[1] if len(row) > 1 else '',
            'clan': row[2] if len(row) > 2 else '',
            'skills': {
                'Крафтер': row[3] if len(row) > 3 else '',
                'Рыбалка': row[4] if len(row) > 4 else '',
                'Шахтёр': row[5] if len(row) > 5 else '',
                'Охота': row[6] if len(row) > 6 else '',
                'Кулинария': row[7] if len(row) > 7 else '',
                'Алхимия': row[8] if len(row) > 8 else '',
                'Плавильщик': row[9] if len(row) > 9 else '',
                'Фермер': row[10] if len(row) > 10 else '',
            },
            'updated': row[11] if len(row) > 11 else ''
        }
    except Exception as e:
        print(f"Ошибка получения данных игрока {user_tag}: {e}")
        return None


def update_player_realm(user_tag, player_name, clan, skills, update_time):
    """Обновляет или добавляет запись о навыках игрока"""
    try:
        ws = get_realm_worksheet()
        if ws is None:
            print("❌ get_realm_worksheet вернул None")
            return False

        now = update_time.strftime('%Y-%m-%d %H:%M:%S')

        # Подготавливаем строку данных (ключи БЕЗ эмодзи)
        row_data = [
            user_tag,
            player_name,
            clan,
            skills.get('Крафтер', ''),
            skills.get('Рыбалка', ''),
            skills.get('Шахтёр', ''),
            skills.get('Охота', ''),
            skills.get('Кулинария', ''),
            skills.get('Алхимия', ''),
            skills.get('Плавильщик', ''),
            skills.get('Фермер', ''),
            now
        ]

        # Ищем, есть ли уже такой игрок по тегу
        try:
            cell = ws.find(user_tag)
        except:
            cell = None

        if cell:
            # Обновляем существующую строку
            row_num = cell.row
            update_range = f'A{row_num}:L{row_num}'
            ws.update(range_name=update_range, values=[row_data])
            print(f"✅ Обновлена строка {row_num} для {user_tag}")
        else:
            # Добавляем новую строку
            ws.append_row(row_data)
            print(f"✅ Добавлена новая строка для {user_tag}")

        return True
    except Exception as e:
        print(f"❌ Ошибка записи навыков: {e}")
        import traceback
        traceback.print_exc()
        return False


def get_realm_worksheet():
    """Подключается к таблице с навыками"""
    try:
        scope = ['https://www.googleapis.com/auth/spreadsheets',
                 'https://www.googleapis.com/auth/drive']
        creds = Credentials.from_service_account_file(CREDENTIALS_FILE, scopes=scope)
        client = gspread.authorize(creds)
        sheet = client.open_by_key(REALM_SHEET_ID).worksheet(REALM_SHEET_NAME)
        return sheet
    except Exception as e:
        print(f"Ошибка подключения к таблице навыков: {e}")
        return None


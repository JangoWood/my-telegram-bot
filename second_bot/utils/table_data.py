import csv
import requests
from io import StringIO

def get_table_data_by_gid_with_fallback(gid):
    """Загружает данные с листа по GID, с обработкой ошибок"""
    try:
        url = f'https://docs.google.com/spreadsheets/d/e/2PACX-1vQhxznVeD5jD268Xb5x9crTJe0Di5Ra0OeSfqn_O_GA0plGpQHd8RFUg1GLlAnHgQx45XlklE1IVub9/pub?gid={gid}&output=csv'
        response = requests.get(url, timeout=30)
        response.raise_for_status()
        response.encoding = 'utf-8'

        csv_file = StringIO(response.text)
        reader = csv.reader(csv_file)
        data = list(reader)

        if not data:
            return None, None, "❌ Таблица пуста"

        # Ищем строку с заголовком "Состав" (без учёта регистра)
        start_row = None
        for i, row in enumerate(data):
            if row and len(row) > 0 and row[0].strip().lower() == 'состав':
                start_row = i
                break

        if start_row is None:
            return None, None, "❌ Не найден заголовок 'Состав'"

        headers = data[start_row]
        start_row += 1

        result = []
        for row in data[start_row:]:
            if not row or len(row) < 2:
                continue
            name = row[0].strip() if row[0] else ""
            if name and len(name) > 1 and name.lower() != 'состав':
                result.append(row)

        return result, headers, None
    except Exception as e:
        return None, None, f"❌ Ошибка: {e}"


def get_table_data_by_gid(gid):
    """Загружает данные с конкретного листа по его GID (только одну таблицу под первым 'Состав')"""
    try:
        url = f'https://docs.google.com/spreadsheets/d/e/2PACX-1vQhxznVeD5jD268Xb5x9crTJe0Di5Ra0OeSfqn_O_GA0plGpQHd8RFUg1GLlAnHgQx45XlklE1IVub9/pub?gid={gid}&output=csv'
        response = requests.get(url, timeout=30)
        response.raise_for_status()
        response.encoding = 'utf-8'

        csv_file = StringIO(response.text)
        reader = csv.reader(csv_file)
        data = list(reader)

        if not data:
            return None, None

        # Ищем первую строку с "Состав" в первой колонке
        start_row = None
        for i, row in enumerate(data):
            if row and len(row) > 0 and row[0].strip().lower() == 'состав':
                start_row = i
                break

        if start_row is None:
            print(f"⚠️ На листе {gid} не найден заголовок 'Состав'")
            return None, None

        headers = data[start_row]
        start_row += 1

        # Собираем данные ТОЛЬКО до следующего "Состав" или пустой строки
        result = []
        for row in data[start_row:]:
            # Проверяем, не встретили ли новый "Состав" (начало следующей таблицы)
            if row and len(row) > 0 and row[0].strip().lower() == 'состав':
                break  # Останавливаемся на следующей таблице

            # Проверяем, не пустая ли строка (и не заканчивается ли таблица)
            if not row or len(row) < 2:
                continue

            name = row[0].strip() if row[0] else ""
            # Пропускаем пустые строки и строки-заголовки
            if name and len(name) > 1 and name.lower() != 'состав':
                result.append(row)

        print(f"✅ Лист {gid}: загружено {len(result)} строк (ожидалось около 40)")
        return result, headers
    except Exception as e:
        print(f"❌ Ошибка загрузки листа {gid}: {e}")
        return None, None


def get_table_data():
    """Загружает CSV и возвращает данные из ПЕРВОЙ таблицы с 'Состав'"""
    try:
        response = requests.get(CSV_URL, timeout=15)
        response.raise_for_status()
        response.encoding = 'utf-8'

        csv_file = StringIO(response.text)
        reader = csv.reader(csv_file)
        data = list(reader)

        if not data:
            return None, None, "❌ Таблица пуста"

        # Находим ПЕРВУЮ ячейку с "Состав"
        target_row = None
        target_col = None
        for i, row in enumerate(data):
            for j, cell in enumerate(row):
                if cell and cell.strip() == 'Состав':
                    target_row = i
                    target_col = j
                    break
            if target_row is not None:
                break

        if target_row is None:
            return None, None, "❌ Не найдена ячейка 'Состав'"

        print(f"Найден 'Состав' в строке {target_row}, колонке {target_col}")

        # Заголовки — это строка target_row, начиная с target_col
        headers = data[target_row][target_col:]

        # Данные начинаются со следующей строки
        start_row = target_row + 1

        # Собираем ВСЕ строки, которые содержат данные
        result = []
        for row in data[start_row:]:
            # Проверяем, не наткнулись ли на новый "Состав" (начало следующей таблицы)
            for cell in row:
                if cell and cell.strip() == 'Состав':
                    break
            else:
                if len(row) > target_col:
                    data_row = row[target_col:]
                    if data_row and any(cell and cell.strip() for cell in data_row):
                        name = data_row[0].strip() if data_row[0] else ""
                        if name:
                            result.append(data_row)
                continue
            break

        if not result:
            return None, None, "❌ Нет данных под 'Состав'"

        return result, headers, None
    except Exception as e:
        return None, None, f"❌ Ошибка: {e}"


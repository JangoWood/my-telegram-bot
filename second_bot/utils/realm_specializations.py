"""Загрузка данных из таблицы специализаций."""

import csv
from io import StringIO

import requests


CW_SHEET_GID = '279368796'

CSV_URL = (
    'https://docs.google.com/spreadsheets/d/e/'
    '2PACX-1vSWZzQ4H8cNNvFc0Yxt0XQ9XHH8869jWMoC12z8DPNc1Xd02CqRlIdRx4PbqTCb0lHA9yDx8nSdqb_i/'
    f'pub?gid={CW_SHEET_GID}&output=csv'
)


def get_specializations_data():
    """Загружает данные из таблицы специализаций."""

    try:
        response = requests.get(CSV_URL, timeout=15)
        response.raise_for_status()
        response.encoding = 'utf-8'

        csv_file = StringIO(response.text)
        reader = csv.reader(csv_file)
        data = list(reader)

        if not data:
            return None, None, "❌ Таблица пуста"

        headers = data[0]

        result = []

        for row in data[1:]:
            if any(cell and cell.strip() for cell in row):
                result.append(row)

        return result, headers, None

    except Exception as e:
        return None, None, f"❌ Ошибка: {e}"
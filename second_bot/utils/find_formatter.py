"""Форматирование результатов команды /find."""

SHEET_NAMES = {
    "main": "📊 Анархия",
    "second": "📊 Наследие Анархии",
    "third": "📊 Крылья Анархии",
}


def format_find_result(item):
    """Формирует одну строку результата /find."""
    row = item["row"]
    headers = item["headers"]
    source = item["source"]

    date_start = headers[1].strip() if headers and len(headers) > 1 else "??"
    date_end = headers[2].strip() if headers and len(headers) > 2 else "??"
    player_name = row[0].strip() if row[0] else "???"
    points = row[3].strip() if len(row) > 3 else "0"
    coins = row[4].strip() if len(row) > 4 else "0"
    total = row[5].strip() if len(row) > 5 else "0"
    minus = row[6].strip() if len(row) > 6 else ""
    sheet_label = SHEET_NAMES.get(source, f"📊 {source}")

    result = f"🤟🏼 <b>{player_name}</b> — {sheet_label}\n"
    result += f"  📅 {date_start} – {date_end}: ⚔️ {points} очков, 💰 {coins} монет"
    if total and total not in ["0", ""]:
        result += f", 📦 итог: {total}"
    if minus and minus not in ["0", "", "-"]:
        result += f" ⚠️ минус: {minus}"
    return result + "\n\n"


def build_find_response(found_items):
    """Формирует сообщения /find с учётом лимита Telegram в 4000 символов."""
    response = f"🔎 <b>Найдено {len(found_items)} результатов:</b>\n\n"
    messages = []

    for item in found_items:
        part = format_find_result(item)
        if len(response) + len(part) > 4000:
            messages.append(response)
            response = ""
        response += part

    if response:
        messages.append(response)
    return messages

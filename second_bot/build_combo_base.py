import json
import re
from pathlib import Path


SOURCE = Path("combo.json")
OUTPUT = Path("combo_base.json")


def flatten_text(value):
    """Превращает Telegram text/text_entities в обычный текст."""
    if isinstance(value, str):
        return value

    if isinstance(value, list):
        parts = []

        for item in value:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                parts.append(str(item.get("text", "")))

        return "".join(parts)

    return ""


def parse_card(message):
    text = flatten_text(message.get("text", ""))

    if "📋 Страница приема" not in text:
        return None

    lines = text.splitlines()

    header_index = None
    header_match = None
    cost = None

    for i, line in enumerate(lines):
        line = line.strip()

        # Например:
        # Без чувств (🛡4)
        # Следи за рукой (⚡3🤺2)
        match = re.match(r"^(.+?)\s+\(([^()\n]+)\)$", line)

        if match:
            header_index = i
            header_match = match
            cost = match.group(2).strip()
            break

        # Например:
        # 🍞 Корка хлеба [II]
        # 🥪 Бутерброд [III]
        match = re.match(r"^(.+?)\s+\[([IVXLCDM]+)\]$", line)

        if match:
            header_index = i
            header_match = match
            break

    if header_match is None:
        return None

    name = header_match.group(1).strip()

    body = lines[header_index + 1:]

    requirements_index = None

    for i, line in enumerate(body):
        if line.strip() == "Требования:":
            requirements_index = i
            break

    if requirements_index is None:
        description_lines = body
        requirements = []
    else:
        description_lines = body[:requirements_index]

        requirements = [
            line.strip()
            for line in body[requirements_index + 1:]
            if line.strip()
        ]

    description = "\n".join(
        line.strip()
        for line in description_lines
        if line.strip()
    )

    uses = None

    uses_match = re.search(
        r"Кол-во использований:\s*(\d+)",
        text,
        re.IGNORECASE,
    )

    if uses_match:
        uses = int(uses_match.group(1))

    return {
        "name": name,
        "cost": cost,
        "description": description,
        "uses": uses,
        "requirements": requirements,
        "source_message_id": message.get("id"),
        "raw_text": text,
    }


def main():
    if not SOURCE.exists():
        raise FileNotFoundError(
            f"Не найден файл {SOURCE}. "
            f"Положи combo.json рядом со скриптом."
        )

    with SOURCE.open("r", encoding="utf-8") as f:
        export = json.load(f)

    cards = {}

    for message in export.get("messages", []):
        card = parse_card(message)

        if card is None:
            continue

        # Если одна и та же карточка встречается несколько раз,
        # сохраняем последнюю.
        cards[card["name"]] = card

    result = {
        "source": export.get("name"),
        "cards_count": len(cards),
        "cards": dict(
            sorted(
                cards.items(),
                key=lambda item: item[0].lower(),
            )
        ),
    }

    with OUTPUT.open("w", encoding="utf-8") as f:
        json.dump(
            result,
            f,
            ensure_ascii=False,
            indent=2,
        )

    print(f"Готово: {OUTPUT}")
    print(f"Карточек: {len(cards)}")


if __name__ == "__main__":
    main()
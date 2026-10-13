import json
from pathlib import Path


COMBO_BASE_FILE = Path(__file__).resolve().parent.parent / "combo_base.json"


def load_combo_base():
    with COMBO_BASE_FILE.open("r", encoding="utf-8") as f:
        data = json.load(f)

    return data.get("cards", {})


def get_combo(name):
    cards = load_combo_base()

    query = name.strip().lower()

    # Сначала точное совпадение
    for combo_name, combo in cards.items():
        if combo_name.lower() == query:
            return combo

    return None


def get_all_combos():
    return load_combo_base()
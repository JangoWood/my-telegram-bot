import json
from pathlib import Path

def load_craft_file(path):
    """Загружает JSON-базу крафта и возвращает данные и количество предметов."""
    path = Path(path)
    with open(path, "r", encoding="utf-8") as f:
        craft_base = json.load(f)

    total = sum(
        len(cls.get("items", [])) + sum(
            len(g.get("items", [])) + sum(len(sg.get("items", [])) for sg in g.get("subgroups", []))
            for g in cls.get("groups", [])
        )
        for grade in craft_base.get("grades", [])
        for cls in grade.get("classes", [])
    )

    return craft_base, total

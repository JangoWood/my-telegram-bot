"""Загрузка craft_base.json и построение индекса."""

from pathlib import Path

from services.craft_loader import load_craft_file


def load_craft_base(craft_base_file):
    """Загружает craft_base.json и строит индексы для callback_data."""

    if not craft_base_file.exists():
        print(
            f"⚠️ craft_base.json не найден по пути "
            f"{craft_base_file}"
        )
        return {}, {'grades': []}

    craft_base, total = load_craft_file(craft_base_file)

    craft_index = {'grades': []}

    for grade in craft_base.get('grades', []):
        craft_index['grades'].append(grade['name'])

        for cls in grade.get('classes', []):
            # items — если плоский класс
            # groups — если класс с группами
            pass

    print(
        f"✅ Загружено "
        f"{len(craft_base.get('grades', []))} грейдов, "
        f"{total} предметов"
    )

    return craft_base, craft_index
"""
Парсер выгрузки Telegram-канала EW | Крафт 3.0
Собирает структурированную базу для команды /craft.

Запуск: python build_craft_base.py
Результат: craft_base.json в той же папке
"""

import json
import re
from pathlib import Path


INPUT_FILE = Path(__file__).parent / 'result.json'
OUTPUT_FILE = Path(__file__).parent / 'craft_base.json'


# ==================== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ====================

def extract_message_id_from_url(url):
    """Извлекает id сообщения из t.me ссылки вида .../12 или .../12?xxx"""
    if not url:
        return None
    match = re.search(r'/(\d+)(?:\?|$)', url)
    if match:
        return int(match.group(1))
    return None


def get_message_by_id(messages_dict, msg_id):
    """Возвращает сообщение по id"""
    return messages_dict.get(msg_id)


def extract_bold_first(entities):
    """Возвращает первый bold-текст (обычно заголовок)"""
    for ent in entities:
        if isinstance(ent, dict) and ent.get('type') == 'bold':
            return ent.get('text', '').strip()
    return None


def is_grade_menu(entities):
    """Проверяет, что это меню грейда (🎒 Экипировка [X]:)"""
    first_bold = extract_bold_first(entities)
    if not first_bold:
        return None
    match = re.match(r'^🎒\s*Экипировка\s*\[([^\]]+)\]:', first_bold)
    if match:
        return match.group(1).strip()
    return None


def is_instrument_menu(entities):
    """
    Проверяет, что это меню инструментов.
    Возвращает True, если в первых bold-заголовках есть 'Орудие' или 'Инструменты'.
    """
    # Собираем первые 3-4 значимых куска до первой ссылки/большого отступа
    title_parts = []
    for ent in entities[:8]:
        if isinstance(ent, dict):
            ent_type = ent.get('type')
            text = ent.get('text', '').strip()
            if ent_type == 'bold' and text:
                title_parts.append(text)
            elif ent_type == 'plain' and text and not text.isspace():
                # Plain тоже может содержать часть заголовка
                title_parts.append(text)
            elif ent_type == 'text_link':
                # Начались ссылки — прекращаем
                break
        if len(' '.join(title_parts)) > 100:
            break

    combined = ' '.join(title_parts)
    if 'Орудие' in combined or 'Инструменты' in combined:
        return True
    return False


def is_group_marker(ent):
    """
    Проверяет, что элемент — маркер группы.
    Возвращает (тип, имя) или None.
    """
    if not isinstance(ent, dict):
        return None
    ent_type = ent.get('type')
    text = ent.get('text', '').strip()

    name = text.rstrip(':').strip()

    if ent_type == 'italic':
        if name:
            return ('group', name)

    if ent_type == 'bold':
        if name.startswith('📊') or name.startswith('Все необходимые'):
            return None
        if name.startswith('Ресурсы для крафта'):
            return None
        if name.lower().startswith('сет '):
            return ('subgroup', name)
        if name in ('Редкая', 'Эпическая', 'Обычная', 'Легендарная', 'Уникальная'):
            return ('group', name)

    return None


def is_item_link(ent):
    """Проверяет, что элемент — ссылка на предмет (не «Назад», не служебная)"""
    if not isinstance(ent, dict):
        return False
    if ent.get('type') != 'text_link':
        return False
    text = ent.get('text', '').strip()
    if not text:
        return False
    if text.startswith('⬅') or 'Назад' in text:
        return False
    return True


def is_class_menu(entities):
    """
    Проверяет, что это меню класса. Возвращает dict или None.
    """
    first_bold = extract_bold_first(entities)
    if not first_bold:
        return None

    if first_bold.startswith('🎒'):
        return None
    if first_bold.startswith('⚒️') or first_bold.startswith('🥨') or first_bold.startswith('♻️'):
        return None
    if first_bold.startswith('🌀'):
        return None

    flat_items = []
    groups = []
    current_group = None
    current_subgroup = None
    stop_parsing = False

    for ent in entities:
        if not isinstance(ent, dict):
            continue

        ent_type = ent.get('type')
        text = ent.get('text', '').strip()

        if ent_type == 'bold' and text.startswith('📊 Все необходимые'):
            stop_parsing = True
            continue

        if stop_parsing:
            continue

        marker = is_group_marker(ent)
        if marker:
            marker_type, marker_name = marker
            if marker_type == 'group':
                current_group = {'name': marker_name, 'items': [], 'subgroups': []}
                groups.append(current_group)
                current_subgroup = None
            elif marker_type == 'subgroup':
                if current_group is None:
                    current_group = {'name': marker_name, 'items': [], 'subgroups': []}
                    groups.append(current_group)
                current_subgroup = {'name': marker_name, 'items': []}
                current_group['subgroups'].append(current_subgroup)
            continue

        if is_item_link(ent):
            href = ent.get('href', '')
            text_link = ent.get('text', '').strip()
            item_id = extract_message_id_from_url(href)
            if not item_id:
                continue

            item = {'id': item_id, 'title': text_link, 'url': href}

            if current_subgroup is not None:
                current_subgroup['items'].append(item)
            elif current_group is not None:
                current_group['items'].append(item)
            else:
                flat_items.append(item)

    has_groups = bool(groups)

    if not has_groups and not flat_items:
        return None

    return {
        'name': first_bold,
        'has_groups': has_groups,
        'flat_items': flat_items,
        'groups': groups,
    }


def is_item_message(entities):
    """Проверяет, что это сообщение с ресурсами для предмета."""
    first_bold = extract_bold_first(entities)
    if not first_bold:
        return None
    if '[' not in first_bold or ']' not in first_bold:
        return None

    craft_block_text = None
    resources_block_text = None
    energy_text = None

    in_craft_block = False
    for ent in entities:
        if isinstance(ent, str):
            continue
        ent_type = ent.get('type')
        text = ent.get('text', '')

        if ent_type == 'bold' and text.strip().startswith('Ресурсы для крафта'):
            in_craft_block = True
            continue

        if in_craft_block:
            # Прекращаем сбор при встрече с маркерами конца блока
            if ent_type == 'bold' and 'Все необходимые' in text:
                in_craft_block = False
                continue
            if ent_type == 'bold' and '🔋' in text:
                in_craft_block = False
                # Не прерываем цикл — продолжаем, чтобы поймать energy ниже
            elif ent_type == 'text_link' and 'Назад' in text:
                in_craft_block = False
                continue
            elif ent_type == 'code':
                in_craft_block = False
                continue
            else:
                if ent_type == 'plain':
                    craft_block_text = (craft_block_text or '') + text
                elif ent_type == 'text_link':
                    craft_block_text = (craft_block_text or '') + text
                elif ent_type == 'bold':
                    craft_block_text = (craft_block_text or '') + text

        if ent_type == 'blockquote':
            resources_block_text = text

        if ent_type == 'bold' and '🔋' in text:
            energy_text = text.strip()

    if not craft_block_text:
        return None

    return {
        'title': first_bold,
        'craft_block': (craft_block_text or '').strip().rstrip('\n'),
        'resources_block': (resources_block_text or '').strip(),
        'energy': energy_text,
    }


def build_item_output(item_id, messages_dict):
    """Собирает полный объект предмета по id"""
    item_msg = get_message_by_id(messages_dict, item_id)
    if not item_msg:
        return None
    item_entities = item_msg.get('text_entities', [])
    item_info = is_item_message(item_entities)
    if not item_info:
        return None
    return {
        'id': item_id,
        'title': item_info['title'],
        'craft_block': item_info['craft_block'],
        'resources_block': item_info['resources_block'],
        'energy': item_info['energy'],
    }


# ==================== ИНСТРУМЕНТЫ ====================

INSTRUMENT_TYPES = [
    ('лук', '🏹 Лук'),
    ('кирка', '⛏️ Кирка'),
    ('удочка', '🎣 Удочка'),
    ('мотыга', '🔧 Мотыга'),
]

LEVEL_ORDER = {
    'подмастерья': 1,
    'мастера': 2,
    'грандмастера': 3,
}


def extract_instrument_type(title):
    """Определяет тип инструмента по названию"""
    lower = title.lower()
    for key, display_name in INSTRUMENT_TYPES:
        if key in lower:
            return display_name
    return None


def extract_instrument_level_order(title):
    """Определяет порядок уровня для сортировки: подмастерья → мастера → грандмастера"""
    lower = title.lower()
    for level_name, order in LEVEL_ORDER.items():
        if level_name in lower:
            return order
    return 99


def collect_instruments(messages_dict):
    """
    Собирает инструменты из всех меню-инструментов.
    Возвращает dict: {'groups': [{'name': ..., 'items': [...]}]}
    """
    # Ищем все меню инструментов
    instrument_items = []  # плоский список: [{'id': ..., 'title': ..., 'url': ...}]

    for msg_id, msg in messages_dict.items():
        entities = msg.get('text_entities', [])
        if not is_instrument_menu(entities):
            continue

        for ent in entities:
            if not is_item_link(ent):
                continue
            href = ent.get('href', '')
            title = ent.get('text', '').strip()
            item_id = extract_message_id_from_url(href)
            if not item_id:
                continue
            instrument_items.append({
                'id': item_id,
                'title': title,
                'url': href,
            })

    if not instrument_items:
        return {'groups': []}

    # Группируем по типу
    groups_dict = {}  # {display_name: [items]}

    for item in instrument_items:
        type_name = extract_instrument_type(item['title'])
        if not type_name:
            # Если тип не распознан — кладём в «Прочее»
            type_name = '📦 Прочее'
        if type_name not in groups_dict:
            groups_dict[type_name] = []
        groups_dict[type_name].append(item)

    # Сортируем внутри групп по уровню, потом по названию
    for type_name in groups_dict:
        groups_dict[type_name].sort(
            key=lambda x: (extract_instrument_level_order(x['title']), x['title'])
        )

    # Собираем итоговый список групп с полными данными предметов
    groups = []
    for type_name, items in groups_dict.items():
        items_full = []
        for item in items:
            item_full = build_item_output(item['id'], messages_dict)
            if item_full:
                items_full.append(item_full)
        groups.append({
            'name': type_name,
            'items': items_full,
        })

    # Сортируем группы по порядку INSTRUMENT_TYPES
    order_map = {display: i for i, (_, display) in enumerate(INSTRUMENT_TYPES)}
    groups.sort(key=lambda g: order_map.get(g['name'], 99))

    return {'groups': groups}


# ==================== ОСНОВНАЯ ЛОГИКА ====================

def build_base():
    if not INPUT_FILE.exists():
        print(f"❌ Файл {INPUT_FILE} не найден")
        return

    print(f"📂 Читаем {INPUT_FILE}...")
    with open(INPUT_FILE, 'r', encoding='utf-8') as f:
        data = json.load(f)

    messages = data.get('messages', [])
    print(f"📨 Всего сообщений: {len(messages)}")

    messages_dict = {}
    for msg in messages:
        if msg.get('type') != 'message':
            continue
        messages_dict[msg['id']] = msg

    # Шаг 1: находим меню грейдов
    grade_menus = {}
    for msg_id, msg in messages_dict.items():
        entities = msg.get('text_entities', [])
        grade_name = is_grade_menu(entities)
        if grade_name:
            grade_menus[grade_name] = {
                'id': msg_id,
                'entities': entities,
                'classes': [],
            }
            print(f"  🎒 Найден грейд: {grade_name} (id={msg_id})")

    if not grade_menus:
        print("❌ Не найдены меню грейдов")
        return

    # Шаг 2: для каждого грейда находим меню классов
    for grade_name, grade_data in grade_menus.items():
        entities = grade_data['entities']

        for ent in entities:
            if not is_item_link(ent):
                continue
            href = ent.get('href', '')
            class_id = extract_message_id_from_url(href)
            if not class_id:
                continue

            class_msg = get_message_by_id(messages_dict, class_id)
            if not class_msg:
                continue

            class_entities = class_msg.get('text_entities', [])
            class_info = is_class_menu(class_entities)
            if not class_info:
                continue

            grade_data['classes'].append({
                'name': class_info['name'],
                'id': class_id,
                'has_groups': class_info['has_groups'],
                'flat_items': class_info['flat_items'],
                'groups': class_info['groups'],
            })

            if class_info['has_groups']:
                total = sum(len(g['items']) for g in class_info['groups'])
                total += sum(len(sg['items']) for g in class_info['groups'] for sg in g.get('subgroups', []))
                print(f"    📁 Класс: {class_info['name']} (с группами, {total} предметов)")
            else:
                print(f"    📁 Класс: {class_info['name']} ({len(class_info['flat_items'])} предметов)")

    # Шаг 3: собираем предметы
    result = {'grades': []}

    for grade_name, grade_data in grade_menus.items():
        grade_out = {'name': grade_name, 'classes': []}

        for class_info in grade_data['classes']:
            class_out = {'name': class_info['name']}

            if class_info['has_groups']:
                groups_out = []
                for group in class_info['groups']:
                    group_out = {'name': group['name'], 'items': [], 'subgroups': []}

                    for item in group['items']:
                        item_full = build_item_output(item['id'], messages_dict)
                        if item_full:
                            group_out['items'].append(item_full)

                    for subgroup in group.get('subgroups', []):
                        subgroup_out = {'name': subgroup['name'], 'items': []}
                        for item in subgroup['items']:
                            item_full = build_item_output(item['id'], messages_dict)
                            if item_full:
                                subgroup_out['items'].append(item_full)
                        group_out['subgroups'].append(subgroup_out)

                    groups_out.append(group_out)

                class_out['groups'] = groups_out
            else:
                items_out = []
                for item in class_info['flat_items']:
                    item_full = build_item_output(item['id'], messages_dict)
                    if item_full:
                        items_out.append(item_full)
                class_out['items'] = items_out

            grade_out['classes'].append(class_out)

        result['grades'].append(grade_out)

    # Шаг 4: собираем инструменты
    print()
    print("🔧 Собираем инструменты...")
    result['instruments'] = collect_instruments(messages_dict)

    for group in result['instruments']['groups']:
        print(f"  🛠 {group['name']}: {len(group['items'])} предметов")

    # Сохраняем
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    # Итоги
    print()
    print("=" * 50)
    print(f"✅ Готово! Сохранено в {OUTPUT_FILE}")
    print()

    total_items = 0
    for grade in result['grades']:
        grade_items = 0
        for cls in grade['classes']:
            if 'groups' in cls:
                for g in cls['groups']:
                    grade_items += len(g['items'])
                    for sg in g.get('subgroups', []):
                        grade_items += len(sg['items'])
            else:
                grade_items += len(cls.get('items', []))
        total_items += grade_items
        print(f"  {grade['name']}: {len(grade['classes'])} классов, {grade_items} предметов")

    instruments_count = sum(len(g['items']) for g in result['instruments']['groups'])
    print(f"  ИНСТРУМЕНТЫ: {len(result['instruments']['groups'])} групп, {instruments_count} предметов")
    print(f"  ВСЕГО предметов: {total_items + instruments_count}")


if __name__ == '__main__':
    build_base()
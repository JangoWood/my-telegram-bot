"""Временно замороженный функционал боевого советника и тестового парсера.

Логика намеренно не перерабатывается.
Модуль изолирован от основного бота до отдельной большой переработки.
"""

import re
from datetime import datetime

from telegram import Update
from telegram.ext import ContextTypes


# Хранилище сессий CW
cw_sessions = {}

async def start_cw(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    # Проверка: уже в режиме
    if user_id in cw_sessions:
        await update.message.reply_text(
            "❌ Ты уже в режиме советника.\n"
            "Используй /stop_cw, чтобы выйти."
        )
        return

    # Проверка: указан ли ник
    if not context.args:
        await update.message.reply_text(
            "❌ Укажи свой игровой ник.\n"
            "Пример: /start_cw Jango"
        )
        return

    player_nick = context.args[0].strip()

    # Создаём сессию
    cw_sessions[user_id] = {
        'player_nick': player_nick,
        'last_turn': 0,
        'logs': [],
        'stats': {},
        'enemy_stats_by_name': {},  # ← теперь словарь по имени
        'enemy_hits_by_name': {},  # ← теперь словарь по имени
        'enemy_received_by_name': {},  # ← теперь словарь по имени
        'started_at': datetime.now(),
    }

    await update.message.reply_text(
        f"✅ Режим советника активирован!\n"
        f"Игрок: {player_nick}\n\n"
        f"Присылай логи боя, содержащие слово «Ход».\n"
        f"Я буду анализировать их по порядку."
    )


async def stop_cw(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    if user_id not in cw_sessions:
        await update.message.reply_text(
            "❌ Ты не в режиме советника.\n"
            "Используй /start_cw <ник>, чтобы начать."
        )
        return

    # Удаляем сессию
    del cw_sessions[user_id]

    await update.message.reply_text(
        "❌ Режим советника завершён.\n"
        "До новых боёв!"
    )

def is_log(text):
    """Проверяет, похоже ли сообщение на лог боя"""
    return "Ход" in text

def parse_turn(text):
    match = re.search(r'Ход\s*(\d+)', text)
    if match:
        return int(match.group(1))
    return None

def parse_team(line):
    match = re.search(r'([^:]+)\s*💔\s*\((\d+)/(\d+)\)', line)
    if match:
        return {
            'name': match.group(1).strip(),
            'hp': int(match.group(2)),
            'max_hp': int(match.group(3)),
        }
    return None

def parse_player(line):
    match = re.search(
        r'^\d+\.\s*([^\s]+)\s+([^\s]+?)([А-Яа-яA-Za-z0-9_]+)\s*🔸(\d+)\s*❤️\((\d+)/(\d+)\)',
        line
    )
    if match:
        return {
            'emoji_prefix': match.group(1),
            'role_emoji': match.group(2),
            'name': match.group(3),
            'full_id': f"{match.group(1)} {match.group(2)}{match.group(3)} 🔸{match.group(4)}",
            'level': int(match.group(4)),
            'hp': int(match.group(5)),
            'max_hp': int(match.group(6)),
        }
    return None

def parse_next_fight(text):
    fights = []
    in_next = False
    for line in text.split('\n'):
        if 'Следующий ход:' in line:
            in_next = True
            continue
        if in_next and line.strip():
            # Сохраняем всю строку целиком
            fights.append(line.strip())
        if in_next and not line.strip():
            break
    return fights

def get_enemy_from_next_fight(fights, player_nick):
    for line in fights:
        # Убираем номер в начале (например, "1. " или "2. ")
        clean_line = re.sub(r'^\d+\.\s*', '', line)
        parts = clean_line.split(' vs ')
        if len(parts) == 2:
            player1 = parts[0].strip()
            player2 = parts[1].strip()
            if player_nick in player1:
                return player2
            elif player_nick in player2:
                return player1
    return None

def parse_player_actions(text, enemy_name):
    result = {
        'combos': [],
        'skills': [],
        'hits': [],
        'received': [],
        'missed_turns': [],
    }

    lines = text.split('\n')
    for line in lines:
        if enemy_name not in line:
            continue

        # 1. Пропуск хода
        if 'пропускает удар' in line:
            result['missed_turns'].append(line.strip())
            continue

        # 2. Приёмы (сокращённый вид)
        if 'использует комбинацию' in line and enemy_name in line:
            # Извлекаем название приёма после "комбинацию"
            match = re.search(r'использует комбинацию\s+([^(]+)', line)
            if match:
                combo_name = match.group(1).strip()
            else:
                combo_name = line.strip()

            usage = ""
            for next_line in lines[lines.index(line) + 1:]:
                if 'Кол-во использований:' in next_line:
                    usage_match = re.search(r'Кол-во использований:\s*(\d+/\d+)', next_line)
                    if usage_match:
                        usage = usage_match.group(1)
                    break
                if not next_line.strip() or 'использует комбинацию' in next_line or 'бьет' in next_line:
                    break

            # Сохраняем полную строку для фильтрации
            result['combos'].append({
                'name': combo_name,
                'usage': usage,
                'full_line': line.strip()  # сохраняем для проверки принадлежности
            })
            continue

        # 3. Навыки (с 💫) — с подсчётом использований
        if '💫' in line and enemy_name in line:
            # Извлекаем название навыка после 💫
            match = re.search(r'💫\s*([^,\n]+)', line)
            if match:
                skill_name = match.group(1).strip()
            else:
                skill_name = line.strip()

            result['skills'].append({
                'name': skill_name,
                'full_line': line.strip()
            })
            continue
        # 4. Удары и полученные удары
        if 'бьет' in line:
            parts = line.split('бьет')
            if len(parts) < 2:
                continue

            left = parts[0].strip()   # кто бьёт
            right = parts[1].strip()  # кого бьют + часть тела

            # Определяем часть тела по ключевым словам
            part = "неизвестно"
            body_parts = ['голову', 'голова', 'грудь', 'живот', 'пояс', 'ноги']
            for bp in body_parts:
                if bp in right:
                    part = bp
                    break

            # Определяем результат
            is_block = 'попадает в блок' in line or 'блок' in line or 'Противник заблокировал' in line
            is_crit = 'критическим ударом' in line
            is_evade = 'увернулся' in line
            is_counter = 'контрудар' in line

            # Если соперник в левой части — он бьёт
            if enemy_name in left:
                result['hits'].append({
                    'part': part,
                    'block': is_block,
                    'crit': is_crit,
                    'evade': is_evade,
                    'counter': is_counter,
                })

            # Если соперник в правой части — по нему бьют
            if enemy_name in right and not is_counter:
                result['received'].append({
                    'part': part,
                    'block': is_block,
                    'crit': is_crit,
                    'evade': is_evade,
                    'counter': is_counter,
                })

    return result

def extract_player_name(line):
    """Извлекает чистое имя игрока из полной строки"""
    match = re.search(r'([А-Яа-яA-Za-z0-9_]+)\s*🔸', line)
    if match:
        return match.group(1)
    return None

def parse_enemy_stats(text, enemy_name):
    """
    Собирает статистику для соперника за текущий ход:
    🗡 — попадания (удары не в блок)
    🛡 — блоки
    🥊 — критические удары
    ⚡️ — уклонения
    🤺 — контрудары
    🌬 — промахи / попадания в блок
    """
    stats = {
        'swords': 0,
        'shields': 0,
        'crits': 0,
        'evades': 0,
        'counters': 0,
        'misses': 0,
    }

    lines = text.split('\n')
    for line in lines:
        if enemy_name not in line:
            continue

        # 🗡 Попадания (только когда соперник сам бьёт)
        if 'бьет' in line and 'наносит' in line:
            # Проверяем, что enemy_name находится до того, как появляется "бьет"
            # или enemy_name является субъектом действия
            parts = line.split('бьет')
            if len(parts) > 0 and enemy_name in parts[0]:
                # Это удар соперника
                if 'блок' not in line and 'попадает в блок' not in line:
                    stats['swords'] += 1

        # 🛡 Блоки (соперник ставит блок)
        if 'попадает в блок' in line and 'бьет' in line:
            stats['shields'] += 1

        # 🥊 Критические удары
        if 'критическим ударом' in line:
            stats['crits'] += 1

        # ⚡️ Уклонения
        if 'увернулся' in line:
            stats['evades'] += 1

        # 🤺 Контрудары
        if 'контрудар' in line:
            stats['counters'] += 1

        # 🌬 Промахи / блоки (когда удар соперника попал в блок)
        if 'бьет' in line and ('блок' in line or 'попадает в блок' in line):
            parts = line.split('бьет')
            if len(parts) > 0 and enemy_name in parts[0]:
                stats['misses'] += 1

    return stats

def subtract_combo_resources(stats, resources):
    """Вычитает ресурсы из статистики игрока"""
    if not resources:
        return

    # Ищем 🗡N, 🛡N, 🥊N, ⚡️N, 🤺N, 🌬N
    swords = re.search(r'🗡(\d+)', resources)
    shields = re.search(r'🛡(\d+)', resources)
    crits = re.search(r'🥊(\d+)', resources)
    evades = re.search(r'⚡️(\d+)', resources)
    counters = re.search(r'🤺(\d+)', resources)
    misses = re.search(r'🌬(\d+)', resources)

    if swords:
        stats['swords'] -= int(swords.group(1))
    if shields:
        stats['shields'] -= int(shields.group(1))
    if crits:
        stats['crits'] -= int(crits.group(1))
    if evades:
        stats['evades'] -= int(evades.group(1))
    if counters:
        stats['counters'] -= int(counters.group(1))
    if misses:
        stats['misses'] -= int(misses.group(1))

    # Не даём уйти в минус
    for key in stats:
        if stats[key] < 0:
            stats[key] = 0

async def test_parse(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Проверяем, есть ли ответ на сообщение
    if not update.message.reply_to_message:
        await update.message.reply_text(
            "❌ Ответь на сообщение с логом боя командой /test_parse"
        )
        return

    text = update.message.reply_to_message.text
    if not text:
        await update.message.reply_text("❌ В сообщении нет текста.")
        return

    # Получаем ник из сессии
    user_id = update.effective_user.id
    session = cw_sessions.get(user_id)
    if not session:
        await update.message.reply_text(
            "❌ Ты не в режиме советника. Используй /start_cw <ник>"
        )
        return

    player_nick = session['player_nick']

    # Парсим номер хода
    turn = parse_turn(text)
    msg = f"🔍 Номер хода: {turn}\n\n"

    # Парсим команды
    for line in text.split('\n'):
        if 'Нападающие' in line or 'Защитники' in line:
            team = parse_team(line)
            if team:
                msg += f"📊 {team['name']}: ❤️ {team['hp']}/{team['max_hp']}\n"

    if turn is None and not any('Нападающие' in line or 'Защитники' in line for line in text.split('\n')):
        msg += "\n⚠️ Не удалось распознать номер хода или команды."

    # Парсим защитников и нападающих
    defenders = []
    attackers = []
    current_team = None

    for line in text.split('\n'):
        if 'Следующий ход:' in line:
            break
        if 'Защитники' in line:
            current_team = 'defenders'
            continue
        if 'Нападающие' in line:
            current_team = 'attackers'
            continue
        if current_team and '❤️' in line and '🔸' in line:
            player = parse_player(line)
            if player:
                if current_team == 'defenders':
                    defenders.append(player)
                else:
                    attackers.append(player)

    # === НАХОДИМ FULL_ID НАШЕГО ИГРОКА ===
    player_full_id = player_nick  # запасной вариант
    all_players = defenders + attackers
    for player in all_players:
        if player['name'] == player_nick:
            player_full_id = player['full_id']
            break

    # Вывод защитников
    if defenders:
        msg += "\n🛡️ Защитники:\n"
        for p in defenders:
            hp_percent = round(p['hp'] / p['max_hp'] * 100)
            msg += f"  {p['emoji_prefix']} {p['role_emoji']}{p['name']} 🔸{p['level']} ❤️({p['hp']}/{p['max_hp']}) {hp_percent}%\n"
            stats = session['enemy_stats_by_name'].get(p['name'], {})
            if stats:
                msg += f"<blockquote>🗡{stats.get('swords', 0)}🛡{stats.get('shields', 0)}🥊{stats.get('crits', 0)}⚡️{stats.get('evades', 0)}🤺{stats.get('counters', 0)}🌬{stats.get('misses', 0)}</blockquote>\n"

    # Вывод нападающих
    if attackers:
        msg += "\n⚔️ Нападающие:\n"
        for p in attackers:
            hp_percent = round(p['hp'] / p['max_hp'] * 100)
            msg += f"  {p['emoji_prefix']} {p['role_emoji']}{p['name']} 🔸{p['level']} ❤️({p['hp']}/{p['max_hp']}) {hp_percent}%\n"
            stats = session['enemy_stats_by_name'].get(p['name'], {})
            if stats:
                msg += f"<blockquote>🗡{stats.get('swords', 0)}🛡{stats.get('shields', 0)}🥊{stats.get('crits', 0)}⚡️{stats.get('evades', 0)}🤺{stats.get('counters', 0)}🌬{stats.get('misses', 0)}</blockquote>\n"

    # Следующий ход
    fights = parse_next_fight(text)
    if fights:
        enemy_line = get_enemy_from_next_fight(fights, player_nick)
        if enemy_line:
            enemy_name = extract_player_name(enemy_line)
            msg += f"\n⚔️ Следующий ход соперника: {enemy_line}\n"

            # === ДИАГНОСТИКА ДЛЯ ПОЛУЧЕННЫХ УДАРОВ ===
            msg += "\n🔍 Диагностика полученных ударов:\n"
            for line in text.split('\n'):
                if 'бьет' in line and enemy_name in line:
                    msg += f"  Строка: {line[:120]}\n"
                    if 'по' in line:
                        parts = line.split('по')
                        msg += f"    'по' есть в строке\n"
                        msg += f"    enemy_name в parts[0]: {enemy_name in parts[0]}\n"
                        msg += f"    enemy_name в parts[1]: {enemy_name in parts[1] if len(parts) > 1 else False}\n"
                    else:
                        msg += f"    'по' НЕТ в строке\n"
                    # Проверяем, есть ли часть тела
                    match = re.search(r'бьет\s+[^,\.]+\s+в\s+([^,\.]+?)(?:\s|,|\.|по)', line)
                    if match:
                        msg += f"    Часть тела: {match.group(1)}\n"
                    else:
                        msg += f"    Часть тела НЕ найдена\n"
                    msg += f"    enemy_name в строке: {enemy_name in line}\n"
                    msg += f"    'бьет' в строке: {'бьет' in line}\n"

            # === ПАРСИМ ДЕЙСТВИЯ СОПЕРНИКА ===
            actions = parse_player_actions(text, enemy_name)

            # === ВЫВОД ПРИЁМОВ (только для текущего соперника) ===
            enemy_combos = []
            for combo in actions.get('combos', []):
                # Проверяем, что приём принадлежит текущему сопернику
                if isinstance(combo, dict) and combo.get('full_line'):
                    if enemy_name in combo['full_line']:
                        enemy_combos.append(combo)

            if enemy_combos:
                msg += "\n📋 Использованные приемы:\n"
                for combo in enemy_combos:
                    msg += f"  {combo['name']} : {combo['usage']}\n"

            # === ВЫВОД НАВЫКОВ (только для текущего соперника) ===
            enemy_skills = []
            skill_count = {}

            for skill in actions.get('skills', []):
                if isinstance(skill, dict) and skill.get('full_line'):
                    if enemy_name in skill['full_line']:
                        skill_name = skill['name']
                        # Считаем, сколько раз встречается навык
                        if skill_name not in skill_count:
                            skill_count[skill_name] = 0
                        skill_count[skill_name] += 1
                        # Добавляем только один раз в список (для уникальности)
                        if skill_name not in [s['name'] for s in enemy_skills]:
                            enemy_skills.append(skill)

            if enemy_skills:
                msg += "\n💫 Использованные навыки:\n"
                for skill in enemy_skills:
                    count = skill_count.get(skill['name'], 0)
                    msg += f"  {skill['name']} ({count})\n"

            # === СОХРАНЯЕМ ДЕЙСТВИЯ ДЛЯ ВСЕХ ИГРОКОВ ===
            all_players = defenders + attackers

            for player in all_players:
                player_name = player['name']

                if player_name not in session['enemy_hits_by_name']:
                    session['enemy_hits_by_name'][player_name] = []
                if player_name not in session['enemy_received_by_name']:
                    session['enemy_received_by_name'][player_name] = []
                if player_name not in session['enemy_stats_by_name']:
                    session['enemy_stats_by_name'][player_name] = {
                        'swords': 0, 'shields': 0, 'crits': 0,
                        'evades': 0, 'counters': 0, 'misses': 0,
                    }

                player_actions = parse_player_actions(text, player_name)
                player_stats = parse_enemy_stats(text, player_name)

                if player_actions.get('hits'):
                    session['enemy_hits_by_name'][player_name].extend(player_actions['hits'])
                if player_actions.get('received'):
                    session['enemy_received_by_name'][player_name].extend(player_actions['received'])

                # Сохраняем статистику
                if player_stats:
                    stats = session['enemy_stats_by_name'][player_name]
                    stats['swords'] += player_stats['swords']
                    stats['shields'] += player_stats['shields']
                    stats['crits'] += player_stats['crits']
                    stats['evades'] += player_stats['evades']
                    stats['counters'] += player_stats['counters']
                    stats['misses'] += player_stats['misses']

            # === ВЫЧИТАЕМ РЕСУРСЫ ИЗ СТАТИСТИКИ ТЕКУЩЕГО СОПЕРНИКА ===
            if enemy_name in session['enemy_stats_by_name']:
                stats = session['enemy_stats_by_name'][enemy_name]
                for combo in actions.get('combos', []):
                    if isinstance(combo, dict) and combo.get('resources'):
                        subtract_combo_resources(stats, combo['resources'])

            # === ДИАГНОСТИКА: проверяем, что сохранилось в сессии ===
            msg += "\n🔍 Диагностика сессии:\n"
            all_players = defenders + attackers
            for player in all_players:
                pname = player['name']
                hits = session['enemy_hits_by_name'].get(pname, [])
                received = session['enemy_received_by_name'].get(pname, [])
                msg += f"  {pname}: hits={len(hits)}, received={len(received)}\n"
                if hits:
                    msg += f"    hits: {hits}\n"
                if received:
                    msg += f"    received: {received}\n"

            # === ВЫВОД ДЛЯ ТЕКУЩЕГО СОПЕРНИКА ===
            if enemy_name in session['enemy_hits_by_name']:
                msg += f"\n🎯 Удары соперника ({enemy_name}):\n"
                for i, hit in enumerate(session['enemy_hits_by_name'][enemy_name], 1):
                    icon = "🛡" if hit['block'] else "🗡"
                    msg += f"  {i}) {hit['part']} ({icon})\n"

            if enemy_name in session['enemy_received_by_name']:
                msg += f"\n🛡️ Полученные удары ({enemy_name}):\n"
                for i, rec in enumerate(session['enemy_received_by_name'][enemy_name], 1):
                    icon = "🛡" if rec['block'] else "🗡"
                    msg += f"  {i}) {rec['part']} ({icon})\n"

            if enemy_name in session['enemy_stats_by_name']:
                stats = session['enemy_stats_by_name'][enemy_name]
                msg += f"\n📊 Накопленная статистика соперника ({enemy_name}):\n"
                msg += f"  🗡 {stats['swords']}  🛡 {stats['shields']}  🥊 {stats['crits']}  ⚡️ {stats['evades']}  🤺 {stats['counters']}  🌬 {stats['misses']}\n"

    # Разбиваем сообщение на части по 4000 символов
    if len(msg) > 4000:
        parts = [msg[i:i + 4000] for i in range(0, len(msg), 4000)]
        for part in parts:
            await update.message.reply_text(part, parse_mode="HTML")
    else:
        await update.message.reply_text(msg, parse_mode="HTML")

# ХЕЛП на КВ
async def help_cw(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Начинает сессию отслеживания противников"""
    user_id = update.effective_user.id

    # Проверка: уже в режиме
    if user_id in help_cw_sessions:
        await update.message.reply_text(
            "❌ Ты уже в режиме отслеживания противников.\n"
            "Используй /stop_help_cw, чтобы выйти."
        )
        return

    # Проверка: указан ли клан
    if not context.args:
        await update.message.reply_text(
            "❌ Укажи название своего клана.\n"
            "Пример: /help_cw Анархия"
        )
        return

    clan_name = ' '.join(context.args).strip()

    # Создаём сессию
    help_cw_sessions[user_id] = {
        'my_clan': clan_name,
        'enemy_clan': None,          # будет заполнено из первого лога
        'enemy_players': {},          # {имя_игрока: {'swords': 0, 'shields': 0, ...}}
        'last_turn': 0,
        'logs': [],
        'combos_used': {},            # {имя_игрока: [список использованных приёмов]}
        'started_at': datetime.now(),
    }

    await update.message.reply_text(
        f"✅ Режим отслеживания противников активирован!\n"
        f"Твой клан: {clan_name}\n\n"
        f"Присылай логи боя, содержащие слово «Ход».\n"
        f"Я буду отслеживать накопленные очки действий противников."
    )

from __future__ import annotations

from collections import defaultdict
from telegram import Update
from telegram.ext import ContextTypes
import re

from services.war_od import (
    OD_TYPES,
    WARNING_SEQUENCES,
    apply_turn,
    format_turn,
    parse_used_combos,
    check_warning_sequences,
    extract_player_name,
    parse_player_clans,
    parse_war_sides,
)
from services.status_effects import STATUS_EFFECTS
from services.status_manager import apply_status, tick_statuses
import json
from pathlib import Path

war_sessions = {}


COMBO_BASE_PATH = (
    Path(__file__).resolve().parent.parent / "combo_base.json"
)

with COMBO_BASE_PATH.open("r", encoding="utf-8") as f:
    COMBO_BASE = json.load(f)

COMBO_CARDS = COMBO_BASE.get("cards", {})


def get_combo_class(combo_name: str) -> str | None:
    """Возвращает класс приёма из combo_base.json."""
    combo = COMBO_CARDS.get(combo_name)

    if not combo:
        return None

    for requirement in combo.get("requirements", []):
        match = re.match(r"^\s*Класс:\s*(.+?)\s*$", requirement)

        if match:
            return match.group(1).strip()

    return None


def _empty():
    return {x: 0 for x in OD_TYPES}

def will_be_silenced_next_turn(statuses, player):
    player_statuses = statuses.get(player, {})

    return any(
        effect.get("status") == "🔇"
        and effect.get("duration", 0) > 0
        for effect in player_statuses.values()
    )
async def start_war(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    war_sessions[user_id] = {
        "balances": {},
        "processed": set(),
        "last_turn": 0,
        "pending_sequences": {},
        "disabled_targets": {},
        "statuses": {},
        "player_classes": {},
    }

    await update.message.reply_text(
        "⚔️ Учёт ОД запущен.\n\n"
        "Присылай сообщения с логами ходов.\n"
        "Пока считаю только ОД: траты → начисления → остаток."
    )


async def stop_war(update: Update, context: ContextTypes.DEFAULT_TYPE):
    war_sessions.pop(update.effective_user.id, None)
    await update.message.reply_text("🛑 Учёт ОД остановлен.")

def parse_combo_usage(text: str) -> dict[str, dict[str, tuple[int, int]]]:
    """
    Возвращает для каждого игрока использованные приёмы
    и их количество использований.

    Пример:
    Мурианна:
        Отступление II -> (3, 3)
    """
    result = {}

    current_player = None

    for line in text.splitlines():
        if "использует комбинацию" not in line:
            continue

        player = extract_player_name(
            line.split("использует комбинацию", 1)[0]
        )

        if not player:
            continue

        match_combo = re.search(
            r"использует комбинацию\s+(.+?)\s*\(",
            line,
        )

        if not match_combo:
            continue

        combo_name = match_combo.group(1).strip().replace("*", "")

        # Пока только запоминаем игрока и приём.
        current_player = player

        # Само "X/Y" находится ниже в блоке,
        # поэтому обработка делается во втором проходе.
        result.setdefault(player, {})[combo_name] = (0, 0)

    # Ищем блоки использования и связываем X/Y
    # с последним найденным приёмом.
    lines = text.splitlines()

    current_player = None
    current_combo = None

    for line in lines:
        if "использует комбинацию" in line:
            player = extract_player_name(
                line.split("использует комбинацию", 1)[0]
            )

            match_combo = re.search(
                r"использует комбинацию\s+(.+?)\s*\(",
                line,
            )

            if player and match_combo:
                current_player = player
                current_combo = match_combo.group(1).strip().replace("*", "")

        elif current_player and current_combo:
            match_usage = re.search(
                r"Кол-во использований:\s*(\d+)\s*/\s*(\d+)",
                line,
            )

            if match_usage:
                used = int(match_usage.group(1))
                maximum = int(match_usage.group(2))

                result.setdefault(current_player, {})[
                    current_combo
                ] = (used, maximum)

                current_player = None
                current_combo = None

    return result

async def war_log(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    session = war_sessions.get(user_id)

    if not session or not update.message or not update.message.text:
        return

    text = update.message.text

    player_clans = parse_player_clans(text)
    defenders_clan, attackers_clan = parse_war_sides(text)

    # ---------------------------------------------------------
    # Рассчитываем текущий ход
    # ---------------------------------------------------------
    result = apply_turn(session["balances"], text)
    # ---------------------------------------------------------
    # Защита от повторной обработки
    # ---------------------------------------------------------
    if result.log_id in session["processed"]:
        await update.message.reply_text(
            f"ℹ️ Ход {result.turn} уже обработан. Повторно не считаю."
        )
        return

    # ---------------------------------------------------------
    # Если ход пришёл не по порядку — начинаем заново
    # ---------------------------------------------------------
    if session["last_turn"] and result.turn <= session["last_turn"]:
        session["balances"] = {}
        session["pending_sequences"] = {}
        session["disabled_targets"] = {}
        session["statuses"] = {}
        session["player_classes"] = {}

        result = apply_turn(
            session["balances"],
            text,
        )

    session.setdefault("statuses", {})

    # Снимок активных статусов текущего хода.
    # Статус, наложенный в этом ходу, начнёт отображаться со следующего хода.

    # Запоминаем игроков под 🔇 до уменьшения длительности статусов.

    # Снимок активных статусов для отображения.
    status_lines = {}

    for player, player_statuses in session["statuses"].items():
        lines = []

        for effect in player_statuses.values():
            status = effect["status"]
            duration = effect["duration"]
            lines.append(f"{status} — {duration} ⏳")

        if lines:
            status_lines[player] = lines

    # Уменьшаем длительность старых статусов.
    tick_statuses(session["statuses"])


    used_combos = parse_used_combos(text)

    # Закрепляем класс по первому подходящему приёму игрока.
    player_classes = session.setdefault("player_classes", {})

    for player, combos in used_combos.items():
        if player in player_classes:
            continue

        for combo in combos:
            player_class = get_combo_class(combo)

            if player_class:
                player_classes[player] = player_class
                break


    # ---------------------------------------------------------
    # Выстрел в горло: цель определяется по блоку ударов.
    # Строка 💫 означает, что приём сработал.
    # ---------------------------------------------------------
    throat_shot_users = {}

    for line in text.splitlines():
        if "💫" not in line or "Выстрел в горло" not in line:
            continue

        player = extract_player_name(line.split("💫", 1)[0])
        match = re.search(r"Выстрел в горло\s+([IVX]+)", line)

        if not player or not match:
            continue

        combo_name = f"Выстрел в горло {match.group(1)}"
        effect = STATUS_EFFECTS.get(combo_name)

        if effect:
            throat_shot_users[player] = effect

    # Находим противников, которых атаковал каждый игрок.
    attacked_targets = {}

    for line in text.splitlines():
        if "бьет" not in line:
            continue

        # Имя атакующего находится до слова «бьет».
        attacker = extract_player_name(line.split("бьет", 1)[0])

        # Имя цели — после слова «бьет».
        target = extract_player_name(line.split("бьет", 1)[1])

        if not attacker or not target or attacker == target:
            continue

        attacked_targets.setdefault(attacker, set()).add(target)

    # Накладываем 🔇 только на однозначно найденную цель.
    for player, effect in throat_shot_users.items():
        targets = attacked_targets.get(player, set())

        if len(targets) != 1:
            continue

        target = next(iter(targets))

        apply_status(
            session["statuses"],
            player,
            effect,
            player_clans,
            target_player=target,
        )

    # ---------------------------------------------------------
    # Применяем эффекты использованных приёмов.
    # ---------------------------------------------------------
    for player, combos in used_combos.items():
        for combo in combos:
            effect = STATUS_EFFECTS.get(combo)

            if not effect:
                continue

            apply_status(
                session["statuses"],
                player,
                effect,
                player_clans,
            )


    # ---------------------------------------------------------
    # Выстрел в горло: приём сработал, определяем цель по бою.
    # ---------------------------------------------------------
    throat_shot_users = {}

    for line in text.splitlines():
        if "💫" not in line or "Выстрел в горло" not in line:
            continue

        player = extract_player_name(line.split("💫", 1)[0])
        match = re.search(r"Выстрел в горло\s+([IVX]+)", line)

        if not player or not match:
            continue

        combo_name = f"Выстрел в горло {match.group(1)}"
        effect = STATUS_EFFECTS.get(combo_name)

        if effect:
            throat_shot_users[player] = effect

    # Берём только строки собственно боевого блока.
    combat_lines = []
    in_combat = False

    for line in text.splitlines():
        if "Ход боя:" in line:
            in_combat = True
            continue

        if in_combat and "Следующий ход:" in line:
            break

        if in_combat and "бьет" in line:
            combat_lines.append(line)

    # Связываем участников по взаимным ударам.
    opponents = {}

    for line in combat_lines:
        if "бьет" not in line:
            continue

        left, right = line.split("бьет", 1)
        attacker = extract_player_name(left)
        target = extract_player_name(right)

        if not attacker or not target or attacker == target:
            continue

        opponents.setdefault(attacker, set()).add(target)
        opponents.setdefault(target, set()).add(attacker)

    for player, effect in throat_shot_users.items():
        targets = opponents.get(player, set())

        # Не накладываем статус, если цель нельзя определить однозначно.
        if len(targets) != 1:
            continue

        target = next(iter(targets))

        apply_status(
            session["statuses"],
            player,
            effect,
            player_clans,
            target_player=target,
        )

    # Учитываем 🔇, наложенный в текущем ходу.
    silenced_players = {
        player
        for player, player_statuses in session["statuses"].items()
        if any(
            effect.get("status") == "🔇"
            and effect.get("duration", 0) > 0
            for effect in player_statuses.values()
        )
    }

    pending = session.get("pending_sequences", {})

    # ---------------------------------------------------------
    # Проверяем максимальное количество использований приёмов.
    #
    # Например:
    # Отступление II: 3/3
    #
    # После этого Отступление II больше никогда не отслеживаем
    # для этого игрока в рамках текущей войны.
    # ---------------------------------------------------------
    combo_usage = parse_combo_usage(text)

    disabled_targets = session.setdefault(
        "disabled_targets",
        {},
    )

    for player, combos in combo_usage.items():
        for combo, (used, maximum) in combos.items():
            if used >= maximum:
                disabled_targets.setdefault(
                    player,
                    set(),
                ).add(combo)

    # ---------------------------------------------------------
    # Если второй приём достиг максимального количества
    # использований, удаляем уже существующую связку.
    # ---------------------------------------------------------
    for player, combos in combo_usage.items():
        for combo, (used, maximum) in combos.items():
            if used < maximum:
                continue

            if player not in pending:
                continue

            remaining_sequences = []

            for state in pending[player]:
                sequence = WARNING_SEQUENCES.get(state["first"])

                if not sequence:
                    continue

                target = sequence["target"]

                if target == combo:
                    continue

                remaining_sequences.append(state)

            if remaining_sequences:
                pending[player] = remaining_sequences
            else:
                pending.pop(player, None)

    # ---------------------------------------------------------
    # 2. Добавляем новые первые приёмы.
    #
    # expires_turn:
    #
    # Сосредоточение на 7 → expires_turn = 10
    # Деморализующая волна на 7 → expires_turn = 9
    # Резня на 7 → expires_turn = 8
    #
    # То есть:
    # Сосредоточение → 8, 9, 10
    # Деморализующая → 8, 9
    # Резня → 8
    # ---------------------------------------------------------
    for player, combos in used_combos.items():
        for combo in combos:
            sequence = WARNING_SEQUENCES.get(combo)

            if not sequence:
                continue

            target = sequence["target"]

            if target in disabled_targets.get(player, set()):
                continue

            player_pending = pending.setdefault(player, [])

            existing_state = next(
                (
                    state
                    for state in player_pending
                    if state["first"] == combo
                ),
                None,
            )

            if existing_state and existing_state["expires_turn"] >= result.turn:
                if combo in (
                        "Сосредоточение II",
                        "Деморализующая волна II",
                ):
                    existing_state["expires_turn"] += sequence["turns"]
            else:
                if combo == "Резня II":
                    expires_turn = result.turn
                else:
                    expires_turn = result.turn + sequence["turns"]

                player_pending.append(
                    {
                        "first": combo,
                        "expires_turn": expires_turn,
                    }
                )

    # ---------------------------------------------------------
    # 3. Проверяем предупреждения.
    #
    # ВАЖНО:
    # первый приём тоже проверяется СЕЙЧАС.
    #
    # Поэтому Сосредоточение на ходу 7 при достаточном
    # количестве ОД даёт предупреждение уже на ходу 7.
    # ---------------------------------------------------------
    warnings = []

    for player, sequences in pending.items():
        balance = result.balances.get(player, {})

        for state in sequences:
            first_combo = state["first"]
            expires_turn = state["expires_turn"]

            # После окончания окна связка больше не действует.
            if result.turn > expires_turn:
                continue

            sequence = WARNING_SEQUENCES.get(first_combo)

            if not sequence:
                continue

            target = sequence["target"]
            cost = sequence["cost"]

            # Предупреждение относится к следующему ходу.
            # Если на следующем ходу игрок будет под 🔇,
            # предупреждение не показываем.
            if player in silenced_players:
                continue

            ready = all(
                balance.get(symbol, 0) >= amount
                for symbol, amount in cost.items()
            )

            if ready:
                future_turns = max(
                    0,
                    expires_turn - result.turn,
                )

                # Получаем эмодзи клана игрока.
                clan = player_clans.get(player, "")
                clan_emoji = clan.split()[0] if clan else ""

                if future_turns > 0:
                    warnings.append(
                        (
                            player,
                            f"⚠️ {clan_emoji}{player}: после «{first_combo}» "
                            f"доступен «{target}» ⏳{future_turns}"
                        )
                    )
                elif first_combo == "Резня II":
                    warnings.append(
                        (
                            player,
                            f"⚠️ {clan_emoji}{player}: после «{first_combo}» "
                            f"доступен «{target}»"
                        )
                    )

    # ---------------------------------------------------------
    # 4. Удаляем истёкшие связки.
    # ---------------------------------------------------------
    expired_players = []

    for player, sequences in pending.items():
        active_sequences = [
            state
            for state in sequences
            if result.turn <= state["expires_turn"]
        ]

        if active_sequences:
            pending[player] = active_sequences
        else:
            expired_players.append(player)

    for player in expired_players:
        pending.pop(player, None)
    # ---------------------------------------------------------
    # Сохраняем состояние
    # ---------------------------------------------------------

    session["pending_sequences"] = pending
    session["processed"].add(result.log_id)
    session["balances"] = result.balances
    session["last_turn"] = result.turn

    # ---------------------------------------------------------
    # ---------------------------------------------------------
    # Формируем ответ
    # ---------------------------------------------------------

    output = format_turn(
        result,
        player_clans,
        warnings,
        status_lines,
        defenders_clan,
        attackers_clan,
    )

    # Добавляем эмодзи класса перед эмодзи клана.
    player_classes = session.get("player_classes", {})

    for player, player_class in player_classes.items():
        match = re.match(r"([^\w\s]+)", player_class)
        if not match:
            continue

        class_emoji = match.group(1)

        # Ищем имя игрока в начале строки после эмодзи клана.
        pattern = re.compile(
            r"(^|\n)([^\w\s<>\n]+)" + re.escape(player),
        )

        output = pattern.sub(
            lambda m: (
                    m.group(1)
                    + class_emoji
                    + m.group(2)
                    + player
            ),
            output,
        )

    await update.message.reply_text(
        output,
        parse_mode="HTML",
    )


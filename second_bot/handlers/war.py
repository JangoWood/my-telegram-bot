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
)

war_sessions = {}


def _empty():
    return {x: 0 for x in OD_TYPES}


async def start_war(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    war_sessions[user_id] = {
        "balances": {},
        "processed": set(),
        "last_turn": 0,
        "pending_sequences": {},
        "disabled_targets": {},
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

        result = apply_turn(
            session["balances"],
            text,
        )

    used_combos = parse_used_combos(text)

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
    # Формируем ответ
    # ---------------------------------------------------------
    output = format_turn(
        result,
        player_clans,
        warnings,
    )

    await update.message.reply_text(
        output,
        parse_mode="HTML",
    )

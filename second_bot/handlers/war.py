from __future__ import annotations

from collections import defaultdict
from telegram import Update
from telegram.ext import ContextTypes

from services.war_od import (
    OD_TYPES,
    WARNING_SEQUENCES,
    apply_turn,
    format_turn,
    parse_used_combos,
    check_warning_sequences,
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
    }

    await update.message.reply_text(
        "⚔️ Учёт ОД запущен.\n\n"
        "Присылай сообщения с логами ходов.\n"
        "Пока считаю только ОД: траты → начисления → остаток."
    )


async def stop_war(update: Update, context: ContextTypes.DEFAULT_TYPE):
    war_sessions.pop(update.effective_user.id, None)
    await update.message.reply_text("🛑 Учёт ОД остановлен.")


async def war_log(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    session = war_sessions.get(user_id)

    if not session or not update.message or not update.message.text:
        return

    text = update.message.text

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
    # Если ход пришёл не по порядку — начинаем расчёт заново
    # ---------------------------------------------------------
    if session["last_turn"] and result.turn <= session["last_turn"]:
        session["balances"] = {}
        session["pending_sequences"] = {}

        result = apply_turn(
            session["balances"],
            text,
        )

    # ---------------------------------------------------------
    # Приёмы, использованные в текущем ходу
    # ---------------------------------------------------------
    used_combos = parse_used_combos(text)

    pending = session.get("pending_sequences", {})

    # ---------------------------------------------------------
    # Удаляем из pending те связки, чей второй приём
    # уже был использован в ТЕКУЩЕМ ходу.
    #
    # Это делаем до добавления новых связок.
    # ---------------------------------------------------------
    for player, combos in used_combos.items():
        if player not in pending:
            continue

        finished_targets = set(combos)
        remaining_sequences = []

        for state in pending[player]:
            first_combo = state["first"]
            sequence = WARNING_SEQUENCES.get(first_combo)

            if not sequence:
                continue

            target = sequence["target"]

            if target in finished_targets:
                # Второй приём использован.
                # Связка полностью закрыта.
                continue

            remaining_sequences.append(state)

        if remaining_sequences:
            pending[player] = remaining_sequences
        else:
            pending.pop(player, None)

    # ---------------------------------------------------------
    # Добавляем первые приёмы, использованные ТЕКУЩЕМ ходу.
    #
    # ВАЖНО:
    # новый first_combo НЕ уменьшаем сейчас.
    #
    # Например:
    # Сосредоточение на ходу 8
    # remaining = 3
    #
    # Эти 3 хода будут:
    # 9, 10, 11
    # ---------------------------------------------------------
    for player, combos in used_combos.items():
        for combo in combos:
            sequence = WARNING_SEQUENCES.get(combo)

            if not sequence:
                continue

            player_pending = pending.setdefault(player, [])

            already_pending = any(
                state["first"] == combo
                for state in player_pending
            )

            if not already_pending:
                player_pending.append(
                    {
                        "first": combo,
                        "remaining": sequence["turns"],
                        "started_turn": result.turn,
                    }
                )

    # ---------------------------------------------------------
    # Проверяем предупреждения ПО ТЕКУЩЕМУ ходу.
    #
    # Для новой связки первый приём уже применён сейчас,
    # но её окно начинается со следующего хода.
    #
    # Поэтому предупреждение для НОВОЙ связки здесь
    # не показываем.
    # ---------------------------------------------------------
    warnings = []

    for player, sequences in pending.items():
        balance = result.balances.get(player, {})

        for state in sequences:
            first_combo = state["first"]
            remaining = state["remaining"]
            started_turn = state["started_turn"]

            # Связка создана именно сейчас.
            # Она начинает действовать со следующего хода.
            if started_turn == result.turn:
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

            if ready and remaining > 0:
                warnings.append(
                    f"⚠️ {player}: после «{first_combo}» "
                    f"доступен «{target}» "
                    f"(осталось ходов: {remaining})"
                )

    # ---------------------------------------------------------
    # После проверки текущего хода уменьшаем срок
    # существующих связок.
    #
    # Но только тех, которые были активны ДО текущего хода.
    #
    # Например:
    # Ход 8: Сосредоточение → 3
    # Ход 9: предупреждение → потом 2
    # Ход 10: предупреждение → потом 1
    # Ход 11: предупреждение → потом 0
    # Ход 12: связки уже нет.
    # ---------------------------------------------------------
    expired_players = []

    for player, sequences in pending.items():
        updated_sequences = []

        for state in sequences:
            if state["started_turn"] == result.turn:
                updated_sequences.append(state)
                continue

            state["remaining"] -= 1

            if state["remaining"] > 0:
                updated_sequences.append(state)

        if updated_sequences:
            pending[player] = updated_sequences
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
    output = format_turn(result)

    if warnings:
        output += "\n\n" + "\n".join(warnings)

    await update.message.reply_text(output)

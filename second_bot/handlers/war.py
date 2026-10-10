from __future__ import annotations

from collections import defaultdict
from telegram import Update
from telegram.ext import ContextTypes

from services.war_od import (
    OD_TYPES,
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

    # Сначала рассчитываем текущий ход.
    result = apply_turn(session["balances"], text)

    # Не обрабатываем один и тот же лог дважды.
    if result.log_id in session["processed"]:
        await update.message.reply_text(
            f"ℹ️ Ход {result.turn} уже обработан. Повторно не считаю."
        )
        return

    # Если ход пришёл не по порядку — начинаем расчёт заново.
    if session["last_turn"] and result.turn <= session["last_turn"]:
        session["balances"] = {}
        session["pending_sequences"] = {}

        result = apply_turn(
            session["balances"],
            text,
        )

    # ---------------------------------------------------------
    # Какие специальные приёмы использованы в текущем ходу
    # ---------------------------------------------------------
    used_combos = parse_used_combos(text)

    pending = session.get("pending_sequences", {})

    # ---------------------------------------------------------
    # Добавляем первые приёмы новых связок.
    # ---------------------------------------------------------
    for player, combos in used_combos.items():
        for combo in combos:
            if combo in WARNING_SEQUENCES:
                player_pending = pending.setdefault(player, [])

                if combo not in player_pending:
                    player_pending.append(combo)

    # ---------------------------------------------------------
    # Если второй приём связки уже использован,
    # закрываем эту связку.
    # ---------------------------------------------------------
    for player, combos in used_combos.items():
        if player not in pending:
            continue

        finished = set(combos)

        remaining = []

        for first_combo in pending[player]:
            sequence = WARNING_SEQUENCES.get(first_combo)

            if not sequence:
                continue

            target = sequence["target"]

            if target in finished:
                # Второй приём уже применён —
                # больше ждать его не нужно.
                continue

            remaining.append(first_combo)

        if remaining:
            pending[player] = remaining
        else:
            pending.pop(player, None)

    # ---------------------------------------------------------
    # Сохраняем состояние после текущего хода.
    # ---------------------------------------------------------
    session["pending_sequences"] = pending
    session["processed"].add(result.log_id)
    session["balances"] = result.balances
    session["last_turn"] = result.turn

    # ---------------------------------------------------------
    # Проверяем возможность продолжить связку
    # по ОД ПОСЛЕ всех действий текущего хода.
    # ---------------------------------------------------------
    warnings = check_warning_sequences(
        result.balances,
        pending,
    )

    # ---------------------------------------------------------
    # Формируем обычный отчёт.
    # ---------------------------------------------------------
    output = format_turn(result)

    if warnings:
        output += "\n\n" + "\n".join(warnings)

    await update.message.reply_text(output)

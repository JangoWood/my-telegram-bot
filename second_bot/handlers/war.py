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

    # Проверяем ход заранее, чтобы не считать дубликаты.
    result = apply_turn(session["balances"], text)

    if result.log_id in session["processed"]:
        await update.message.reply_text(
            f"ℹ️ Ход {result.turn} уже обработан. Повторно не считаю."
        )
        return

    # ---------------------------------------------------------
    # ПРЕДУПРЕЖДЕНИЯ ПО ПОСЛЕДОВАТЕЛЬНОСТЯМ
    # ---------------------------------------------------------
    #
    # session["pending_sequences"] содержит приёмы,
    # которые игрок использовал на предыдущем ходу.
    #
    # Проверяем их против ОД, накопленного к началу текущего хода.
    #
    warnings = check_warning_sequences(
        session["balances"],
        session.get("pending_sequences", {}),
    )

    # ---------------------------------------------------------
    # Если пришёл ход не по порядку — начинаем расчёт заново.
    # ---------------------------------------------------------
    if session["last_turn"] and result.turn <= session["last_turn"]:
        session["balances"] = {}

        result = apply_turn(
            session["balances"],
            text,
        )

        # После сброса старые предупреждения уже не актуальны.
        warnings = []

    # ---------------------------------------------------------
    # Сохраняем обработанный ход
    # ---------------------------------------------------------
    session["processed"].add(result.log_id)
    session["balances"] = result.balances
    session["last_turn"] = result.turn

    # ---------------------------------------------------------
    # Запоминаем специальные приёмы текущего хода.
    #
    # Они будут проверены уже на СЛЕДУЮЩЕМ ходу.
    # ---------------------------------------------------------
    session["pending_sequences"] = parse_used_combos(text)

    # ---------------------------------------------------------
    # Формируем обычный отчёт ОД
    # ---------------------------------------------------------
    output = format_turn(result)

    # ---------------------------------------------------------
    # Добавляем предупреждения
    # ---------------------------------------------------------
    if warnings:
        output += "\n\n" + "\n".join(warnings)

    await update.message.reply_text(output)

from telegram import Update
from telegram.ext import ContextTypes

from services.combo_loader import get_combo


async def getcombo_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    if not context.args:
        await update.message.reply_text(
            "Использование:\n"
            "/getcombo название приема"
        )
        return

    combo_name = " ".join(context.args).strip()

    combo = get_combo(combo_name)

    if combo is None:
        await update.message.reply_text(
            f"❌ Прием «{combo_name}» не найден."
        )
        return

    lines = [
        f"📋 <b>{combo['name']}</b>",
        "",
    ]

    if combo["cost"]:
        lines.append(f"💠 Стоимость: {combo['cost']}")

    if combo["description"]:
        lines.extend([
            "",
            combo["description"],
        ])

    if combo["uses"] is not None:
        lines.extend([
            "",
            f"🔄 Кол-во использований: {combo['uses']}",
        ])

    if combo["requirements"]:
        lines.extend([
            "",
            "<b>Требования:</b>",
        ])

        lines.extend(
            f"• {requirement}"
            for requirement in combo["requirements"]
        )

    await update.message.reply_text(
        "\n".join(lines),
        parse_mode="HTML",
    )
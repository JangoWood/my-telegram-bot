"""Команда /f — поиск игроков по специализации."""

from telegram import Update
from telegram.ext import ContextTypes

from services.realm_players import get_all_players_from_realm


async def spec_search(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Поиск игроков по специализации из таблицы Ремесло."""

    if not context.args:
        await update.message.reply_text(
            "🔍 <b>Поиск по специализации</b>\n\n"
            "Примеры:\n"
            "  /f крафтер — все крафтеры\n"
            "  /f крафтер ГМ4 — только ГМ4\n"
            "  /f кулинария ПМ3 — только ПМ3\n\n"
            "📋 <b>Доступные специализации и синонимы:</b>\n"
            "  • крафтер / крафт / к\n"
            "  • рыбалка / рыба / р\n"
            "  • шахтёр / шахта / ш\n"
            "  • охота / охотник / о\n"
            "  • кулинария / еда / кухня / кул\n"
            "  • алхимия / алхим / алх / а\n"
            "  • плавильщик / плавка / пл\n"
            "  • фермер / ферма / ф",
            parse_mode="HTML"
        )
        return

    search_input = context.args[0].lower()
    level_filter = context.args[1].upper() if len(context.args) > 1 else None

    synonyms = {
        'крафтер': 'Крафтер', 'крафт': 'Крафтер', 'к': 'Крафтер',
        'рыбалка': 'Рыбалка', 'рыба': 'Рыбалка', 'р': 'Рыбалка',
        'шахтёр': 'Шахтёр', 'шахта': 'Шахтёр', 'ш': 'Шахтёр',
        'охота': 'Охота', 'охотник': 'Охота', 'о': 'Охота',
        'кулинария': 'Кулинария', 'еда': 'Кулинария',
        'кухня': 'Кулинария', 'кул': 'Кулинария',
        'алхимия': 'Алхимия', 'алхим': 'Алхимия',
        'алх': 'Алхимия', 'а': 'Алхимия',
        'плавильщик': 'Плавильщик', 'плавка': 'Плавильщик',
        'пл': 'Плавильщик',
        'фермер': 'Фермер', 'ферма': 'Фермер', 'ф': 'Фермер',
    }

    skill_name = synonyms.get(search_input)

    if not skill_name:
        await update.message.reply_text(
            f"❌ Специализация '{search_input}' не найдена.\n\n"
            "📋 <b>Доступные:</b> крафтер, рыбалка, шахтёр, "
            "охота, кулинария, алхимия, плавильщик, фермер",
            parse_mode="HTML"
        )
        return

    all_players = get_all_players_from_realm()

    if not all_players:
        await update.message.reply_text(
            "❌ Нет данных в таблице Ремесло"
        )
        return

    levels = {}

    for player in all_players:
        level = player['skills'].get(skill_name, '')

        if not level or level == '-':
            continue

        if level_filter and level.upper() != level_filter:
            continue

        if level not in levels:
            levels[level] = []

        levels[level].append({
            'name': player['name'],
            'tag': player['tag']
        })

    if not levels:
        filter_text = (
            f" с уровнем {level_filter}"
            if level_filter
            else ""
        )

        await update.message.reply_text(
            f"❌ Нет игроков по специализации "
            f"'{skill_name}'{filter_text}"
        )
        return

    def sort_key(level):
        order = {
            'Э': 1,
            'ГМ': 2,
            'М': 3,
            'ПМ': 4,
            'У': 5
        }

        if level[:2] in order:
            prefix = level[:2]
            num_start = 2
        elif level[:1] in order:
            prefix = level[:1]
            num_start = 1
        else:
            return (99, 0)

        try:
            num = (
                int(level[num_start:])
                if len(level) > num_start
                else 0
            )
        except ValueError:
            num = 0

        return (order.get(prefix, 99), -num)

    sorted_levels = sorted(
        levels.keys(),
        key=sort_key
    )

    filter_text = f" {level_filter}" if level_filter else ""

    response = (
        f"🔍 <b>Поиск по специализации: "
        f"{skill_name}{filter_text}</b>\n\n"
    )

    for level in sorted_levels:
        players = sorted(
            levels[level],
            key=lambda p: p['name'].lower()
        )

        links = []

        for player in players:
            name = player['name']
            tag = player['tag']

            if tag and tag.startswith('@'):
                username = tag[1:]
                links.append(
                    f'<a href="https://t.me/{username}">'
                    f'{name}</a>'
                )
            else:
                links.append(name)

        response += (
            f"<b>{level}</b> ({len(players)}): "
            f"{', '.join(links)}\n"
        )

        if len(response) > 4000:
            await update.message.reply_text(
                response,
                parse_mode="HTML",
                disable_web_page_preview=True
            )
            response = ""

    if response:
        await update.message.reply_text(
            response,
            parse_mode="HTML",
            disable_web_page_preview=True
        )
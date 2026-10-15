"""Новый тестовый учёт очков действий (ОД) для помощника по клановой войне.

combat_war.py намеренно не используется и не изменяется.
"""

from __future__ import annotations

import hashlib
import re
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Dict, List, Tuple


OD_TYPES = ("🗡", "🛡", "🥊", "⚡️", "🤺", "🌬")
COST_RE = re.compile(r"(🗡|🛡|🥊|⚡️|🤺|🌬)(\d+)")
WARNING_SEQUENCES = {
    "Резня II": {
        "target": "Тысяча ударов II",
        "cost": {"🛡": 1, "🤺": 1},
        "turns": 1,
    },
    "Сосредоточение II": {
        "target": "Отступление II",
        "cost": {"⚡️": 1, "🌬": 1},
        "turns": 3,
    },
    "Деморализующая волна II": {
        "target": "Шоковый удар II",
        "cost": {"🛡": 1, "🌬": 1},
        "turns": 2,
    },
}
TURN_RE = re.compile(r"(?m)\bХод\s+(\d+)\s+👀")
PLAYER_RE = re.compile(r"(?:^|\n)\s*\d+\.\s+.*?\s+([А-Яа-яA-Za-z0-9_]+)\s*(?:🔸(\d+))?\s+❤️\((\d+)/(\d+)\)")
DEAD_RE = re.compile(r"(?:^|\n)\s*\d+\.\s+.*?\s+([А-Яа-яA-Za-z0-9_]+).*?💀")


@dataclass
class PlayerOD:
    name: str
    od: Dict[str, int] = field(default_factory=lambda: {x: 0 for x in OD_TYPES})
    spent: Dict[str, int] = field(default_factory=lambda: {x: 0 for x in OD_TYPES})
    gained: Dict[str, int] = field(default_factory=lambda: {x: 0 for x in OD_TYPES})


@dataclass
class TurnOD:
    turn: int
    log_id: str
    spent: Dict[str, Dict[str, int]]
    gained: Dict[str, Dict[str, int]]
    balances: Dict[str, Dict[str, int]]
    health: Dict[str, tuple[int, int]]


def empty_od() -> Dict[str, int]:
    return {x: 0 for x in OD_TYPES}


def parse_combo_costs(text: str) -> Dict[str, Dict[str, int]]:
    """Возвращает расходы ОД по игрокам за один ход."""
    result: Dict[str, Dict[str, int]] = defaultdict(empty_od)
    for line in text.splitlines():
        if "использует комбинацию" not in line:
            continue
        m = re.search(r"^.*?\s([А-Яа-яA-Za-z0-9_]+)\s+🔸\d+\s+использует комбинацию", line)
        if not m:
            continue
        player = m.group(1)
        costs = re.search(r"\(([^)]*)\)", line)
        if not costs:
            continue
        for symbol, amount in COST_RE.findall(costs.group(1)):
            result[player][symbol] += int(amount)
    return dict(result)

def parse_used_combos(text: str) -> Dict[str, List[str]]:
    """Возвращает применённые приёмы по игрокам за ход."""
    result: Dict[str, List[str]] = defaultdict(list)

    for line in text.splitlines():
        if "использует комбинацию" not in line:
            continue

        player = extract_player_name(
            line.split("использует комбинацию", 1)[0]
        )
        if not player:
            continue

        match = re.search(
            r"использует комбинацию\s+(.+?)\s*\(",
            line
        )
        if not match:
            continue

        combo_name = match.group(1).strip()

        # Возвращаем все использованные комбинации.
        # Логика предупреждений сама отфильтрует только первые приёмы
        # из WARNING_SEQUENCES, а status_effects.py должен видеть и
        # целевые приёмы вроде «Тысяча ударов II» и «Шоковый удар II».
        result[player].append(combo_name)

    return dict(result)

def check_warning_sequences(
    balances: Dict[str, Dict[str, int]],
    pending_sequences: Dict[str, List[dict]],
) -> List[str]:
    warnings = []

    for player, sequences in pending_sequences.items():
        balance = balances.get(player, {})

        for sequence_state in sequences:
            first_combo = sequence_state["first"]
            remaining = sequence_state["remaining"]

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

    return warnings

def _actor_before(line: str, verb: str) -> str | None:
    if verb not in line:
        return None
    prefix = line.split(verb, 1)[0]
    # Берём имя непосредственно перед 🔸уровнем.
    m = re.search(r"([А-Яа-яA-Za-z0-9_]+)\s+🔸\d+\s*$", prefix)
    return m.group(1) if m else None

def extract_player_name(text: str) -> str | None:
    matches = re.findall(
        r"([А-Яа-яЁёA-Za-z0-9_]+)\s+🔸\d+",
        text
    )

    return matches[-1] if matches else None

def parse_players(text: str) -> List[str]:
    result = []

    for line in text.splitlines():
        if not re.match(r"^\s*\d+\.\s+", line):
            continue

        name = extract_player_name(line)

        if name and name not in result:
            result.append(name)

    return result


def parse_player_health(text: str) -> Dict[str, tuple[int, int]]:
    """Возвращает текущее и максимальное здоровье игроков."""
    result = {}

    for line in text.splitlines():
        if line.startswith("Ход боя:") or line.startswith("Следующий ход:"):
            break

        if not re.match(r"^\s*\d+\.\s+", line):
            continue

        player = extract_player_name(line)
        hp_match = re.search(r"❤️\((\d+)/(\d+)\)", line)

        if player and hp_match:
            result[player] = (
                int(hp_match.group(1)),
                int(hp_match.group(2)),
            )

    return result


def parse_player_clans(text: str) -> Dict[str, str]:
    """Определяет клан каждого игрока из блока текущего хода."""
    result = {}

    current_clan = None

    for line in text.splitlines():
        if line.startswith("🔵 Защитники:"):
            current_clan = line.split(":", 1)[1].strip()
            continue

        if line.startswith("🔴 Нападающие:"):
            current_clan = line.split(":", 1)[1].strip()
            continue

        if current_clan and re.match(r"^\s*\d+\.\s+", line):
            player = extract_player_name(line)

            if player:
                result[player] = current_clan

    return result

def parse_war_sides(text: str) -> tuple[str, str]:
    """Возвращает (клан_защитников, клан_нападающих)."""

    defenders_clan = ""
    attackers_clan = ""

    for line in text.splitlines():
        if line.startswith("🔵 Защитники:"):
            defenders_clan = line.split(":", 1)[1].strip()

        elif line.startswith("🔴 Нападающие:"):
            attackers_clan = line.split(":", 1)[1].strip()

    return defenders_clan, attackers_clan

def parse_action_gains(text: str) -> Dict[str, Dict[str, int]]:
    """
    Начисления ОД за боевые события текущего хода.

    🗡 — успешное попадание
    🛡 — успешный блок
    🥊 — крит
    ⚡️ — уклонение
    🤺 — контрудар
    🌬 — удар в блок / удар, от которого увернулись / пробитие блока
    """
    result: Dict[str, Dict[str, int]] = defaultdict(empty_od)

    for line in text.splitlines():

        # ---------------------------------------------------------
        # АТАКА
        # ---------------------------------------------------------
        if "бьет" in line:
            actor_part = line.split("бьет", 1)[0]
            actor = extract_player_name(actor_part)

            if not actor:
                continue

            # 1. Обычное успешное попадание
            if "И наносит" in line:
                result[actor]["🗡"] += 1

            # 2. Атака попала в блок
            if "попадает в блок" in line:
                result[actor]["🌬"] += 1

                target_part = line.split("бьет", 1)[1]
                target_match = re.search(
                    r"([А-Яа-яЁёA-Za-z0-9_]+)\s+🔸\d+",
                    target_part
                )
                target = target_match.group(1) if target_match else None

                if target:
                    result[target]["🛡"] += 1

            # 3. Атака пробила блок
            if "пробивает блок" in line:
                result[actor]["🌬"] += 1

                target_part = line.split("бьет", 1)[1]
                target_match = re.search(
                    r"([А-Яа-яЁёA-Za-z0-9_]+)\s+🔸\d+",
                    target_part
                )
                target = target_match.group(1) if target_match else None

                if target:
                    result[target]["🛡"] += 1
                    print(
                        f"DEBUG ПРОБИЛ БЛОК: "
                        f"атакующий={actor}, защитник={target}"
                    )

            # 4. Крит
            if "🥊" in line:
                result[actor]["🥊"] += 1

        # ---------------------------------------------------------
        # УКЛОНЕНИЕ
        # ---------------------------------------------------------
        if "⚡️ увернулся" in line or "⚡️ увернулась" in line:
            prefix = line.split("⚡️", 1)[0]

            # Атакующий получает 🌬
            if "бьет" in prefix:
                actor_part = prefix.split("бьет", 1)[0]
                actor = extract_player_name(actor_part)

                if actor:
                    result[actor]["🌬"] += 1

            # Увернувшийся получает ⚡️
            dodger = extract_player_name(prefix)

            if dodger:
                result[dodger]["⚡️"] += 1

        # ---------------------------------------------------------
        # КОНТРУДАР
        # ---------------------------------------------------------
        if "контрударом" in line:
            prefix = line.split("контрударом", 1)[0]
            actor = extract_player_name(prefix)

            if actor:
                result[actor]["🤺"] += 1

    return dict(result)


def apply_turn(previous: Dict[str, Dict[str, int]], text: str) -> TurnOD:
    m = TURN_RE.search(text)
    if not m:
        raise ValueError("Не найден номер хода")
    turn = int(m.group(1))
    log_id = hashlib.sha256("\n".join(x.strip() for x in text.splitlines()).encode("utf-8")).hexdigest()

    spent = parse_combo_costs(text)
    gained = parse_action_gains(text)

    names = set(parse_players(text)) | set(previous) | set(spent) | set(gained)
    balances: Dict[str, Dict[str, int]] = {}
    for name in names:
        balances[name] = empty_od()
        for symbol in OD_TYPES:
            balances[name][symbol] = max(0, previous.get(name, {}).get(symbol, 0) - spent.get(name, {}).get(symbol, 0) + gained.get(name, {}).get(symbol, 0))

    health = parse_player_health(text)

    return TurnOD(
        turn=turn,
        log_id=log_id,
        spent=spent,
        gained=gained,
        balances=balances,
        health=health,
    )


def format_turn(
    result,
    player_clans,
    warnings=None,
    status_lines=None,
    defenders_clan="",
    attackers_clan="",
):
    """Формирует вывод ОД по командам и кланам."""

    warnings = warnings or []
    status_lines = status_lines or {}

    # Предупреждения группируем по игроку.
    warnings_by_player = {}

    for player, warning_text in warnings:
        warnings_by_player.setdefault(player, []).append(
            warning_text
        )

    defenders = []
    attackers = []

    for player, balance in result.balances.items():
        clan = player_clans.get(player, "")
        emoji = clan.split()[0] if clan else ""

        item = {
            "name": player,
            "emoji": emoji,
            "balance": balance,
        }

        if clan == defenders_clan:
            defenders.append(item)
        elif clan == attackers_clan:
            attackers.append(item)

    # Стабильный порядок игроков
    defenders.sort(key=lambda x: x["name"].lower())
    attackers.sort(key=lambda x: x["name"].lower())

    lines = [
        f"⚔️ Ход {result.turn}: помощь в КВ",
        "",
    ]

    def append_team(title, players):
        if not players:
            return

        lines.append(title)

        for player in players:
            name = player["name"]
            emoji = player["emoji"]
            od = player["balance"]

            values = " ".join(
                f"{od_type}{od.get(od_type, 0)}"
                for od_type in OD_TYPES
            )

            # Имя, текущее здоровье, максимум и процент
            hp, max_hp = result.health.get(name, (0, 0))
            hp_percent = round(hp / max_hp * 100) if max_hp else 0

            lines.append(
                f"{emoji}{name} ❤️({hp}/{max_hp}) {hp_percent}%"
            )

            # ОД отдельным блоком
            lines.append(
                f"<blockquote>{values}</blockquote>"
            )

            # Активные эффекты отдельной строкой
            for status_line in status_lines.get(name, []):
                lines.append(f"[{status_line}]")

            # Предупреждения сразу после игрока
            for warning in warnings_by_player.get(name, []):
                lines.append(warning)

        lines.append("")

    append_team(
        f"🔵 Защитники: {defenders_clan}",
        defenders,
    )

    append_team(
        f"🔴 Нападающие: {attackers_clan}",
        attackers,
    )

    return "\n".join(lines).rstrip()
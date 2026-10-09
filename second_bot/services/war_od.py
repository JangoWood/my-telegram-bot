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


def _actor_before(line: str, verb: str) -> str | None:
    if verb not in line:
        return None
    prefix = line.split(verb, 1)[0]
    # Берём имя непосредственно перед 🔸уровнем.
    m = re.search(r"([А-Яа-яA-Za-z0-9_]+)\s+🔸\d+\s*$", prefix)
    return m.group(1) if m else None


def parse_action_gains(text: str) -> Dict[str, Dict[str, int]]:
    """Начисления ОД за боевые события текущего хода.

    Правила соответствуют зафиксированной старой механике:
    🗡 попадание, 🛡 блок, 🥊 крит, ⚡️ уклонение,
    🤺 контрудар, 🌬 удар в блок/промах.
    """
    result: Dict[str, Dict[str, int]] = defaultdict(empty_od)

    for line in text.splitlines():
        # Удар игрока с уроном, не заблокированный.
        actor = _actor_before(line, "бьет")
        if actor and "наносит" in line and "попадает в блок" not in line and "И попадает в блок" not in line:
            result[actor]["🗡"] += 1

        # Игрок поставил блок: в строке перед "бьет" находится именно он.
        if actor and "попадает в блок" in line:
            result[actor]["🌬"] += 1
            # Отдельное событие блока относится к атакующему игроку-цели.
            target_part = line.split("бьет", 1)[1]
            target_m = re.search(r"по\s+.*?\s([А-Яа-яA-Za-z0-9_]+)\s*(?:🔸\d+)", target_part)
            if target_m:
                result[target_m.group(1)]["🛡"] += 1

        # Уклонение цели.
        if "увернулся" in line or "увернулась" in line:
            # В строке перед "увернулся" обычно явно стоит имя цели.
            prefix = re.split(r"увернул(?:ся|ась)", line, maxsplit=1)[0]
            m = re.search(r"([А-Яа-яA-Za-z0-9_]+)\s*(?:🔸\d+).*?$", prefix)
            if m:
                result[m.group(1)]["⚡️"] += 1

        # Крит. Считаем только если игрок является субъектом строки.
        if "критическим ударом" in line:
            actor = _actor_before(line, "бьет")
            if actor:
                result[actor]["🥊"] += 1

        # Контрудар принадлежит игроку, имя которого стоит перед "нанес"/"контрударом".
        if "контрудар" in line:
            m = re.search(r"([А-Яа-яA-Za-z0-9_]+)\s+🔸\d+[^\n]*контрудар", line)
            if m:
                result[m.group(1)]["🤺"] += 1

    return dict(result)


def apply_turn(previous: Dict[str, Dict[str, int]], text: str) -> TurnOD:
    m = TURN_RE.search(text)
    if not m:
        raise ValueError("Не найден номер хода")
    turn = int(m.group(1))
    log_id = hashlib.sha256("\n".join(x.strip() for x in text.splitlines()).encode("utf-8")).hexdigest()

    spent = parse_combo_costs(text)
    gained = parse_action_gains(text)

    names = set(previous) | set(spent) | set(gained)
    balances: Dict[str, Dict[str, int]] = {}
    for name in names:
        balances[name] = empty_od()
        for symbol in OD_TYPES:
            balances[name][symbol] = max(0, previous.get(name, {}).get(symbol, 0) - spent.get(name, {}).get(symbol, 0) + gained.get(name, {}).get(symbol, 0))

    return TurnOD(turn=turn, log_id=log_id, spent=spent, gained=gained, balances=balances)


def format_turn(result: TurnOD) -> str:
    lines = [f"⚔️ Ход {result.turn}: учёт ОД"]
    for name in sorted(result.balances, key=str.lower):
        spent = " ".join(f"{s}{result.spent.get(name, {}).get(s, 0)}" for s in OD_TYPES if result.spent.get(name, {}).get(s, 0)) or "—"
        gained = " ".join(f"{s}{result.gained.get(name, {}).get(s, 0)}" for s in OD_TYPES if result.gained.get(name, {}).get(s, 0)) or "—"
        balance = " ".join(f"{s}{result.balances[name][s]}" for s in OD_TYPES)
        lines.append(f"{name}\n  − {spent}\n  + {gained}\n  = {balance}")
    return "\n".join(lines)

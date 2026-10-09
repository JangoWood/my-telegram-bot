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
            if "критическим ударом" in line:
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

    return TurnOD(turn=turn, log_id=log_id, spent=spent, gained=gained, balances=balances)


def format_turn(result: TurnOD) -> str:
    lines = [f"⚔️ Ход {result.turn}: учёт ОД"]
    for name in sorted(result.balances, key=str.lower):
        spent = " ".join(f"{s}{result.spent.get(name, {}).get(s, 0)}" for s in OD_TYPES if result.spent.get(name, {}).get(s, 0)) or "—"
        gained = " ".join(f"{s}{result.gained.get(name, {}).get(s, 0)}" for s in OD_TYPES if result.gained.get(name, {}).get(s, 0)) or "—"
        balance = " ".join(f"{s}{result.balances[name][s]}" for s in OD_TYPES)
        lines.append(f"{name}\n  − {spent}\n  + {gained}\n  = {balance}")
    return "\n".join(lines)

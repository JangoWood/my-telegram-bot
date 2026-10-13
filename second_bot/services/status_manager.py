def apply_status(
    statuses,
    target,
    effect,
):
    """
    Накладывает эффект на цель.

    statuses:
        словарь активных эффектов игрока

    target:
        имя игрока

    effect:
        описание эффекта из status_effects.py
    """

    stack_key = effect.get("stack_key", effect["status"])
    duration = effect.get("duration", 1)
    repeat_mode = effect.get("repeat_mode", "stack")

    player_statuses = statuses.setdefault(target, {})

    existing = player_statuses.get(stack_key)

    if existing:
        if repeat_mode == "replace":
            existing["duration"] = duration
        else:
            existing["duration"] += duration
    else:
        player_statuses[stack_key] = {
            "status": effect["status"],
            "duration": duration,
        }


def tick_statuses(statuses):
    """
    Уменьшает длительность активных эффектов на 1 ход.
    """

    expired = []

    for player, player_statuses in statuses.items():
        for stack_key, effect in player_statuses.items():
            effect["duration"] -= 1

            if effect["duration"] <= 0:
                expired.append((player, stack_key))

    for player, stack_key in expired:
        statuses[player].pop(stack_key, None)

    for player in list(statuses):
        if not statuses[player]:
            statuses.pop(player, None)


def has_status(statuses, player, stack_key):
    """
    Проверяет, есть ли у игрока активный эффект.
    """

    return (
        player in statuses
        and stack_key in statuses[player]
        and statuses[player][stack_key]["duration"] > 0
    )
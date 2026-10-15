
def apply_status(
    statuses,
    player,
    effect,
    player_clans,
    target_player=None,
):
    """Накладывает эффект на конкретную цель или по старым правилам."""

    target_type = effect.get("target", "enemy")
    player_clan = player_clans.get(player, "")

    if target_type == "enemy" and target_player:
        targets = [target_player]

    elif target_type in ("enemy", "enemy_team"):
        targets = [
            name
            for name, clan in player_clans.items()
            if clan and clan != player_clan
        ]

    else:
        targets = [player]

    for target in targets:
        _apply_to_target(statuses, target, effect)



def _apply_to_target(statuses, target, effect):
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
    return (
        player in statuses
        and stack_key in statuses[player]
        and statuses[player][stack_key]["duration"] > 0
    )


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
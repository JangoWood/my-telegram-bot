import re
from services.war_od import apply_turn, format_turn

with open('/mnt/data/кв.txt', encoding='utf-8') as f:
    text = f.read()

headers = list(re.finditer(r'(?m)^.*?Ход\s+\d+\s+👀.*$', text))
balances = {}
seen = set()

for i, match in enumerate(headers):
    end = headers[i + 1].start() if i + 1 < len(headers) else len(text)
    chunk = text[match.start():end]
    result = apply_turn(balances, chunk)
    if result.log_id in seen:
        continue
    seen.add(result.log_id)
    # Ход 1 после завершения первого боя начинается новым боем.
    if i and result.turn <= previous_turn:
        balances = {}
        result = apply_turn(balances, chunk)
    balances = result.balances
    previous_turn = result.turn

print(f'Проверено ходов: {len(headers)}')
print(f'Игроков в последнем состоянии: {len(balances)}')
print(format_turn(result))

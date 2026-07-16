from __future__ import annotations

import json
from pathlib import Path
from typing import Any

PLAN_PATH = Path(__file__).with_name('route_plan.json')
REQUIRED_TEAMS = ('Красные', 'Белые', 'Оранжевые', 'Зелёные', 'Синие')
REQUIRED_LOCATIONS = {'culture', 'science', 'history', 'memory', 'open'}


def load_route_plan(path: Path = PLAN_PATH) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding='utf-8'))
    routes = data.get('routes', {})
    slots = data.get('time_slots', [])
    if tuple(routes) != REQUIRED_TEAMS:
        raise RuntimeError('route_plan.json: команды отсутствуют или расположены в неверном порядке')
    if len(slots) != 5:
        raise RuntimeError('route_plan.json: должно быть ровно пять временных блоков')
    for team, route in routes.items():
        if len(route) != 5 or set(route) != REQUIRED_LOCATIONS:
            raise RuntimeError(f'route_plan.json: маршрут команды {team} неполон или содержит повторы')
    return data


PLAN = load_route_plan()
ROUTES: dict[str, tuple[str, ...]] = {
    team: tuple(route) for team, route in PLAN['routes'].items()
}
TIME_SLOTS: tuple[str, ...] = tuple(PLAN['time_slots'])

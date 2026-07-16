from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class TeamGame:
    game_id: str
    team: str
    location: str
    title: str
    mechanic: str
    prompt: str
    options: tuple[str, ...]
    correct: int
    success: str
    hint: str


CATALOG_DIR = Path(__file__).with_name('game_catalog')
TEAM_FILES = {
    'Красные': 'red.json',
    'Белые': 'white.json',
    'Оранжевые': 'orange.json',
    'Зелёные': 'green.json',
    'Синие': 'blue.json',
}


def _load_game(row: dict[str, Any]) -> TeamGame:
    return TeamGame(
        game_id=str(row['game_id']),
        team=str(row['team']),
        location=str(row['location']),
        title=str(row['title']),
        mechanic=str(row['mechanic']),
        prompt=str(row['prompt']),
        options=tuple(str(value) for value in row['options']),
        correct=int(row['correct']),
        success=str(row['success']),
        hint=str(row['hint']),
    )


def load_catalog() -> tuple[TeamGame, ...]:
    games: list[TeamGame] = []
    for team, filename in TEAM_FILES.items():
        rows = json.loads((CATALOG_DIR / filename).read_text(encoding='utf-8'))
        loaded = [_load_game(row) for row in rows]
        if any(item.team != team for item in loaded):
            raise RuntimeError(f'{filename}: найдена игра другой команды')
        games.extend(loaded)
    return tuple(games)


GAMES = load_catalog()
TEAM_GAMES: dict[str, tuple[TeamGame, ...]] = {
    team: tuple(game for game in GAMES if game.team == team)
    for team in TEAM_FILES
}
GAMES_BY_ID: dict[str, TeamGame] = {game.game_id: game for game in GAMES}
GAMES_BY_TEAM_LOCATION: dict[tuple[str, str], tuple[TeamGame, ...]] = {
    (team, location): tuple(
        game for game in GAMES if game.team == team and game.location == location
    )
    for team in TEAM_GAMES
    for location in ('culture', 'science', 'history', 'memory', 'open')
}


def validate_catalog() -> list[str]:
    errors: list[str] = []
    if len(GAMES) != 50:
        errors.append(f'Ожидалось 50 игр, найдено {len(GAMES)}')
    if len(GAMES_BY_ID) != len(GAMES):
        errors.append('Есть повторяющиеся идентификаторы игр')
    for team, games in TEAM_GAMES.items():
        if len(games) != 10:
            errors.append(f'У команды {team} не 10 игр: {len(games)}')
        for location in ('culture', 'science', 'history', 'memory', 'open'):
            count = len(GAMES_BY_TEAM_LOCATION[(team, location)])
            if count != 2:
                errors.append(f'{team}/{location}: ожидалось 2 игры, найдено {count}')
    for item in GAMES:
        if not 0 <= item.correct < len(item.options):
            errors.append(f'{item.game_id}: неверный индекс ответа')
        if len(item.options) < 2 or len(item.options) > 4:
            errors.append(f'{item.game_id}: допустимо 2-4 варианта')
    return errors

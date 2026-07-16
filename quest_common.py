from __future__ import annotations

import secrets
from typing import Any

from aiogram.fsm.state import State, StatesGroup
from aiogram.types import KeyboardButton, Message, ReplyKeyboardMarkup

import app as game
from game_data import LOCATIONS, OPEN_SPACES, TEAM_COLORS
from route_config import ROUTES, TIME_SLOTS
from storage import utcnow
from team_games import GAMES_BY_TEAM_LOCATION, TeamGame

LOCATION_TITLES = {key: value['title'] for key, value in LOCATIONS.items()} | {'open': OPEN_SPACES['title']}
LOCATION_PLACES = {key: value['place'] for key, value in LOCATIONS.items()} | {'open': OPEN_SPACES['place']}
NUMBER_MARKS = ('1️⃣', '2️⃣', '3️⃣', '4️⃣')


class GateFlow(StatesGroup):
    code = State()


def main_menu(admin: bool = False) -> ReplyKeyboardMarkup:
    keyboard = [
        [KeyboardButton(text='📍 Текущая точка'), KeyboardButton(text='🎮 10 игр команды')],
        [KeyboardButton(text='🗺 Маршрут'), KeyboardButton(text='📜 Прогресс')],
        [KeyboardButton(text='🦋 Состояние Архива'), KeyboardButton(text='🗃 Моя коллекция')],
        [KeyboardButton(text='🗓 Программа'), KeyboardButton(text='❓ Архивариус')],
        [KeyboardButton(text='🤝 Партнёры проекта')],
    ]
    if admin:
        keyboard.append([KeyboardButton(text='🛡 Управление проектом')])
    return ReplyKeyboardMarkup(
        keyboard=keyboard,
        resize_keyboard=True,
        input_field_placeholder='Выбери следующий шаг',
    )


game.main_menu = main_menu


def waiting_menu(admin: bool = False) -> ReplyKeyboardMarkup:
    keyboard = [
        [KeyboardButton(text='🗓 Программа'), KeyboardButton(text='ℹ️ Как играть')],
        [KeyboardButton(text='🤝 Партнёры проекта')],
    ]
    if admin:
        keyboard.append([KeyboardButton(text='🛡 Управление проектом')])
    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)


def progress_bar(done: int, total: int) -> str:
    done = max(0, min(done, total))
    return '■' * done + '□' * (total - done)


def is_assigned(user: Any) -> bool:
    return bool(user and user['team'] in TEAM_COLORS)


def ordered_games(team: str) -> tuple[TeamGame, ...]:
    return tuple(
        item
        for location in ROUTES[team]
        for item in GAMES_BY_TEAM_LOCATION[(team, location)]
    )


async def init_team_quest() -> None:
    statements = (
        '''CREATE TABLE IF NOT EXISTS team_route_unlocks(
            event_date TEXT NOT NULL,
            team TEXT NOT NULL,
            location_key TEXT NOT NULL,
            step_index INTEGER NOT NULL,
            unlocked_by INTEGER NOT NULL,
            unlocked_at TEXT NOT NULL,
            PRIMARY KEY(event_date, team, location_key)
        )''',
        '''CREATE TABLE IF NOT EXISTS team_game_progress(
            user_id INTEGER NOT NULL,
            game_id TEXT NOT NULL,
            attempts INTEGER NOT NULL DEFAULT 0,
            passed INTEGER NOT NULL DEFAULT 0,
            completed_at TEXT,
            PRIMARY KEY(user_id, game_id)
        )''',
        '''CREATE TABLE IF NOT EXISTS live_location_codes(
            location_key TEXT PRIMARY KEY,
            code TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            updated_by INTEGER NOT NULL DEFAULT 0
        )''',
        'CREATE INDEX IF NOT EXISTS idx_route_unlock_team ON team_route_unlocks(event_date, team, step_index)',
        'CREATE INDEX IF NOT EXISTS idx_team_game_user ON team_game_progress(user_id, passed)',
    )
    for statement in statements:
        await game.db.execute(statement)

    used = {str(row['code']) for row in await game.db.all('SELECT code FROM live_location_codes')}
    for location in ('culture', 'science', 'history', 'memory', 'open'):
        existing = await game.db.one(
            'SELECT code FROM live_location_codes WHERE location_key = ?',
            (location,),
        )
        if existing:
            continue
        while True:
            code = str(secrets.randbelow(9000) + 1000)
            if code not in used:
                used.add(code)
                break
        await game.db.execute(
            '''INSERT INTO live_location_codes(location_key, code, updated_at, updated_by)
               VALUES(?, ?, ?, 0)''',
            (location, code, utcnow()),
        )


async def completed_locations(user: Any) -> set[str]:
    if not is_assigned(user):
        return set()
    rows = await game.db.all(
        '''SELECT location_key FROM team_route_unlocks
           WHERE event_date = ? AND team = ?''',
        (user['event_date'], user['team']),
    )
    return {str(row['location_key']) for row in rows}


async def current_stage(user: Any) -> tuple[int, str] | None:
    completed = await completed_locations(user)
    for index, key in enumerate(ROUTES[user['team']]):
        if key not in completed:
            return index, key
    return None


async def team_route_done_count(user: Any) -> int:
    return len(await completed_locations(user))


async def passed_games(user_id: int) -> set[str]:
    rows = await game.db.all(
        'SELECT game_id FROM team_game_progress WHERE user_id = ? AND passed = 1',
        (user_id,),
    )
    return {str(row['game_id']) for row in rows}


async def game_is_unlocked(user: Any, item: TeamGame) -> bool:
    if not is_assigned(user) or item.team != user['team']:
        return False
    route = ROUTES[user['team']]
    location_index = route.index(item.location)
    completed = await completed_locations(user)
    pair = GAMES_BY_TEAM_LOCATION[(user['team'], item.location)]
    pair_index = pair.index(item)
    if item.location in completed:
        return True
    current = await current_stage(user)
    return bool(current and current[0] == location_index and pair_index == 0)


async def route_code(location: str) -> str:
    row = await game.db.one(
        'SELECT code FROM live_location_codes WHERE location_key = ?',
        (location,),
    )
    return str(row['code']) if row else ''


def option_text(options: tuple[str, ...]) -> str:
    return '\n\n'.join(
        f'<b>{NUMBER_MARKS[index]}</b> {game.escape(value)}'
        for index, value in enumerate(options)
    )


def option_keyboard(prefix: str, count: int):
    return game.inline_buttons(
        [(NUMBER_MARKS[index], f'{prefix}:{index}') for index in range(count)],
        columns=count,
    )


async def require_assigned(message: Message):
    user = await game.get_user(message.from_user.id)
    if not user:
        await message.answer('Сначала открой Архив командой /start.')
        return None
    if not is_assigned(user):
        await message.answer(
            '<b>Команда ещё не выдана.</b>\n\n'
            'После регистрации Архивариус распределяет участников вручную, чтобы сохранить равные команды. '
            'Когда команда будет назначена, бот пришлёт маршрут автоматически.',
            reply_markup=waiting_menu(await game.is_admin(message.from_user.id)),
        )
        return None
    return user

from __future__ import annotations

import asyncio
import shutil
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import BufferedInputFile, CallbackQuery, Message

import app as game
from game_data import PARAMETER_LABELS, TEAM_COLORS, format_event_date
from quest_common import LOCATION_TITLES, current_stage, is_assigned, passed_games, progress_bar
from route_config import ROUTES, TIME_SLOTS
from team_games import GAMES_BY_ID

router = Router(name='last_keeper_production_v4')

COLLECTION_NAMES = {
    'culture': 'Живое слово',
    'science': 'Ответственное открытие',
    'history': 'Проверенный источник',
    'memory': 'Человеческий голос',
    'open': 'Карта культурных связей',
}


async def archive_collection(target: Message, user_id: int) -> None:
    user = await game.get_user(user_id)
    if not is_assigned(user):
        await target.answer('Цифровая коллекция откроется после назначения команды.')
        return

    rows = await game.db.all(
        'SELECT game_id FROM team_game_progress WHERE user_id = ? AND passed = 1',
        (user_id,),
    )
    passed_ids = {str(row['game_id']) for row in rows}
    grouped: dict[str, list[str]] = defaultdict(list)
    for game_id in passed_ids:
        item = GAMES_BY_ID.get(game_id)
        if item:
            grouped[item.location].append(item.title)

    lines = [
        '<b>Цифровая коллекция Хранителя</b>',
        f'Команда: <b>{game.escape(user["team"])}</b>',
        f'Собрано фрагментов: {progress_bar(len(passed_ids), 10)}  {len(passed_ids)}/10',
        '',
        'Каждый фрагмент — не балл, а тема, которую ты помог вернуть в Архив памяти России.',
        '',
    ]
    for key in ('culture', 'science', 'history', 'memory', 'open'):
        titles = sorted(grouped.get(key, []))
        state = ' · '.join(game.escape(title) for title in titles) if titles else 'ещё не открыто'
        lines.append(f'<b>{COLLECTION_NAMES[key]}</b>\n{state}')

    choices = await game.team_choices(user['event_date'], user['team'])
    if choices:
        values = await game.team_parameters(user['event_date'], user['team'])
        positive = sorted(
            ((key, value) for key, value in values.items() if value > 0),
            key=lambda item: item[1],
            reverse=True,
        )[:3]
        contour = ', '.join(PARAMETER_LABELS[key] for key, _ in positive) or 'ещё формируется'
        lines.extend(['', f'<b>След команды:</b> {contour}'])

    await target.answer(
        '\n\n'.join(lines),
        reply_markup=game.inline_buttons([
            ('🎮 Продолжить игры', 'tq:games'),
            ('📍 Текущая точка', 'tq:current'),
            ('📜 Общий прогресс', 'tq:progress'),
        ]),
    )


async def mission_status(target: Message, user_id: int) -> None:
    user = await game.get_user(user_id)
    if not is_assigned(user):
        await target.answer('Архивариус ещё формирует твою команду. После назначения откроется первая глава.')
        return
    stage = await current_stage(user)
    completed = await game.db.all(
        'SELECT location_key FROM team_route_unlocks WHERE event_date = ? AND team = ?',
        (user['event_date'], user['team']),
    )
    done = {str(row['location_key']) for row in completed}
    choices = await game.team_choices(user['event_date'], user['team'])
    passed = len(await passed_games(user_id))

    if stage:
        index, key = stage
        now_text = (
            f'<b>Глава {index + 1}/5 · {LOCATION_TITLES[key]}</b>\n'
            f'Время: {TIME_SLOTS[index]}\n'
            'Следующая глава откроется только после подтверждения живого задания.'
        )
    else:
        now_text = '<b>Все пять глав открыты.</b> Команда готова увидеть последствия в финале «Эффект бабочки».'

    echo = ''
    if choices:
        last = choices[-1]
        echo = (
            '\n\n<b>Эхо прошлого выбора</b>\n'
            f'{game.escape(last["narrator_hint"] or last["immediate_text"])}\n'
            '<i>Архив помнит решения команды и переносит их последствия дальше по маршруту.</i>'
        )

    await target.answer(
        '<b>Состояние Архива</b>\n\n'
        f'Живой маршрут: {progress_bar(len(done), 5)}  {len(done)}/5\n'
        f'Личные игры: {progress_bar(passed, 10)}  {passed}/10\n'
        f'Решения команды: {progress_bar(len(choices), 4)}  {len(choices)}/4\n\n'
        f'{now_text}{echo}',
        reply_markup=game.inline_buttons([
            ('📍 Открыть текущую главу', 'tq:current'),
            ('🗃 Моя коллекция', 'v4:collection'),
        ]),
    )


@router.message(Command('collection'))
@router.message(F.text == '🗃 Моя коллекция')
async def collection_message(message: Message) -> None:
    await archive_collection(message, message.from_user.id)


@router.callback_query(F.data == 'v4:collection')
async def collection_callback(callback: CallbackQuery) -> None:
    await callback.answer()
    await archive_collection(callback.message, callback.from_user.id)


@router.message(Command('mission'))
@router.message(F.text == '🦋 Состояние Архива')
async def mission_message(message: Message) -> None:
    await mission_status(message, message.from_user.id)


@router.callback_query(F.data == 'v4:mission')
async def mission_callback(callback: CallbackQuery) -> None:
    await callback.answer()
    await mission_status(callback.message, callback.from_user.id)


async def operations_report(target: Message) -> None:
    lines = ['<b>Оперативная карта проекта</b>', '']
    for event_date in game.settings.event_dates:
        lines.append(f'<b>{format_event_date(event_date)}</b>')
        for team in TEAM_COLORS:
            users = await game.db.one(
                'SELECT COUNT(*) AS total FROM users WHERE event_date = ? AND team = ?',
                (event_date, team),
            )
            done_rows = await game.db.all(
                'SELECT location_key FROM team_route_unlocks WHERE event_date = ? AND team = ?',
                (event_date, team),
            )
            done = {str(row['location_key']) for row in done_rows}
            current = next(
                ((index, key) for index, key in enumerate(ROUTES[team]) if key not in done),
                None,
            )
            current_text = 'финал' if not current else f'{current[0] + 1}/5 {LOCATION_TITLES[current[1]]}'
            games = await game.db.one(
                '''SELECT COUNT(*) AS total FROM team_game_progress p
                   JOIN users u ON u.telegram_id = p.user_id
                   WHERE u.event_date = ? AND u.team = ? AND p.passed = 1''',
                (event_date, team),
            )
            lines.append(
                f'• <b>{team}</b>: {users["total"]} чел. · маршрут {len(done)}/5 · '
                f'игр {games["total"]} · сейчас {current_text}'
            )
        lines.append('')
    await target.answer(
        '\n'.join(lines),
        reply_markup=game.inline_buttons([
            ('🎛 Центр управления командами', 'ac:home'),
            ('🎨 Выдать команды', 'tq:admin:queue'),
            ('🔢 Коды локаций', 'tq:admin:codes'),
        ]),
    )


@router.message(Command('ops'))
async def ops_command(message: Message) -> None:
    if not await game.is_admin(message.from_user.id):
        return
    await operations_report(message)


@router.callback_query(F.data == 'v4:ops')
async def ops_callback(callback: CallbackQuery) -> None:
    if not await game.is_admin(callback.from_user.id):
        return
    await callback.answer()
    await operations_report(callback.message)


@router.message(Command('backup'))
async def backup_command(message: Message) -> None:
    if not game.is_superadmin(message.from_user.id):
        return
    path = Path(game.settings.database_path)
    if not path.exists():
        await message.answer('Файл базы пока не создан.')
        return
    payload = await asyncio.to_thread(path.read_bytes)
    stamp = datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')
    await message.answer_document(
        BufferedInputFile(payload, filename=f'last-keeper-{stamp}.db'),
        caption='Ручная резервная копия базы проекта.',
    )


def create_startup_backup(database_path: str, keep: int = 14) -> str | None:
    source = Path(database_path)
    if not source.exists():
        return None
    backup_dir = source.parent / 'backups'
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')
    destination = backup_dir / f'last-keeper-{stamp}.db'
    shutil.copy2(source, destination)
    backups = sorted(backup_dir.glob('last-keeper-*.db'), reverse=True)
    for old in backups[keep:]:
        old.unlink(missing_ok=True)
    return str(destination)

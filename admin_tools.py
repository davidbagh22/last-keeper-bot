from __future__ import annotations

from aiogram import F, Router
from aiogram.types import CallbackQuery

import app as game
from game_data import LOCATIONS, TEAM_COLORS, format_event_date

router = Router(name='last_keeper_admin_tools')
LOCATION_KEYS = tuple(LOCATIONS)


@router.callback_query(F.data == 'admin:teams')
async def team_overview(callback: CallbackQuery) -> None:
    if not await game.is_admin(callback.from_user.id):
        return
    await callback.answer()
    rows = await game.db.all(
        'SELECT DISTINCT event_date, team FROM users ORDER BY event_date, team'
    )
    if not rows:
        await callback.message.answer('Пока нет зарегистрированных команд.')
        return
    buttons = []
    for row in rows:
        try:
            date_index = game.settings.event_dates.index(row['event_date'])
            team_index = TEAM_COLORS.index(row['team'])
        except ValueError:
            continue
        buttons.append((
            f'{format_event_date(row["event_date"])} · {row["team"]}',
            f'ops:team:{date_index}:{team_index}',
        ))
    await callback.message.answer(
        '<b>Команды и коррекция маршрута</b>\n'
        'Выбери команду, чтобы увидеть решения и при необходимости открыть повторное прохождение.',
        reply_markup=game.inline_buttons(buttons),
    )


@router.callback_query(F.data.startswith('ops:team:'))
async def team_card(callback: CallbackQuery) -> None:
    if not await game.is_admin(callback.from_user.id):
        return
    await callback.answer()
    _, _, date_raw, team_raw = callback.data.split(':')
    date_index = int(date_raw)
    team_index = int(team_raw)
    if date_index >= len(game.settings.event_dates) or team_index >= len(TEAM_COLORS):
        return
    event_date = game.settings.event_dates[date_index]
    team = TEAM_COLORS[team_index]
    members = await game.db.one(
        'SELECT COUNT(*) AS total FROM users WHERE event_date = ? AND team = ?',
        (event_date, team),
    )
    captain = await game.db.one(
        "SELECT full_name, telegram_id FROM users WHERE event_date = ? AND team = ? AND role = 'captain'",
        (event_date, team),
    )
    choices = await game.team_choices(event_date, team)
    choice_map = {row['location_key']: row for row in choices}
    open_mark = await game.db.one(
        "SELECT 1 FROM route_marks WHERE event_date = ? AND team = ? AND route_key = 'open'",
        (event_date, team),
    )

    lines = [
        f'<b>{team} · {format_event_date(event_date)}</b>',
        f'Участников: {members["total"]}',
        'Капитан: ' + (
            f'{game.escape(captain["full_name"])} · <code>{captain["telegram_id"]}</code>'
            if captain else 'не назначен'
        ),
        '',
        '<b>Командные решения</b>',
    ]
    buttons = []
    for location_index, key in enumerate(LOCATION_KEYS):
        row = choice_map.get(key)
        if row:
            choice = next(
                (item for item in LOCATIONS[key]['choices'] if item.code == row['choice_code']),
                None,
            )
            label = choice.button if choice else row['choice_code']
            lines.append(f'✓ {LOCATIONS[key]["title"]}: {game.escape(label)}')
            buttons.append((
                f'Сбросить: {LOCATIONS[key]["title"]}',
                f'ops:reset:{date_index}:{team_index}:{location_index}',
            ))
        else:
            lines.append(f'○ {LOCATIONS[key]["title"]}: решения нет')
    lines.append(f'{"✓" if open_mark else "○"} Открытые пространства')
    if open_mark:
        buttons.append((
            'Сбросить отметку открытых пространств',
            f'ops:reset-open:{date_index}:{team_index}',
        ))
    buttons.append(('Назад к командам', 'admin:teams'))
    await callback.message.answer('\n'.join(lines), reply_markup=game.inline_buttons(buttons))


@router.callback_query(F.data.startswith('ops:reset:'))
async def reset_choice(callback: CallbackQuery) -> None:
    if not await game.is_admin(callback.from_user.id):
        return
    _, _, date_raw, team_raw, location_raw = callback.data.split(':')
    date_index = int(date_raw)
    team_index = int(team_raw)
    location_index = int(location_raw)
    if (
        date_index >= len(game.settings.event_dates)
        or team_index >= len(TEAM_COLORS)
        or location_index >= len(LOCATION_KEYS)
    ):
        return
    event_date = game.settings.event_dates[date_index]
    team = TEAM_COLORS[team_index]
    key = LOCATION_KEYS[location_index]
    await game.db.execute(
        'DELETE FROM team_choices WHERE event_date = ? AND team = ? AND location_key = ?',
        (event_date, team, key),
    )
    await game.db.execute(
        'DELETE FROM route_marks WHERE event_date = ? AND team = ? AND route_key = ?',
        (event_date, team, key),
    )
    await game.db.log(callback.from_user.id, 'reset_team_choice', {
        'event_date': event_date,
        'team': team,
        'location': key,
    })
    await callback.answer('Решение сброшено', show_alert=True)
    await callback.message.answer(
        f'Команда «{team}» снова может пройти локацию «{LOCATIONS[key]["title"]}» и зафиксировать новый выбор.'
    )


@router.callback_query(F.data.startswith('ops:reset-open:'))
async def reset_open_mark(callback: CallbackQuery) -> None:
    if not await game.is_admin(callback.from_user.id):
        return
    _, _, date_raw, team_raw = callback.data.split(':')
    date_index = int(date_raw)
    team_index = int(team_raw)
    if date_index >= len(game.settings.event_dates) or team_index >= len(TEAM_COLORS):
        return
    event_date = game.settings.event_dates[date_index]
    team = TEAM_COLORS[team_index]
    await game.db.execute(
        "DELETE FROM route_marks WHERE event_date = ? AND team = ? AND route_key = 'open'",
        (event_date, team),
    )
    await game.db.log(callback.from_user.id, 'reset_open_spaces', {
        'event_date': event_date,
        'team': team,
    })
    await callback.answer('Отметка сброшена', show_alert=True)

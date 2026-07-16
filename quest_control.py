from __future__ import annotations

import aiosqlite
from aiogram import Bot, F, Router
from aiogram.types import CallbackQuery, Message

import app as game
from game_data import TEAM_COLORS, format_event_date
from quest_common import (
    LOCATION_PLACES,
    LOCATION_TITLES,
    completed_locations,
    current_stage,
    is_assigned,
    main_menu,
    passed_games,
    progress_bar,
)
from route_config import ROUTES, TIME_SLOTS
from storage import utcnow
from team_games import GAMES_BY_TEAM_LOCATION

router = Router(name='last_keeper_admin_control_center')


def _team_index(team: str) -> int:
    return TEAM_COLORS.index(team)


def _date_index(event_date: str) -> int:
    return list(game.settings.event_dates).index(event_date)


async def _team_members(event_date: str, team: str):
    return await game.db.all(
        'SELECT telegram_id, full_name FROM users WHERE event_date = ? AND team = ? ORDER BY full_name',
        (event_date, team),
    )


async def _team_done(event_date: str, team: str) -> set[str]:
    rows = await game.db.all(
        'SELECT location_key FROM team_route_unlocks WHERE event_date = ? AND team = ?',
        (event_date, team),
    )
    return {str(row['location_key']) for row in rows}


def _current_for(event_date: str, team: str, done: set[str]):
    for index, key in enumerate(ROUTES[team]):
        if key not in done:
            return index, key
    return None


async def _notify_team(bot: Bot, event_date: str, team: str, text: str) -> tuple[int, int]:
    sent = 0
    failed = 0
    for row in await _team_members(event_date, team):
        try:
            await bot.send_message(int(row['telegram_id']), text, reply_markup=main_menu(await game.is_admin(int(row['telegram_id']))))
            sent += 1
        except Exception:
            failed += 1
    return sent, failed


@router.callback_query(F.data == 'ac:home')
async def control_home(callback: CallbackQuery) -> None:
    if not await game.is_admin(callback.from_user.id):
        return
    await callback.answer()
    await send_control_home(callback.message)


async def send_control_home(target: Message) -> None:
    lines = [
        '<b>Центр управления командами</b>',
        '',
        'Здесь Архивариус управляет прохождением без передачи кодов участникам:',
        '• видит текущую точку каждой команды;',
        '• одним нажатием завершает живой этап;',
        '• автоматически открывает следующую точку и вторую игру;',
        '• отправляет всей команде единое уведомление.',
        '',
        'Выбери день программы.',
    ]
    buttons = [
        (f'📅 {format_event_date(date)}', f'ac:day:{index}')
        for index, date in enumerate(game.settings.event_dates)
    ]
    await target.answer('\n'.join(lines), reply_markup=game.inline_buttons(buttons))


@router.callback_query(F.data.startswith('ac:day:'))
async def control_day(callback: CallbackQuery) -> None:
    if not await game.is_admin(callback.from_user.id):
        return
    parts = callback.data.split(':')
    if len(parts) != 3 or not parts[2].isdigit():
        return
    day_index = int(parts[2])
    if day_index >= len(game.settings.event_dates):
        return
    event_date = game.settings.event_dates[day_index]
    await callback.answer()
    lines = [f'<b>Команды · {format_event_date(event_date)}</b>', '']
    buttons = []
    for team in TEAM_COLORS:
        members = await _team_members(event_date, team)
        done = await _team_done(event_date, team)
        current = _current_for(event_date, team, done)
        current_text = 'финал' if not current else LOCATION_TITLES[current[1]]
        lines.append(f'• <b>{team}</b>: {len(members)} чел. · {len(done)}/5 · сейчас {current_text}')
        buttons.append((f'{team} · {len(done)}/5', f'ac:team:{day_index}:{_team_index(team)}'))
    await callback.message.answer('\n'.join(lines), reply_markup=game.inline_buttons(buttons))


@router.callback_query(F.data.startswith('ac:team:'))
async def control_team(callback: CallbackQuery) -> None:
    if not await game.is_admin(callback.from_user.id):
        return
    parts = callback.data.split(':')
    if len(parts) != 4 or not parts[2].isdigit() or not parts[3].isdigit():
        return
    day_index = int(parts[2])
    team_index = int(parts[3])
    if day_index >= len(game.settings.event_dates) or team_index >= len(TEAM_COLORS):
        return
    event_date = game.settings.event_dates[day_index]
    team = TEAM_COLORS[team_index]
    await callback.answer()
    await send_team_card(callback.message, event_date, team)


async def send_team_card(target: Message, event_date: str, team: str) -> None:
    members = await _team_members(event_date, team)
    done = await _team_done(event_date, team)
    current = _current_for(event_date, team, done)
    decisions = await game.db.one(
        'SELECT COUNT(*) AS total FROM team_choices WHERE event_date = ? AND team = ?',
        (event_date, team),
    )
    game_progress = await game.db.one(
        '''SELECT COUNT(*) AS total FROM team_game_progress p
           JOIN users u ON u.telegram_id = p.user_id
           WHERE u.event_date = ? AND u.team = ? AND p.passed = 1''',
        (event_date, team),
    )
    lines = [
        f'<b>Команда «{team}»</b>',
        f'День: {format_event_date(event_date)}',
        f'Участников: {len(members)}',
        f'Живой маршрут: {progress_bar(len(done), 5)}  {len(done)}/5',
        f'Пройдено цифровых игр участниками: {game_progress["total"]}',
        f'Командных решений: {decisions["total"]}/4',
        '',
    ]
    buttons: list[tuple[str, str]] = []
    day_index = _date_index(event_date)
    team_index = _team_index(team)
    if current:
        index, key = current
        pair = GAMES_BY_TEAM_LOCATION[(team, key)]
        lines.extend([
            f'<b>Сейчас</b>: этап {index + 1}/5 · {LOCATION_TITLES[key]}',
            f'Время: {TIME_SLOTS[index]}',
            f'Место: {LOCATION_PLACES[key]}',
            f'После подтверждения откроются: «{pair[1].title}» и следующий этап.',
        ])
        buttons.extend([
            ('✅ Завершить текущую локацию', f'ac:confirm:{day_index}:{team_index}'),
            ('📣 Напомнить команде маршрут', f'ac:remind:{day_index}:{team_index}'),
        ])
    else:
        lines.append('<b>Маршрут завершён.</b> Команда готова к общему финалу.')
        buttons.append(('📣 Сообщить о готовности к финалу', f'ac:remind:{day_index}:{team_index}'))
    buttons.extend([
        ('👥 Показать участников', f'ac:members:{day_index}:{team_index}'),
        ('⬅️ К списку команд', f'ac:day:{day_index}'),
    ])
    await target.answer('\n'.join(lines), reply_markup=game.inline_buttons(buttons))


@router.callback_query(F.data.startswith('ac:confirm:'))
async def confirm_stage_prompt(callback: CallbackQuery) -> None:
    if not await game.is_admin(callback.from_user.id):
        return
    parts = callback.data.split(':')
    if len(parts) != 4 or not parts[2].isdigit() or not parts[3].isdigit():
        return
    day_index = int(parts[2])
    team_index = int(parts[3])
    event_date = game.settings.event_dates[day_index]
    team = TEAM_COLORS[team_index]
    done = await _team_done(event_date, team)
    current = _current_for(event_date, team, done)
    if not current:
        await callback.answer('Маршрут уже завершён.', show_alert=True)
        return
    _, key = current
    await callback.answer()
    await callback.message.answer(
        f'<b>Подтвердить завершение?</b>\n\n'
        f'Команда: <b>{team}</b>\n'
        f'Локация: <b>{LOCATION_TITLES[key]}</b>\n\n'
        'После подтверждения действие увидит вся команда, откроется вторая игра этапа и следующая точка.',
        reply_markup=game.inline_buttons([
            ('✅ Да, этап пройден', f'ac:finish:{day_index}:{team_index}'),
            ('Отмена', f'ac:team:{day_index}:{team_index}'),
        ]),
    )


@router.callback_query(F.data.startswith('ac:finish:'))
async def finish_stage(callback: CallbackQuery, bot: Bot) -> None:
    if not await game.is_admin(callback.from_user.id):
        return
    parts = callback.data.split(':')
    if len(parts) != 4 or not parts[2].isdigit() or not parts[3].isdigit():
        return
    day_index = int(parts[2])
    team_index = int(parts[3])
    if day_index >= len(game.settings.event_dates) or team_index >= len(TEAM_COLORS):
        return
    event_date = game.settings.event_dates[day_index]
    team = TEAM_COLORS[team_index]
    done = await _team_done(event_date, team)
    current = _current_for(event_date, team, done)
    if not current:
        await callback.answer('Маршрут уже завершён.', show_alert=True)
        return
    index, key = current
    try:
        await game.db.execute(
            '''INSERT INTO team_route_unlocks(
                event_date, team, location_key, step_index, unlocked_by, unlocked_at
            ) VALUES(?, ?, ?, ?, ?, ?)''',
            (event_date, team, key, index, callback.from_user.id, utcnow()),
        )
    except aiosqlite.IntegrityError:
        await callback.answer('Этот этап уже завершён.', show_alert=True)
        return
    await game.db.log(callback.from_user.id, 'admin_finish_stage', {
        'event_date': event_date, 'team': team, 'location': key,
    })
    new_done = await _team_done(event_date, team)
    next_stage = _current_for(event_date, team, new_done)
    next_text = 'общий финал «Эффект бабочки»' if not next_stage else LOCATION_TITLES[next_stage[1]]
    pair = GAMES_BY_TEAM_LOCATION[(team, key)]
    text = (
        f'<b>✓ Архивариус подтвердил прохождение.</b>\n\n'
        f'Команда «{team}» завершила «{LOCATION_TITLES[key]}».\n'
        f'Открыта новая игра: <b>{game.escape(pair[1].title)}</b>.\n'
        f'Следующая точка: <b>{next_text}</b>.\n\n'
        'Открой «🎮 10 игр команды» и «📍 Текущая точка».'
    )
    sent, failed = await _notify_team(bot, event_date, team, text)
    await callback.answer('Этап открыт для всей команды', show_alert=True)
    await callback.message.answer(
        f'<b>Готово.</b> Уведомления: {sent} доставлено, {failed} не доставлено.'
    )
    await send_team_card(callback.message, event_date, team)


@router.callback_query(F.data.startswith('ac:remind:'))
async def remind_team(callback: CallbackQuery, bot: Bot) -> None:
    if not await game.is_admin(callback.from_user.id):
        return
    parts = callback.data.split(':')
    if len(parts) != 4 or not parts[2].isdigit() or not parts[3].isdigit():
        return
    day_index = int(parts[2])
    team_index = int(parts[3])
    event_date = game.settings.event_dates[day_index]
    team = TEAM_COLORS[team_index]
    done = await _team_done(event_date, team)
    current = _current_for(event_date, team, done)
    if current:
        index, key = current
        text = (
            f'<b>Маршрут команды «{team}»</b>\n\n'
            f'Сейчас: <b>{LOCATION_TITLES[key]}</b>\n'
            f'Время: {TIME_SLOTS[index]}\n'
            f'Место: {LOCATION_PLACES[key]}\n\n'
            'После живого задания переход подтвердит Архивариус. Ничего вводить вручную не нужно.'
        )
    else:
        text = f'<b>Команда «{team}» завершила все пять этапов.</b>\nОжидайте общий финал «Эффект бабочки».'
    sent, failed = await _notify_team(bot, event_date, team, text)
    await callback.answer(f'Доставлено: {sent}; ошибок: {failed}', show_alert=True)


@router.callback_query(F.data.startswith('ac:members:'))
async def show_members(callback: CallbackQuery) -> None:
    if not await game.is_admin(callback.from_user.id):
        return
    parts = callback.data.split(':')
    if len(parts) != 4 or not parts[2].isdigit() or not parts[3].isdigit():
        return
    event_date = game.settings.event_dates[int(parts[2])]
    team = TEAM_COLORS[int(parts[3])]
    members = await _team_members(event_date, team)
    await callback.answer()
    lines = [f'<b>Команда «{team}» · {format_event_date(event_date)}</b>']
    if not members:
        lines.append('Участников пока нет.')
    else:
        for index, row in enumerate(members, start=1):
            lines.append(f'{index}. {game.escape(row["full_name"])} · <code>{row["telegram_id"]}</code>')
    await callback.message.answer('\n'.join(lines))


@router.message(F.text.in_({'📍 Текущая точка', '📍 Куда идти', 'Следующая точка'}))
async def participant_current_point(message: Message) -> None:
    user = await game.get_user(message.from_user.id)
    if not is_assigned(user):
        await message.answer('Текущая точка появится после назначения команды Архивариусом.')
        return
    current = await current_stage(user)
    if not current:
        passed = len(await passed_games(message.from_user.id))
        await message.answer(
            '<b>Все пять живых точек пройдены.</b>\n\n'
            f'Личные игры: {passed}/10. До финала можно завершить оставшиеся миссии.',
            reply_markup=game.inline_buttons([
                ('🎮 Игры команды', 'tq:games'),
                ('🦋 Командный контур', 'progress:final'),
            ]),
        )
        return
    index, key = current
    pair = GAMES_BY_TEAM_LOCATION[(user['team'], key)]
    await message.answer(
        f'<b>Этап {index + 1} из 5 · {LOCATION_TITLES[key]}</b>\n\n'
        f'🕒 <b>{TIME_SLOTS[index]}</b>\n'
        f'📍 {LOCATION_PLACES[key]}\n\n'
        '<b>Что делать</b>\n'
        '1. Пройдите живое задание всей командой.\n'
        f'2. Можно пройти цифровую разминку «{game.escape(pair[0].title)}».\n'
        '3. Сообщите ведущему, что команда готова.\n'
        '4. Архивариус подтвердит этап одной кнопкой — следующая точка откроется всем автоматически.\n\n'
        '<i>Участникам больше не нужно вводить коды.</i>',
        reply_markup=game.inline_buttons([
            ('🎮 Разминка этапа', f'tq:game:{pair[0].game_id}'),
            ('🗺 Показать маршрут', 'tq:route'),
        ]),
    )


@router.callback_query(F.data == 'tq:current')
async def participant_current_callback(callback: CallbackQuery) -> None:
    await callback.answer()
    await participant_current_point(callback.message)

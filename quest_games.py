from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message

import app as game
from legend_engine import value_choice_count
from quest_common import *
from team_games import GAMES_BY_ID, presented_correct_index, presented_options

router = Router(name='last_keeper_team_games')


@router.callback_query(F.data == 'tq:games')
async def games_callback(callback: CallbackQuery) -> None:
    await callback.answer()
    await send_games(callback.message, callback.from_user.id)


@router.message(F.text.in_({'🎮 10 игр команды', '🧩 Испытания', 'Игровой Архив'}))
@router.message(Command('games'))
async def games_message(message: Message) -> None:
    await send_games(message, message.from_user.id)


async def send_games(target: Message, user_id: int) -> None:
    user = await game.get_user(user_id)
    if not is_assigned(user):
        await target.answer('Десять игр откроются после назначения команды.')
        return
    passed = await passed_games(user_id)
    value_rows = await game.db.all(
        'SELECT game_id FROM personal_value_choices WHERE user_id = ?',
        (user_id,),
    )
    value_done = {str(row['game_id']) for row in value_rows}
    games = ordered_games(user['team'])
    lines = [
        '╭────────────────╮',
        f'   <b>АРХИВ КОМАНДЫ «{game.escape(user["team"].upper())}»</b>',
        '╰────────────────╯',
        '',
        f'Знания: {progress_bar(len(passed), 10)}  {len(passed)}/10',
        f'Личные выборы: {progress_bar(len(value_done), 10)}  {len(value_done)}/10',
        '',
        'Каждая миссия состоит из двух слоёв:',
        '🔎 восстановить культурный или исторический фрагмент;',
        '🧭 принять личное решение, где нет правильного ответа.',
        '',
    ]
    buttons: list[tuple[str, str]] = []
    for number, item in enumerate(games, start=1):
        unlocked = await game_is_unlocked(user, item)
        if item.game_id in passed and item.game_id in value_done:
            marker, state = '✓', 'знание и выбор сохранены'
        elif item.game_id in passed:
            marker, state = '🧭', 'остался личный выбор'
            buttons.append((f'🧭 {number}. Сделать выбор', f'legend:start:{item.game_id}'))
        elif unlocked:
            marker, state = '▶', 'доступна'
            buttons.append((f'▶ {number}. {item.title}', f'tq:game:{item.game_id}'))
        else:
            marker, state = '🔒', 'откроется по маршруту'
        lines.append(f'{marker} <b>{number}. {game.escape(item.title)}</b> · {state}')
    await target.answer(
        '\n'.join(lines),
        reply_markup=game.inline_buttons(buttons) if buttons else None,
    )


@router.callback_query(F.data.startswith('tq:game:'))
async def open_game(callback: CallbackQuery) -> None:
    game_id = callback.data.split(':', 2)[2]
    item = GAMES_BY_ID.get(game_id)
    user = await game.get_user(callback.from_user.id)
    if not item or not is_assigned(user) or item.team != user['team']:
        await callback.answer('Эта игра не принадлежит вашей команде.', show_alert=True)
        return
    if not await game_is_unlocked(user, item):
        await callback.answer('Игра закрыта кодом предыдущей живой точки.', show_alert=True)
        return
    existing = await game.db.one(
        'SELECT passed FROM team_game_progress WHERE user_id = ? AND game_id = ?',
        (callback.from_user.id, game_id),
    )
    if existing and existing['passed']:
        await callback.answer('Знание уже восстановлено. Теперь сохрани личный выбор.', show_alert=True)
        await callback.message.answer(
            '<b>Вторая часть миссии</b>\n\nЗдесь больше нет правильных и неправильных ответов.',
            reply_markup=game.inline_buttons([('🧭 Сделать выбор', f'legend:start:{game_id}')]),
        )
        return
    options = presented_options(item)
    await callback.answer()
    await callback.message.answer(
        '┏━━━━━━━━━━━━━━┓\n'
        '   <b>СЛОЙ ЗНАНИЯ</b>\n'
        '┗━━━━━━━━━━━━━━┛\n\n'
        f'<b>{game.escape(item.title)}</b>\n'
        f'<i>{game.escape(item.mechanic)} · {LOCATION_TITLES[item.location]}</i>\n\n'
        f'{game.escape(item.prompt)}\n\n'
        f'{option_text(options)}\n\n'
        '<i>Полные ответы — в сообщении. На кнопках только номера.</i>',
        reply_markup=option_keyboard(f'tq:answer:{item.game_id}', len(options)),
    )


@router.callback_query(F.data.startswith('tq:answer:'))
async def answer_game(callback: CallbackQuery) -> None:
    parts = callback.data.split(':')
    if len(parts) != 4 or not parts[3].isdigit():
        return
    game_id = parts[2]
    answer_index = int(parts[3])
    item = GAMES_BY_ID.get(game_id)
    user = await game.get_user(callback.from_user.id)
    if not item or not is_assigned(user) or item.team != user['team']:
        return
    if not await game_is_unlocked(user, item):
        await callback.answer('Эта миссия пока закрыта.', show_alert=True)
        return
    options = presented_options(item)
    if answer_index >= len(options):
        return
    existing = await game.db.one(
        'SELECT attempts, passed FROM team_game_progress WHERE user_id = ? AND game_id = ?',
        (callback.from_user.id, game_id),
    )
    attempts = int(existing['attempts']) + 1 if existing else 1
    correct = answer_index == presented_correct_index(item)
    await game.db.execute(
        '''INSERT INTO team_game_progress(user_id, game_id, attempts, passed, completed_at)
           VALUES(?, ?, ?, ?, ?)
           ON CONFLICT(user_id, game_id) DO UPDATE SET
               attempts = excluded.attempts,
               passed = MAX(team_game_progress.passed, excluded.passed),
               completed_at = CASE WHEN excluded.passed = 1 THEN excluded.completed_at ELSE team_game_progress.completed_at END''',
        (callback.from_user.id, game_id, attempts, 1 if correct else 0, utcnow() if correct else None),
    )
    await callback.answer()
    selected = game.escape(options[answer_index])
    if correct:
        passed = len(await passed_games(callback.from_user.id))
        choices = await value_choice_count(callback.from_user.id)
        await callback.message.edit_text(
            '┏━━━━━━━━━━━━━━┓\n'
            '   <b>ФРАГМЕНТ ВОССТАНОВЛЕН</b>\n'
            '┗━━━━━━━━━━━━━━┛\n\n'
            f'Твой ответ: <i>{selected}</i>\n\n'
            f'{game.escape(item.success)}\n\n'
            f'Знания: {progress_bar(passed, 10)}  {passed}/10\n'
            f'Личные выборы: {progress_bar(choices, 10)}  {choices}/10\n\n'
            '<b>Но знание — только первая половина.</b>\n'
            'Теперь Архив спросит, как именно ты поступил бы с этим наследием.',
            reply_markup=game.inline_buttons([
                ('🧭 Перейти к выбору', f'legend:start:{game_id}'),
                ('🎮 К списку', 'tq:games'),
            ]),
        )
    else:
        await callback.message.edit_text(
            '╭──────────────╮\n'
            '   <b>ФРАГМЕНТ НЕ СОШЁЛСЯ</b>\n'
            '╰──────────────╯\n\n'
            f'Твой ответ: <i>{selected}</i>\n\n'
            f'Подсказка: {game.escape(item.hint)}\n\n'
            f'Попытка {attempts}. Ошибка не отнимает прогресс — она помогает проверить источник.',
            reply_markup=game.inline_buttons([('↻ Собрать ещё раз', f'tq:game:{game_id}')]),
        )


@router.callback_query(F.data == 'tq:progress')
async def progress_callback(callback: CallbackQuery) -> None:
    await callback.answer()
    await send_progress(callback.message, callback.from_user.id)


@router.message(F.text.in_({'📜 Прогресс', '📜 Мой путь', 'Мой прогресс'}))
@router.message(Command('progress'))
async def progress_message(message: Message) -> None:
    await send_progress(message, message.from_user.id)


async def send_progress(target: Message, user_id: int) -> None:
    user = await game.get_user(user_id)
    if not is_assigned(user):
        await target.answer('Прогресс начнётся после назначения команды.')
        return
    route_done = await team_route_done_count(user)
    passed = len(await passed_games(user_id))
    personal_choices = await value_choice_count(user_id)
    decisions = await game.db.one(
        '''SELECT COUNT(*) AS total FROM team_choices WHERE event_date = ? AND team = ?''',
        (user['event_date'], user['team']),
    )
    current = await current_stage(user)
    next_text = 'ожидание общего финала' if not current else LOCATION_TITLES[current[1]]
    await target.answer(
        '╭────────────────╮\n'
        '   <b>ПУТЬ ХРАНИТЕЛЯ</b>\n'
        '╰────────────────╯\n\n'
        f'📍 Живые точки      {progress_bar(route_done, 5)}  {route_done}/5\n'
        f'🔎 Знания           {progress_bar(passed, 10)}  {passed}/10\n'
        f'🧭 Личные выборы    {progress_bar(personal_choices, 10)}  {personal_choices}/10\n'
        f'🤝 Решения команды  {progress_bar(int(decisions["total"]), 4)}  {decisions["total"]}/4\n\n'
        f'Команда: <b>{game.escape(user["team"])}</b>\n'
        f'Следом: <b>{next_text}</b>\n\n'
        '<i>Личные выборы формируют твою легенду. Командные решения создают общую версию Архива. '
        'До финала последствия скрыты.</i>',
        reply_markup=game.inline_buttons([
            ('📍 Сейчас', 'tq:current'),
            ('🎮 Игры', 'tq:games'),
            ('◻️ Легенда', 'legend:final'),
        ], columns=2),
    )

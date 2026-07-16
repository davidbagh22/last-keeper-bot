from __future__ import annotations

import json

import aiosqlite
from aiogram import Bot, F, Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

import app as game
from game_data import LOCATIONS, OPEN_SPACES, format_event_date
from quest_common import *
from route_config import ROUTES, TIME_SLOTS
from storage import utcnow
from team_games import GAMES_BY_TEAM_LOCATION

router = Router(name='last_keeper_route_gate')


@router.message(CommandStart())
async def start(message: Message, state: FSMContext) -> None:
    await state.clear()
    user = await game.get_user(message.from_user.id)
    if not user:
        await state.set_state(game.Registration.consent)
        await message.answer(
            '<b>«Последний хранитель»</b>\n'
            '<i>Иммерсивная игра о русской культуре, памяти и цене решений</i>\n\n'
            'В Доме Москвы команда проходит пять реальных точек. После каждой точки цифровой код '
            'открывает следующий участок маршрута. Параллельно каждому участнику доступны десять '
            'уникальных игр его команды.\n\n'
            '<b>Схема пути</b>\n'
            'живая локация → цифровой код → игры команды → следующая локация → общий финал.\n\n'
            'Команду участнику выдаёт только Архивариус - выбрать цвет самостоятельно нельзя.',
            reply_markup=game.inline_buttons([
                ('▶️ Зарегистрироваться', 'reg:yes'),
                ('🎬 Демо механики', 'demo:intro'),
                ('🗓 Программа', 'ux:program'),
            ]),
        )
        return

    if not is_assigned(user):
        await message.answer(
            '<b>Регистрация сохранена.</b>\n\n'
            f'Хранитель: <b>{game.escape(user["full_name"])}</b>\n'
            f'День: {format_event_date(user["event_date"])}\n'
            'Статус: <b>ожидает распределения</b>\n\n'
            'Архивариус вручную выдаст одну из пяти команд. Это защищает маршруты от перегрузки '
            'и позволяет точно соблюдать схему программы.',
            reply_markup=waiting_menu(await game.is_admin(message.from_user.id)),
        )
        return

    completed = await team_route_done_count(user)
    passed = len(await passed_games(message.from_user.id))
    current = await current_stage(user)
    current_title = 'финал «Эффект бабочки»' if not current else LOCATION_TITLES[current[1]]
    await message.answer(
        '<b>Архив узнал тебя</b>\n\n'
        f'Хранитель: <b>{game.escape(user["full_name"])}</b>\n'
        f'Команда: <b>{game.escape(user["team"])}</b>\n'
        f'День: {format_event_date(user["event_date"])}\n\n'
        f'Живой маршрут: {progress_bar(completed, 5)}  {completed}/5\n'
        f'Игры команды: {progress_bar(passed, 10)}  {passed}/10\n'
        f'Сейчас открыто: <b>{current_title}</b>\n\n'
        'Нажми «Текущая точка». Следующий этап не откроется, пока команда не введёт '
        'цифровой код, полученный на живой локации.',
        reply_markup=main_menu(await game.is_admin(message.from_user.id)),
    )


@router.callback_query(game.Registration.date, F.data.startswith('date:'))
async def registration_date(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    await callback.answer()
    event_date = callback.data.split(':', 1)[1]
    if event_date not in game.settings.event_dates:
        await state.clear()
        await callback.message.answer('Этот день больше недоступен. Отправь /start.')
        return
    data = await state.get_data()
    try:
        await game.db.execute(
            '''INSERT INTO users(
                telegram_id, username, full_name, age, organization, event_date,
                team, role, status, consent_at, created_at
            ) VALUES(?, ?, ?, ?, ?, ?, '', 'participant', 'waiting_team', ?, ?)''',
            (
                callback.from_user.id,
                callback.from_user.username or '',
                data['full_name'],
                data['age'],
                data.get('organization', ''),
                event_date,
                data.get('consent_at', utcnow()),
                utcnow(),
            ),
        )
    except aiosqlite.IntegrityError:
        pass
    await state.clear()
    await callback.message.edit_text(
        '<b>Регистрация сохранена.</b>\n\n'
        f'Хранитель: {game.escape(data["full_name"])}\n'
        f'День: {format_event_date(event_date)}\n'
        'Команда: <b>будет выдана Архивариусом</b>'
    )
    await callback.message.answer(
        'Как только Архивариус назначит цвет команды, здесь появятся персональный маршрут '
        'и десять уникальных игровых миссий.',
        reply_markup=waiting_menu(await game.is_admin(callback.from_user.id)),
    )
    notice = (
        '<b>Новый участник ожидает команду</b>\n'
        f'{game.escape(data["full_name"])} · {format_event_date(event_date)}\n'
        f'Telegram ID: <code>{callback.from_user.id}</code>'
    )
    for admin_id in await game.admin_recipients():
        try:
            await bot.send_message(admin_id, notice)
        except Exception:
            pass


@router.message(F.text.in_({'📍 Текущая точка', '📍 Куда идти', 'Следующая точка'}))
async def show_current_point(message: Message) -> None:
    await send_current_point(message, message.from_user.id)


async def send_current_point(target: Message, user_id: int) -> None:
    user = await game.get_user(user_id)
    if not user:
        await target.answer('Сначала открой Архив командой /start.')
        return
    if not is_assigned(user):
        await target.answer('Текущая точка появится после того, как Архивариус выдаст команду.')
        return
    current = await current_stage(user)
    if not current:
        passed = len(await passed_games(user_id))
        await target.answer(
            '<b>Все пять живых точек пройдены.</b>\n\n'
            f'Игры команды: {passed}/10. '
            'До общего финала можно завершить оставшиеся цифровые миссии и проверить командный контур.',
            reply_markup=game.inline_buttons([
                ('🎮 Игры команды', 'tq:games'),
                ('🦋 Командный контур', 'progress:final'),
            ]),
        )
        return

    index, key = current
    pair = GAMES_BY_TEAM_LOCATION[(user['team'], key)]
    description = OPEN_SPACES['story'] if key == 'open' else LOCATIONS[key]['offline_task']
    await target.answer(
        f'<b>Этап {index + 1} из 5 · {LOCATION_TITLES[key]}</b>\n\n'
        f'🕒 <b>{TIME_SLOTS[index]}</b>\n'
        f'📍 {LOCATION_PLACES[key]}\n\n'
        f'{description}\n\n'
        '<b>Что делать</b>\n'
        '1. Пройдите живое задание.\n'
        f'2. Пока команда работает, можно открыть разминку «{game.escape(pair[0].title)}».\n'
        '3. В конце получите четырёхзначный код.\n'
        '4. Введите код в боте - только после этого откроются следующая точка и вторая игра этапа.',
        reply_markup=game.inline_buttons([
            ('🎮 Разминка этапа', f'tq:game:{pair[0].game_id}'),
            ('🔢 Ввести код локации', f'tq:code:{key}'),
            ('🗺 Показать маршрут', 'tq:route'),
        ]),
    )


@router.callback_query(F.data == 'tq:route')
async def route_callback(callback: CallbackQuery) -> None:
    await callback.answer()
    await send_route(callback.message, callback.from_user.id)


@router.message(F.text.in_({'🗺 Маршрут', 'Мой маршрут'}))
@router.message(Command('route'))
async def route_message(message: Message) -> None:
    await send_route(message, message.from_user.id)


async def send_route(target: Message, user_id: int) -> None:
    user = await game.get_user(user_id)
    if not is_assigned(user):
        await target.answer('Маршрут появится после того, как Архивариус выдаст команду.')
        return
    completed = await completed_locations(user)
    current = await current_stage(user)
    lines = [
        f'<b>Маршрут команды «{game.escape(user["team"])}»</b>',
        'Порядок взят из утверждённой программы проекта.',
        '',
    ]
    for index, key in enumerate(ROUTES[user['team']]):
        if key in completed:
            marker, state_text = '✓', 'пройдено'
        elif current and index == current[0]:
            marker, state_text = '▶', 'открыто сейчас'
        else:
            marker, state_text = '🔒', 'закрыто предыдущим кодом'
        lines.append(
            f'{marker} <b>{index + 1}. {TIME_SLOTS[index]} · {LOCATION_TITLES[key]}</b>\n'
            f'   {LOCATION_PLACES[key]} · {state_text}'
        )
    lines.append('\nБудущую точку нельзя активировать вручную: её откроет только правильный код текущей локации.')
    await target.answer('\n'.join(lines))


@router.callback_query(F.data.startswith('tq:code:'))
async def request_code(callback: CallbackQuery, state: FSMContext) -> None:
    user = await game.get_user(callback.from_user.id)
    if not is_assigned(user):
        await callback.answer('Сначала дождись назначения команды.', show_alert=True)
        return
    key = callback.data.rsplit(':', 1)[1]
    current = await current_stage(user)
    if not current or current[1] != key:
        await callback.answer('Эта часть Архива сейчас закрыта для вашей команды.', show_alert=True)
        return
    await callback.answer()
    await state.update_data(gate_location=key)
    await state.set_state(GateFlow.code)
    await callback.message.answer(
        f'<b>Код локации «{LOCATION_TITLES[key]}»</b>\n\n'
        'Введи четыре цифры, которые команда получила после живого задания. '
        'Пробелы допустимы. /cancel - отмена.'
    )


@router.message(GateFlow.code)
async def accept_code(message: Message, state: FSMContext, bot: Bot) -> None:
    user = await game.get_user(message.from_user.id)
    data = await state.get_data()
    key = data.get('gate_location')
    if not is_assigned(user) or key not in LOCATION_TITLES:
        await state.clear()
        await message.answer('Сессия устарела. Открой «Текущую точку» ещё раз.')
        return
    current = await current_stage(user)
    if not current or current[1] != key:
        await state.clear()
        await message.answer('Этот этап уже закрыт или сейчас не является текущим.')
        return
    entered = ''.join(character for character in (message.text or '') if character.isdigit())
    expected = await route_code(key)
    if entered != expected:
        await message.answer(
            '<b>Архив не узнаёт этот код.</b>\n\n'
            'Следующая локация остаётся закрытой. Проверь четыре цифры у ведущего и попробуй ещё раз.'
        )
        return

    try:
        await game.db.execute(
            '''INSERT INTO team_route_unlocks(
                event_date, team, location_key, step_index, unlocked_by, unlocked_at
            ) VALUES(?, ?, ?, ?, ?, ?)''',
            (user['event_date'], user['team'], key, current[0], message.from_user.id, utcnow()),
        )
    except aiosqlite.IntegrityError:
        pass
    await state.clear()
    await game.db.log(message.from_user.id, 'unlock_live_location', {
        'event_date': user['event_date'], 'team': user['team'], 'location': key,
    })
    pair = GAMES_BY_TEAM_LOCATION[(user['team'], key)]
    next_stage = await current_stage(user)
    next_text = 'общий финал «Эффект бабочки»' if not next_stage else LOCATION_TITLES[next_stage[1]]
    buttons = [
        ('🎮 Открыть вторую игру', f'tq:game:{pair[1].game_id}'),
        ('📍 Показать следующую точку', 'tq:current'),
    ]
    if key != 'open':
        buttons.insert(0, ('⚖️ Зафиксировать выбор команды', f'tq:decision:{key}'))
    await message.answer(
        '<b>✓ Код принят. Переход открыт.</b>\n\n'
        f'Команда завершила «{LOCATION_TITLES[key]}».\n'
        f'Следующий этап: <b>{next_text}</b>.\n'
        f'Открыта вторая цифровая миссия: <b>{game.escape(pair[1].title)}</b>.\n\n'
        'Для четырёх основных локаций отдельно сохраните общий выбор команды: именно он изменит финал.',
        reply_markup=game.inline_buttons(buttons),
    )
    await game.notify_team(
        bot,
        user,
        f'<b>Команда «{game.escape(user["team"])}» открыла переход.</b>\n'
        f'Пройдено: {LOCATION_TITLES[key]}. Следом: {next_text}.\n'
        f'В разделе игр доступна новая миссия «{game.escape(pair[1].title)}».',
    )


@router.callback_query(F.data == 'tq:current')
async def current_callback(callback: CallbackQuery) -> None:
    await callback.answer()
    await send_current_point(callback.message, callback.from_user.id)


@router.callback_query(F.data.startswith('tq:decision:'))
async def decision_open(callback: CallbackQuery) -> None:
    user = await game.get_user(callback.from_user.id)
    key = callback.data.rsplit(':', 1)[1]
    if not is_assigned(user) or key not in LOCATIONS:
        return
    unlocked = await completed_locations(user)
    if key not in unlocked:
        await callback.answer('Сначала введите код живой локации.', show_alert=True)
        return
    existing = await game.db.one(
        '''SELECT 1 FROM team_choices WHERE event_date = ? AND team = ? AND location_key = ?''',
        (user['event_date'], user['team'], key),
    )
    if existing:
        await callback.answer('Выбор этой локации уже сохранён.', show_alert=True)
        return
    await callback.answer()
    location = LOCATIONS[key]
    await callback.message.answer(
        f'<b>Командный выбор · {location["title"]}</b>\n\n'
        f'{location["prelude"]}\n\n'
        f'<b>{location["question"]}</b>\n\n'
        'Обсудите два последствия. Первый подтверждённый вариант станет решением всей команды.',
        reply_markup=game.inline_buttons([
            (choice.button, f'tq:choose:{key}:{index}')
            for index, choice in enumerate(location['choices'])
        ]),
    )


@router.callback_query(F.data.startswith('tq:choose:'))
async def decision_choose(callback: CallbackQuery) -> None:
    parts = callback.data.split(':')
    if len(parts) != 4 or not parts[3].isdigit():
        return
    _, _, key, index_raw = parts
    if key not in LOCATIONS:
        return
    index = int(index_raw)
    choices = LOCATIONS[key]['choices']
    if index >= len(choices):
        return
    await callback.answer()
    choice = choices[index]
    await callback.message.edit_text(
        f'Команда выбирает: <b>{choice.button}</b>\n\n'
        'После подтверждения изменить решение сможет только Архивариус.',
        reply_markup=game.inline_buttons([
            ('Подтвердить решение', f'tq:confirm:{key}:{index}'),
            ('Вернуться', f'tq:decision:{key}'),
        ]),
    )


@router.callback_query(F.data.startswith('tq:confirm:'))
async def decision_confirm(callback: CallbackQuery, bot: Bot) -> None:
    parts = callback.data.split(':')
    if len(parts) != 4 or not parts[3].isdigit():
        return
    _, _, key, index_raw = parts
    user = await game.get_user(callback.from_user.id)
    if not is_assigned(user) or key not in LOCATIONS:
        return
    index = int(index_raw)
    choices = LOCATIONS[key]['choices']
    if index >= len(choices):
        return
    choice = choices[index]
    try:
        await game.db.execute(
            '''INSERT INTO team_choices(
                event_date, team, location_key, choice_code, selected_by, effects_json,
                immediate_text, hidden_text, video_symbol, narrator_hint, created_at
            ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
            (
                user['event_date'], user['team'], key, choice.code, callback.from_user.id,
                json.dumps(choice.effects, ensure_ascii=False), choice.immediate,
                choice.hidden, choice.symbol, choice.narrator_hint, utcnow(),
            ),
        )
    except aiosqlite.IntegrityError:
        await callback.answer('Решение уже сохранено другим участником.', show_alert=True)
        return
    await callback.answer()
    await game.db.log(callback.from_user.id, 'team_choice', {
        'event_date': user['event_date'], 'team': user['team'], 'location': key, 'choice': choice.code,
    })
    await callback.message.edit_text(
        '<b>✓ Решение команды сохранено.</b>\n\n'
        f'{choice.immediate}\n\n'
        'Последствие вошло в скрытый контур. Полная связь решений проявится только в финале.'
    )
    await game.notify_team(
        bot,
        user,
        f'<b>Выбор команды в локации «{LOCATIONS[key]["title"]}» сохранён.</b>\n\n{choice.immediate}',
    )


@router.message(F.text == '🗓 Программа')
@router.message(Command('program'))
async def program(message: Message) -> None:
    import expert_ux
    await expert_ux.send_program(message)


@router.message(F.text.in_({'❓ Архивариус', '❓ Помощь', 'Задать вопрос'}))
async def support(message: Message) -> None:
    await game.ask_question(message)


@router.message(F.text.in_({'ℹ️ Как играть', 'Как играть'}))
@router.message(Command('help'))
async def guide(message: Message) -> None:
    await message.answer(
        '<b>Как проходит игра</b>\n\n'
        '1️⃣ Архивариус вручную выдаёт тебе цвет команды.\n'
        '2️⃣ Цвет определяет один из пяти маршрутов утверждённой программы.\n'
        '3️⃣ На текущей живой локации команда выполняет реальное задание.\n'
        '4️⃣ Полученный четырёхзначный код открывает только следующий этап.\n'
        '5️⃣ На каждом этапе у твоей команды две цифровые игры - всего десять.\n'
        '6️⃣ После четырёх основных локаций команда фиксирует решения, которые меняют финал.\n\n'
        '<b>Важно:</b> угадать будущий код или открыть чужую точку нельзя. Бот сверяет цвет команды, '
        'порядок маршрута и уже пройденные этапы.'
    )

from __future__ import annotations

from typing import Any, Sequence

import aiosqlite
from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, KeyboardButton, Message, ReplyKeyboardMarkup

import app as game
from game_data import LOCATIONS, OPEN_SPACES, PARAMETER_LABELS, PROGRAM_DAY, WORKSHOPS, format_event_date
from storage import utcnow

router = Router(name='last_keeper_expert_ux')
NUMBER_MARKS = ('1️⃣', '2️⃣', '3️⃣', '4️⃣', '5️⃣')


def main_menu(admin: bool = False) -> ReplyKeyboardMarkup:
    """Короткое меню, в котором действие понятно без инструкции."""
    keyboard = [
        [KeyboardButton(text='📍 Куда идти'), KeyboardButton(text='🗓 Программа')],
        [KeyboardButton(text='🧩 Испытания'), KeyboardButton(text='📜 Мой путь')],
        [KeyboardButton(text='ℹ️ Как играть'), KeyboardButton(text='❓ Помощь')],
    ]
    if admin:
        keyboard.append([KeyboardButton(text='🛡 Панель Архивариуса')])
    return ReplyKeyboardMarkup(
        keyboard=keyboard,
        resize_keyboard=True,
        input_field_placeholder='Выбери действие в Архиве',
    )


# Все старые сценарии автоматически получают новое понятное меню.
game.main_menu = main_menu


def progress_bar(done: int, total: int) -> str:
    total = max(1, total)
    done = min(max(done, 0), total)
    return '■' * done + '□' * (total - done)


def numbered_options(options: Sequence[str]) -> str:
    return '\n\n'.join(
        f'<b>{NUMBER_MARKS[index]}</b> {game.escape(text)}'
        for index, text in enumerate(options)
    )


def answer_keyboard(prefix: str, count: int):
    return game.inline_buttons(
        [(NUMBER_MARKS[index], f'{prefix}:{index}') for index in range(count)],
        columns=count,
    )


def next_point_title(current: tuple[int, str] | None) -> str:
    if not current:
        return 'маршрут завершён'
    _, key = current
    return OPEN_SPACES['title'] if key == 'open' else LOCATIONS[key]['title']


async def send_guide(target: Message) -> None:
    await target.answer(
        '<b>Как работает «Последний хранитель»</b>\n\n'
        'Это единая игра в двух пространствах: задания проходят <b>в Доме Москвы</b>, '
        'а бот становится цифровым Архивариусом и связывает решения команды в один сюжет.\n\n'
        '<b>Путь команды</b>\n'
        '1️⃣ Придите в указанную локацию и выполните реальное задание.\n'
        '2️⃣ Каждый участник может пройти короткое личное испытание в боте.\n'
        '3️⃣ Архивариус локации передаст капитану код.\n'
        '4️⃣ Команда обсудит выбор, а капитан зафиксирует его в боте.\n'
        '5️⃣ Все решения проявятся в общем финале «Эффект бабочки».\n\n'
        '<b>Роли</b>\n'
        '• Хранитель проходит маршрут, собирает личные артефакты и участвует в обсуждении.\n'
        '• Капитан дополнительно вводит коды и подтверждает решение всей команды.\n'
        '• Архивариус помогает, отвечает на вопросы и управляет общим финалом.\n\n'
        '<i>Здесь нет штрафа за «неправильную» позицию. У каждого решения есть последствия.</i>',
        reply_markup=game.inline_buttons([
            ('🎬 Посмотреть демо', 'demo:intro'),
            ('🗓 Открыть программу', 'ux:program'),
        ]),
    )


async def send_program(target: Message) -> None:
    lines = [
        '<b>«Последний хранитель» · программа дня</b>',
        '📍 Дом Москвы в Ереване, ул. Аргишти, 7',
        '📅 16–17 ноября 2026 года',
        '',
        '<b>Вход в историю</b>',
    ]
    for time, activity, _ in PROGRAM_DAY[:3]:
        lines.append(f'<b>{time}</b> · {activity}')
    lines.extend(['', '<b>Основной маршрут</b>'])
    for time, activity, _ in PROGRAM_DAY[3:4]:
        lines.append(f'<b>{time}</b> · {activity}')
    lines.extend(['', '<b>Сбор последствий</b>'])
    for time, activity, _ in PROGRAM_DAY[4:7]:
        lines.append(f'<b>{time}</b> · {activity}')
    lines.extend(['', '<b>Продолжение</b>'])
    for time, activity, _ in PROGRAM_DAY[7:]:
        lines.append(f'<b>{time}</b> · {activity}')
    lines.append('\nТочный порядок локаций зависит от цвета команды.')
    await target.answer(
        '\n'.join(lines),
        reply_markup=game.inline_buttons([
            ('📍 Маршрут команды', 'program:route'),
            ('🛠 Мастерские', 'program:workshops'),
            ('🪐 Открытые пространства', 'program:spaces'),
        ]),
    )


async def send_archive(target: Message, user_id: int) -> None:
    user = await game.get_user(user_id)
    if not user:
        await target.answer('Сначала войди в Архив через /start.')
        return
    rows = await game.db.all(
        'SELECT location_key, passed, artifact FROM personal_progress WHERE user_id = ?',
        (user_id,),
    )
    passed = {row['location_key'] for row in rows if row['passed']}
    lines = [
        '<b>Личные испытания</b>',
        f'{progress_bar(len(passed), 4)}  {len(passed)} из 4',
        '',
        'Это твой личный слой игры. Он не заменяет офлайн-задание и не принимает решение за команду.',
        '',
    ]
    buttons: list[tuple[str, str]] = []
    for index, (key, location) in enumerate(LOCATIONS.items(), start=1):
        status = '✓' if key in passed else '○'
        lines.append(f'{status} <b>{index}. {location["title"]}</b> — {location["artifact"]}')
        buttons.append((f'{status} {index}. {location["title"]}', f'puzzle:{key}'))
    lines.append('\nВыбери сектор. Полные варианты ответов появятся в тексте, а на кнопках останутся короткие номера.')
    await target.answer('\n'.join(lines), reply_markup=game.inline_buttons(buttons))


async def send_progress(target: Message, user_id: int) -> None:
    user = await game.get_user(user_id)
    if not user:
        await target.answer('Сначала войди в Архив через /start.')
        return
    personal_rows = await game.db.all(
        'SELECT location_key, passed, artifact FROM personal_progress WHERE user_id = ?',
        (user_id,),
    )
    personal = {row['location_key']: row for row in personal_rows}
    personal_done = sum(1 for row in personal_rows if row['passed'])
    choices = await game.team_choices(user['event_date'], user['team'])
    marks = await game.db.all(
        'SELECT route_key FROM route_marks WHERE event_date = ? AND team = ?',
        (user['event_date'], user['team']),
    )
    completed_route = {row['route_key'] for row in marks} | {row['location_key'] for row in choices}
    current = await game.current_route_key(user)
    values = await game.team_parameters(user['event_date'], user['team'])

    artifacts = []
    for key, location in LOCATIONS.items():
        row = personal.get(key)
        artifacts.append(f'{"✓" if row and row["passed"] else "○"} {location["artifact"]}')

    positive = [(key, value) for key, value in values.items() if value > 0]
    positive.sort(key=lambda item: item[1], reverse=True)
    contour = ', '.join(PARAMETER_LABELS[key] for key, _ in positive[:2]) or 'ещё не сформирован'

    role_note = (
        'Ты капитан: после офлайн-задания введи код через кнопку «Куда идти».'
        if user['role'] == 'captain'
        else 'После офлайн-задания обсуди выбор с командой; код вводит капитан.'
    )
    await target.answer(
        '<b>Твой путь в Архиве</b>\n\n'
        f'<b>Личный слой</b>  {progress_bar(personal_done, 4)}  {personal_done}/4\n'
        + '\n'.join(artifacts)
        + '\n\n'
        f'<b>Команда «{game.escape(user["team"])}»</b>  '
        f'{progress_bar(len(completed_route), 5)}  {len(completed_route)}/5\n'
        f'Командных решений: {len(choices)}/4\n'
        f'Следующая точка: <b>{next_point_title(current)}</b>\n'
        f'Проявившийся контур: {contour}\n\n'
        f'<b>Что делать сейчас</b>\n{role_note}',
        reply_markup=game.inline_buttons([
            ('🧩 Открыть испытания', 'ux:archive'),
            ('🦋 Проверить финальный контур', 'progress:final'),
        ]),
    )


@router.message(CommandStart())
async def clear_start(message: Message, state: FSMContext) -> None:
    await state.clear()
    user = await game.get_user(message.from_user.id)
    if not user:
        await state.set_state(game.Registration.consent)
        await message.answer(
            '<b>«Последний хранитель»</b>\n'
            '<i>Иммерсивная игра о памяти, культуре и решениях</i>\n\n'
            'Дом Москвы превращается в повреждённый Архив памяти России. '
            'Команды восстанавливают русский культурный код, научные открытия, исторические источники '
            'и человеческие голоса.\n\n'
            '<b>Главная механика</b>\n'
            'Реальное задание → личное испытание → командный выбор → последствие в финале.\n\n'
            'Можно сразу начать регистрацию или за минуту посмотреть механику глазами эксперта.',
            reply_markup=game.inline_buttons([
                ('▶️ Начать путь', 'reg:yes'),
                ('🎬 Демо за 60 секунд', 'demo:intro'),
                ('🗓 Посмотреть программу', 'ux:program'),
            ]),
        )
        return

    personal = await game.db.one(
        'SELECT COUNT(*) AS total FROM personal_progress WHERE user_id = ? AND passed = 1',
        (message.from_user.id,),
    )
    choices = await game.team_choices(user['event_date'], user['team'])
    marks = await game.db.all(
        'SELECT route_key FROM route_marks WHERE event_date = ? AND team = ?',
        (user['event_date'], user['team']),
    )
    completed = {row['route_key'] for row in marks} | {row['location_key'] for row in choices}
    current = await game.current_route_key(user)
    role = 'Капитан команды' if user['role'] == 'captain' else 'Хранитель'
    await message.answer(
        '<b>Архив узнал тебя</b>\n\n'
        f'{role}: <b>{game.escape(user["full_name"])}</b>\n'
        f'Команда: <b>{game.escape(user["team"])}</b>\n'
        f'День: {format_event_date(user["event_date"])}\n\n'
        f'Личные испытания: {progress_bar(int(personal["total"]), 4)}  {personal["total"]}/4\n'
        f'Маршрут команды: {progress_bar(len(completed), 5)}  {len(completed)}/5\n'
        f'Сейчас: <b>{next_point_title(current)}</b>\n\n'
        'Нижнее меню ведёт по игре слева направо: куда идти, что сделать, что уже изменилось.',
        reply_markup=main_menu(await game.is_admin(message.from_user.id)),
    )


@router.message(Command('guide'))
@router.message(Command('help'))
@router.message(F.text.in_({'ℹ️ Как играть', 'Как играть'}))
async def guide(message: Message) -> None:
    await send_guide(message)


@router.message(Command('program'))
@router.message(F.text == '🗓 Программа')
async def program(message: Message) -> None:
    await send_program(message)


@router.message(Command('progress'))
@router.message(F.text == '📜 Мой путь')
async def progress(message: Message) -> None:
    await send_progress(message, message.from_user.id)


@router.message(F.text == '🧩 Испытания')
async def archive(message: Message) -> None:
    await send_archive(message, message.from_user.id)


@router.message(F.text == '📍 Куда идти')
async def next_point(message: Message) -> None:
    await game.next_point(message)


@router.message(F.text == '❓ Помощь')
async def support(message: Message) -> None:
    await game.ask_question(message)


@router.message(F.text == '🛡 Панель Архивариуса')
async def admin_panel(message: Message) -> None:
    await game.admin_panel(message)


@router.callback_query(F.data == 'ux:guide')
async def guide_callback(callback: CallbackQuery) -> None:
    await callback.answer()
    await send_guide(callback.message)


@router.callback_query(F.data == 'ux:program')
async def program_callback(callback: CallbackQuery) -> None:
    await callback.answer()
    await send_program(callback.message)


@router.callback_query(F.data == 'ux:archive')
async def archive_callback(callback: CallbackQuery) -> None:
    await callback.answer()
    await send_archive(callback.message, callback.from_user.id)


@router.callback_query(F.data == 'ux:progress')
async def progress_callback(callback: CallbackQuery) -> None:
    await callback.answer()
    await send_progress(callback.message, callback.from_user.id)


@router.message(Command('demo'))
async def demo_command(message: Message) -> None:
    await message.answer(
        '<b>Экспертный деморежим</b>\nЗа четыре экрана покажу, как соединены реальная игра, Telegram и финальный «эффект бабочки».',
        reply_markup=game.inline_buttons([('Начать демо', 'demo:intro')]),
    )


@router.callback_query(F.data == 'demo:intro')
async def demo_intro(callback: CallbackQuery) -> None:
    await callback.answer()
    await callback.message.edit_text(
        '<b>Демо 1/4 · Не экскурсия и не викторина</b>\n\n'
        'Участник не листает справку о России. Он входит в реальную локацию, работает с текстами, '
        'образами, открытиями и свидетельствами, а затем принимает решение, которое меняет общий сюжет.\n\n'
        '<b>Бот нужен для трёх вещей:</b>\n'
        '• вести команду по своему маршруту;\n'
        '• дать каждому личное испытание;\n'
        '• собрать решения в финальную версию Архива.',
        reply_markup=game.inline_buttons([('Дальше · реальная локация', 'demo:offline')]),
    )


@router.callback_query(F.data == 'demo:offline')
async def demo_offline(callback: CallbackQuery) -> None:
    await callback.answer()
    await callback.message.edit_text(
        '<b>Демо 2/4 · Локация «Цена открытия»</b>\n\n'
        'В пространстве команда сопоставляет российские научные идеи, испытания и последствия ошибки. '
        'После обсуждения Архивариус выдаёт код капитану.\n\n'
        '<b>Важно:</b> бот не подменяет живую работу. Он открывает следующий смысловой слой.',
        reply_markup=game.inline_buttons([('Открыть личное испытание', 'demo:puzzle')]),
    )


@router.callback_query(F.data == 'demo:puzzle')
async def demo_puzzle(callback: CallbackQuery) -> None:
    await callback.answer()
    options = LOCATIONS['science']['puzzle_options']
    await callback.message.edit_text(
        '<b>Демо 3/4 · Личное испытание</b>\n\n'
        f'<b>{LOCATIONS["science"]["puzzle_question"]}</b>\n\n'
        f'{numbered_options(options)}\n\n'
        '<i>Полный ответ находится в сообщении. На кнопках — только номера, поэтому текст больше не обрезается.</i>',
        reply_markup=answer_keyboard('demo-answer', len(options)),
    )


@router.callback_query(F.data.startswith('demo-answer:'))
async def demo_answer(callback: CallbackQuery) -> None:
    await callback.answer()
    index_raw = callback.data.rsplit(':', 1)[1]
    if not index_raw.isdigit():
        return
    index = int(index_raw)
    correct = index == int(LOCATIONS['science']['puzzle_correct'])
    if not correct:
        await callback.message.edit_text(
            '<b>Архив не принимает славу без метода.</b>\n\n'
            'В этой игре ошибка не закрывает путь: она даёт подсказку и возвращает к смыслу вопроса.',
            reply_markup=game.inline_buttons([('Попробовать ещё раз', 'demo:puzzle')]),
        )
        return
    await callback.message.edit_text(
        '<b>Верно: идея становится знанием через проверяемый результат.</b>\n\n'
        'Участник получает личный артефакт — «Печать ответственного открытия». '
        'Но позицию всей команды это не определяет: после офлайн-задания капитан отдельно фиксирует общий выбор.',
        reply_markup=game.inline_buttons([('Дальше · эффект бабочки', 'demo:final')]),
    )


@router.callback_query(F.data == 'demo:final')
async def demo_final(callback: CallbackQuery) -> None:
    await callback.answer()
    await callback.message.edit_text(
        '<b>Демо 4/4 · Один выбор — два будущих</b>\n\n'
        '<b>Открыть технологию сейчас</b>\n'
        'Прогресс ускоряется, но растёт цена непроверенных последствий.\n\n'
        '<b>Остановиться и проверить</b>\n'
        'Ответственность усиливается, но команда принимает цену задержки.\n\n'
        'Четыре таких решения формируют уникальный архетип команды и сценарий финальной визуализации. '
        'Участники видят не баллы, а мир, который получился из их выбора.',
        reply_markup=game.inline_buttons([
            ('▶️ Войти в Архив', 'demo:finish'),
            ('ℹ️ Полная инструкция', 'ux:guide'),
        ]),
    )


@router.callback_query(F.data == 'demo:finish')
async def demo_finish(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    user = await game.get_user(callback.from_user.id)
    if user:
        await callback.message.answer(
            'Демо завершено. Твой реальный путь уже открыт в нижнем меню.',
            reply_markup=main_menu(await game.is_admin(callback.from_user.id)),
        )
        return
    await state.update_data(consent_at=utcnow())
    await state.set_state(game.Registration.name)
    await callback.message.edit_text(
        '<b>Книга Хранителей открыта.</b>\nКак записать тебя? Укажи имя и фамилию.'
    )


@router.callback_query(F.data.startswith('puzzle:'))
async def puzzle_start(callback: CallbackQuery) -> None:
    await callback.answer()
    user = await game.get_user(callback.from_user.id)
    if not user:
        await callback.message.answer('Сначала войди в Архив через /start.')
        return
    key = callback.data.split(':', 1)[1]
    if key not in LOCATIONS:
        return
    location = LOCATIONS[key]
    row = await game.db.one(
        'SELECT passed, artifact FROM personal_progress WHERE user_id = ? AND location_key = ?',
        (callback.from_user.id, key),
    )
    if row and row['passed']:
        await callback.message.answer(
            f'<b>✓ {location["title"]}</b>\n\n'
            f'Этот сектор уже восстановлен. Твой артефакт: <b>{game.escape(row["artifact"])}</b>',
            reply_markup=game.inline_buttons([('Вернуться к испытаниям', 'ux:archive')]),
        )
        return
    options = location['puzzle_options']
    await callback.message.answer(
        f'<b>{location["title"]}</b>\n'
        f'<i>{location["artifact"]}</i>\n\n'
        f'{location["prelude"]}\n\n'
        f'<b>Вопрос</b>\n{location["puzzle_question"]}\n\n'
        f'{numbered_options(options)}\n\n'
        '<i>Нажми номер выбранного ответа.</i>',
        reply_markup=answer_keyboard(f'puzzle-answer:{key}', len(options)),
    )


@router.callback_query(F.data.startswith('puzzle-answer:'))
async def puzzle_answer(callback: CallbackQuery) -> None:
    await callback.answer()
    parts = callback.data.split(':')
    if len(parts) != 3 or not parts[2].isdigit():
        return
    _, key, index_raw = parts
    if key not in LOCATIONS:
        return
    location = LOCATIONS[key]
    index = int(index_raw)
    options = location['puzzle_options']
    if index < 0 or index >= len(options):
        return
    existing = await game.db.one(
        'SELECT attempts, passed FROM personal_progress WHERE user_id = ? AND location_key = ?',
        (callback.from_user.id, key),
    )
    attempts = int(existing['attempts']) + 1 if existing else 1
    correct = index == int(location['puzzle_correct'])
    try:
        await game.db.execute(
            '''INSERT INTO personal_progress(user_id, location_key, attempts, passed, artifact, completed_at)
               VALUES(?, ?, ?, ?, ?, ?)
               ON CONFLICT(user_id, location_key) DO UPDATE SET
                   attempts = excluded.attempts,
                   passed = MAX(personal_progress.passed, excluded.passed),
                   artifact = CASE WHEN excluded.passed = 1 THEN excluded.artifact ELSE personal_progress.artifact END,
                   completed_at = CASE WHEN excluded.passed = 1 THEN excluded.completed_at ELSE personal_progress.completed_at END''',
            (
                callback.from_user.id,
                key,
                attempts,
                1 if correct else 0,
                location['artifact'] if correct else '',
                utcnow() if correct else None,
            ),
        )
    except aiosqlite.Error:
        await callback.message.answer('Архив не смог сохранить ответ. Повтори попытку через несколько секунд.')
        return

    selected = game.escape(options[index])
    if correct:
        await callback.message.edit_text(
            '<b>✓ Фрагмент восстановлен</b>\n\n'
            f'Твой ответ: <i>{selected}</i>\n\n'
            f'{location["puzzle_success"]}\n\n'
            f'Получен артефакт: <b>{location["artifact"]}</b>',
            reply_markup=game.inline_buttons([
                ('🧩 Следующее испытание', 'ux:archive'),
                ('📜 Посмотреть путь', 'ux:progress'),
            ]),
        )
    else:
        await callback.message.edit_text(
            '<b>Фрагмент пока не открылся</b>\n\n'
            f'Твой ответ: <i>{selected}</i>\n\n'
            f'{location["puzzle_retry"]}\n\n'
            f'Попытка: {attempts}. Ошибка не отнимает прогресс.',
            reply_markup=game.inline_buttons([('↻ Вернуться к вопросу', f'puzzle:{key}')]),
        )

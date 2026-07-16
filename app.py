from __future__ import annotations

import csv
import html
import io
import json
import logging
from collections import defaultdict
from typing import Any

import aiosqlite
from aiogram import Bot, F, Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    BufferedInputFile,
    CallbackQuery,
    KeyboardButton,
    Message,
    ReplyKeyboardMarkup,
)
from aiogram.utils.keyboard import InlineKeyboardBuilder

from config import load_settings
from game_data import (
    LOCATIONS,
    OPEN_SPACES,
    PARAMETER_LABELS,
    PROGRAM_DAY,
    ROUTES,
    TEAM_COLORS,
    TIME_SLOTS,
    WORKSHOPS,
    empty_parameters,
    final_archetype,
    format_event_date,
    route_lines,
)
from storage import Database, utcnow

settings = load_settings()
db = Database(settings.database_path)
router = Router(name='last_keeper')
log = logging.getLogger('last_keeper.bot')

CATEGORY_LABELS = {
    'route': 'Маршрут и локация',
    'code': 'Код не работает',
    'team': 'Команда или капитан',
    'health': 'Самочувствие и безопасность',
    'other': 'Другой вопрос',
}


class Registration(StatesGroup):
    consent = State()
    name = State()
    age = State()
    organization = State()
    date = State()


class LocationFlow(StatesGroup):
    code = State()
    choice = State()


class SupportFlow(StatesGroup):
    text = State()


class AdminFlow(StatesGroup):
    add_admin = State()
    broadcast = State()
    broadcast_confirm = State()
    answer_support = State()


async def init_application() -> None:
    await db.init()


async def database_admin_ids() -> set[int]:
    rows = await db.all('SELECT telegram_id FROM admin_users')
    return {int(row['telegram_id']) for row in rows}


async def is_admin(user_id: int) -> bool:
    if user_id in settings.superadmin_ids:
        return True
    row = await db.one('SELECT 1 FROM admin_users WHERE telegram_id = ?', (user_id,))
    return bool(row)


def is_superadmin(user_id: int) -> bool:
    return user_id in settings.superadmin_ids


async def get_user(user_id: int):
    return await db.one('SELECT * FROM users WHERE telegram_id = ?', (user_id,))


async def require_user(message: Message):
    user = await get_user(message.from_user.id)
    if not user:
        await message.answer('Архив пока не знает тебя. Отправь /start и пройди регистрацию.')
        return None
    return user


def main_menu(admin: bool = False) -> ReplyKeyboardMarkup:
    keyboard = [
        [KeyboardButton(text='Следующая точка'), KeyboardButton(text='Программа')],
        [KeyboardButton(text='Мой прогресс'), KeyboardButton(text='Игровой Архив')],
        [KeyboardButton(text='Задать вопрос')],
    ]
    if admin:
        keyboard.append([KeyboardButton(text='Панель Архивариуса')])
    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)


def inline_buttons(items: list[tuple[str, str]], columns: int = 1):
    builder = InlineKeyboardBuilder()
    for text, data in items:
        builder.button(text=text, callback_data=data)
    builder.adjust(columns)
    return builder.as_markup()


def escape(value: Any) -> str:
    return html.escape(str(value or ''))


async def team_choices(event_date: str, team: str):
    return await db.all(
        'SELECT * FROM team_choices WHERE event_date = ? AND team = ? ORDER BY id',
        (event_date, team),
    )


async def team_parameters(event_date: str, team: str) -> dict[str, int]:
    values = empty_parameters()
    for row in await team_choices(event_date, team):
        for key, amount in json.loads(row['effects_json']).items():
            if key in values:
                values[key] += int(amount)
    return values


async def assign_team(event_date: str) -> str:
    rows = await db.all(
        '''SELECT team, COUNT(*) AS amount
           FROM users WHERE event_date = ? GROUP BY team''',
        (event_date,),
    )
    counts = {team: 0 for team in TEAM_COLORS}
    for row in rows:
        if row['team'] in counts:
            counts[row['team']] = int(row['amount'])
    available = [team for team in TEAM_COLORS if counts[team] < settings.team_capacity]
    return min(available or TEAM_COLORS, key=lambda team: (counts[team], TEAM_COLORS.index(team)))


async def current_route_key(user) -> tuple[int, str] | None:
    completed_choices = {
        row['location_key'] for row in await team_choices(user['event_date'], user['team'])
    }
    marks = await db.all(
        'SELECT route_key FROM route_marks WHERE event_date = ? AND team = ?',
        (user['event_date'], user['team']),
    )
    completed = completed_choices | {row['route_key'] for row in marks}
    for index, key in enumerate(ROUTES[user['team']]):
        if key not in completed:
            return index, key
    return None


async def notify_team(bot: Bot, user, text: str) -> None:
    rows = await db.all(
        '''SELECT telegram_id FROM users
           WHERE event_date = ? AND team = ? AND telegram_id <> ?''',
        (user['event_date'], user['team'], user['telegram_id']),
    )
    for row in rows:
        try:
            await bot.send_message(row['telegram_id'], text)
        except Exception:
            log.warning('Could not notify user %s', row['telegram_id'], exc_info=True)


async def admin_recipients() -> set[int]:
    return settings.superadmin_ids | await database_admin_ids()


@router.message(CommandStart())
async def start(message: Message, state: FSMContext) -> None:
    await state.clear()
    user = await get_user(message.from_user.id)
    if user:
        role = 'капитан' if user['role'] == 'captain' else 'Хранитель'
        await message.answer(
            '<b>Архив узнал тебя.</b>\n\n'
            f'{role}: <b>{escape(user["full_name"])}</b>\n'
            f'Команда: <b>{escape(user["team"])}</b>\n'
            f'День: {format_event_date(user["event_date"])}\n\n'
            'Каждый восстановленный фрагмент меняет не маршрут, а то, каким станет финальный Архив.',
            reply_markup=main_menu(await is_admin(message.from_user.id)),
        )
        return

    await state.set_state(Registration.consent)
    await message.answer(
        '<b>Архив открылся. Но часть его страниц исчезла.</b>\n\n'
        'Слова, культурные символы, научные открытия и человеческие голоса ещё можно вернуть. '
        'Сегодня ты входишь не в викторину, а в историю, где решение оставляет след.\n\n'
        'Для маршрута Архиву потребуются имя, возраст и Telegram ID. Данные используются только для организации проекта.',
        reply_markup=inline_buttons([
            ('Войти в Архив', 'reg:yes'),
            ('Не сейчас', 'reg:no'),
        ]),
    )


@router.callback_query(Registration.consent, F.data.startswith('reg:'))
async def registration_consent(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    if callback.data == 'reg:no':
        await state.clear()
        await callback.message.edit_text('Архив закрыл запись. Вернуться можно командой /start.')
        return
    await state.update_data(consent_at=utcnow())
    await state.set_state(Registration.name)
    await callback.message.edit_text(
        '<b>Как записать тебя в Книгу Хранителей?</b>\nУкажи имя и фамилию.'
    )


@router.message(Registration.name)
async def registration_name(message: Message, state: FSMContext) -> None:
    value = ' '.join((message.text or '').split())
    if len(value.split()) < 2 or len(value) > 100:
        await message.answer('Нужно указать имя и фамилию. Например: Анна Петрова.')
        return
    await state.update_data(full_name=value)
    await state.set_state(Registration.age)
    await message.answer(
        '<b>Сколько тебе лет?</b>\nОсновной маршрут создан для участников от 16 до 26 лет.'
    )


@router.message(Registration.age)
async def registration_age(message: Message, state: FSMContext) -> None:
    value = (message.text or '').strip()
    if not value.isdigit() or not 10 <= int(value) <= 99:
        await message.answer('Введи возраст одним числом.')
        return
    age = int(value)
    await state.update_data(age=age, status='confirmed' if 16 <= age <= 26 else 'review')
    await state.set_state(Registration.organization)
    await message.answer(
        '<b>Откуда ты пришёл в Архив?</b>\n'
        'Укажи университет, организацию или молодёжное объединение. Можно написать «Пропустить».'
    )


@router.message(Registration.organization)
async def registration_organization(message: Message, state: FSMContext) -> None:
    value = ' '.join((message.text or '').split())
    await state.update_data(organization='' if value.casefold() == 'пропустить' else value[:150])
    await state.set_state(Registration.date)
    buttons = [(format_event_date(date), f'date:{date}') for date in settings.event_dates]
    await message.answer(
        '<b>Выбери день, когда начнётся твой путь.</b>\n'
        'Программа повторяется для разных потоков участников.',
        reply_markup=inline_buttons(buttons),
    )


@router.callback_query(Registration.date, F.data.startswith('date:'))
async def registration_date(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    event_date = callback.data.split(':', 1)[1]
    if event_date not in settings.event_dates:
        await state.clear()
        await callback.message.answer('Этот день больше недоступен. Отправь /start.')
        return
    data = await state.get_data()
    team = await assign_team(event_date)
    try:
        await db.execute(
            '''INSERT INTO users(
                telegram_id, username, full_name, age, organization, event_date,
                team, role, status, consent_at, created_at
            ) VALUES(?, ?, ?, ?, ?, ?, ?, 'participant', ?, ?, ?)''',
            (
                callback.from_user.id,
                callback.from_user.username or '',
                data['full_name'],
                data['age'],
                data.get('organization', ''),
                event_date,
                team,
                data.get('status', 'confirmed'),
                data.get('consent_at', utcnow()),
                utcnow(),
            ),
        )
    except aiosqlite.IntegrityError:
        pass
    await state.clear()
    review_note = (
        '\nВозраст будет подтверждён организатором вручную.'
        if data.get('status') == 'review' else ''
    )
    await callback.message.edit_text(
        '<b>Запись восстановлена.</b>\n\n'
        f'Хранитель: {escape(data["full_name"])}\n'
        f'День: {format_event_date(event_date)}\n'
        f'Команда: <b>{team}</b>{review_note}'
    )
    await callback.message.answer(
        'Архив определил твой контур. Цвет команды задаёт физический маршрут, '
        'а ваши решения — финальную версию памяти.',
        reply_markup=main_menu(await is_admin(callback.from_user.id)),
    )


@router.message(Command('program'))
@router.message(F.text == 'Программа')
async def program(message: Message) -> None:
    await show_program_message(message)


async def show_program_message(message: Message) -> None:
    lines = [
        '<b>Программа «Последнего хранителя»</b>',
        'Дом Москвы в Ереване, ул. Аргишти, 7',
        '16–17 ноября 2026 года',
        '',
    ]
    for time, activity, _ in PROGRAM_DAY:
        lines.append(f'<b>{time}</b> — {activity}')
    await message.answer(
        '\n'.join(lines),
        reply_markup=inline_buttons([
            ('Маршрут моей команды', 'program:route'),
            ('Мастерские', 'program:workshops'),
            ('Открытые пространства', 'program:spaces'),
        ]),
    )


@router.callback_query(F.data == 'program:route')
async def program_route(callback: CallbackQuery) -> None:
    await callback.answer()
    user = await get_user(callback.from_user.id)
    if not user:
        await callback.message.answer('Сначала зарегистрируйся через /start.')
        return
    await callback.message.answer(
        f'<b>Маршрут команды «{escape(user["team"])}»</b>\n\n' +
        '\n'.join(route_lines(user['team'])) +
        '\n\nФизический маршрут не меняется из-за решений: меняются сюжетные последствия.'
    )


@router.callback_query(F.data == 'program:workshops')
async def program_workshops(callback: CallbackQuery) -> None:
    await callback.answer()
    lines = ['<b>Мастерские Хранителей · 15:50–17:50</b>']
    lines.extend(f'• {title} — {place}' for title, place in WORKSHOPS)
    lines.append('\nТочное окно мастерской зависит от цвета команды и указано в маршрутном листе.')
    await callback.message.answer('\n'.join(lines))


@router.callback_query(F.data == 'program:spaces')
async def program_spaces(callback: CallbackQuery) -> None:
    await callback.answer()
    await callback.message.answer(
        '<b>Открытые пространства Архива</b>\n\n'
        '• «Пушкин. Код слова»\n'
        '• «Екатерина Великая. Кабинет эпохи»\n'
        '• «Культурный код России»\n'
        '• «Гагарин. Первый шаг»\n'
        '• «Лица памяти»\n'
        '• VR-зоны русской культуры и истории\n\n'
        'Выберите пространство, после которого у команды появился новый вопрос — не только удачная фотография.'
    )


@router.message(F.text == 'Следующая точка')
async def next_point(message: Message) -> None:
    user = await require_user(message)
    if not user:
        return
    current = await current_route_key(user)
    if not current:
        await message.answer(
            '<b>Маршрут собран.</b>\n\nВсе четыре решения зафиксированы, открытые пространства отмечены. '
            'Команда готова к общему финалу «Эффект бабочки».',
            reply_markup=inline_buttons([('Показать итоговый контур', 'progress:final')]),
        )
        return
    index, key = current
    if key == 'open':
        buttons = [('Мы посетили пространства', 'route:mark-open'), ('Весь маршрут', 'program:route')]
        await message.answer(
            '<b>Архив выводит команду за пределы одной комнаты.</b>\n\n'
            f'Время: <b>{TIME_SLOTS[index]}</b>\n'
            f'Точка: <b>{OPEN_SPACES["title"]}</b>\n'
            f'Место: {OPEN_SPACES["place"]}\n\n{OPEN_SPACES["story"]}',
            reply_markup=inline_buttons(buttons),
        )
        return
    location = LOCATIONS[key]
    buttons = [
        ('Личное испытание', f'puzzle:{key}'),
        ('Ввести код локации', f'location:open:{key}'),
        ('Весь маршрут', 'program:route'),
    ]
    await message.answer(
        '<b>Архив вызывает вашу команду.</b>\n\n'
        f'Время: <b>{TIME_SLOTS[index]}</b>\n'
        f'Локация: <b>{location["title"]}</b>\n'
        f'Место: {location["place"]}\n\n'
        f'{location["offline_task"]}',
        reply_markup=inline_buttons(buttons),
    )


@router.callback_query(F.data == 'route:mark-open')
async def mark_open_spaces(callback: CallbackQuery) -> None:
    user = await get_user(callback.from_user.id)
    if not user:
        await callback.answer('Сначала зарегистрируйся.', show_alert=True)
        return
    if user['role'] != 'captain' and not await is_admin(callback.from_user.id):
        await callback.answer('Отметку ставит капитан команды или Архивариус.', show_alert=True)
        return
    await callback.answer()
    await db.execute(
        '''INSERT OR IGNORE INTO route_marks(event_date, team, route_key, marked_by, marked_at)
           VALUES(?, ?, 'open', ?, ?)''',
        (user['event_date'], user['team'], callback.from_user.id, utcnow()),
    )
    await callback.message.edit_text(
        '<b>Открытые пространства отмечены.</b>\n'
        'Архив сохранил не посещение, а готовность команды замечать связи между разными эпохами и голосами.'
    )


@router.message(F.text == 'Игровой Архив')
async def game_archive(message: Message) -> None:
    user = await require_user(message)
    if not user:
        return
    rows = await db.all(
        'SELECT location_key, passed FROM personal_progress WHERE user_id = ?',
        (message.from_user.id,),
    )
    passed = {row['location_key'] for row in rows if row['passed']}
    buttons = []
    for key, location in LOCATIONS.items():
        prefix = '✓ ' if key in passed else ''
        buttons.append((prefix + location['title'], f'puzzle:{key}'))
    await message.answer(
        '<b>Личный контур Хранителя</b>\n\n'
        'Командные решения принимает капитан после офлайн-локации. Здесь каждый участник проходит короткие '
        'испытания и собирает собственные артефакты понимания.',
        reply_markup=inline_buttons(buttons, columns=1),
    )


@router.callback_query(F.data.startswith('puzzle:'))
async def puzzle_start(callback: CallbackQuery) -> None:
    await callback.answer()
    user = await get_user(callback.from_user.id)
    if not user:
        await callback.message.answer('Сначала зарегистрируйся через /start.')
        return
    key = callback.data.split(':', 1)[1]
    if key not in LOCATIONS:
        return
    location = LOCATIONS[key]
    row = await db.one(
        'SELECT passed, artifact FROM personal_progress WHERE user_id = ? AND location_key = ?',
        (callback.from_user.id, key),
    )
    if row and row['passed']:
        await callback.message.answer(
            f'<b>{location["title"]}</b> уже восстановлен в твоём личном контуре.\n'
            f'Артефакт: <b>{escape(row["artifact"])}</b>'
        )
        return
    options = [
        (text, f'puzzle-answer:{key}:{index}')
        for index, text in enumerate(location['puzzle_options'])
    ]
    await callback.message.answer(
        f'<b>{location["title"]}</b>\n\n{location["prelude"]}\n\n'
        f'<b>Испытание</b>\n{location["puzzle_question"]}',
        reply_markup=inline_buttons(options),
    )


@router.callback_query(F.data.startswith('puzzle-answer:'))
async def puzzle_answer(callback: CallbackQuery) -> None:
    await callback.answer()
    _, key, index_raw = callback.data.split(':', 2)
    if key not in LOCATIONS or not index_raw.isdigit():
        return
    location = LOCATIONS[key]
    index = int(index_raw)
    existing = await db.one(
        'SELECT attempts, passed FROM personal_progress WHERE user_id = ? AND location_key = ?',
        (callback.from_user.id, key),
    )
    attempts = int(existing['attempts']) + 1 if existing else 1
    correct = index == int(location['puzzle_correct'])
    await db.execute(
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
    if correct:
        await callback.message.edit_text(
            f'<b>Фрагмент восстановлен.</b>\n\n{location["puzzle_success"]}\n\n'
            f'Получен артефакт: <b>{location["artifact"]}</b>'
        )
    else:
        await callback.message.edit_text(
            f'{location["puzzle_retry"]}\n\nПопытка {attempts}.',
            reply_markup=inline_buttons([('Вернуться к испытанию', f'puzzle:{key}')]),
        )


@router.callback_query(F.data.startswith('location:open:'))
async def location_open(callback: CallbackQuery, state: FSMContext) -> None:
    user = await get_user(callback.from_user.id)
    if not user:
        await callback.answer('Сначала зарегистрируйся.', show_alert=True)
        return
    if user['role'] != 'captain' and not await is_admin(callback.from_user.id):
        await callback.answer('Код и решение фиксирует капитан команды.', show_alert=True)
        return
    key = callback.data.rsplit(':', 1)[1]
    if key not in LOCATIONS:
        return
    game_status = await db.setting('game_status', 'open')
    if game_status != 'open' and not await is_admin(callback.from_user.id):
        await callback.answer('Архив временно приостановлен организатором.', show_alert=True)
        return
    exists = await db.one(
        'SELECT 1 FROM team_choices WHERE event_date = ? AND team = ? AND location_key = ?',
        (user['event_date'], user['team'], key),
    )
    if exists:
        await callback.answer('Эта локация уже пройдена вашей командой.', show_alert=True)
        return
    await callback.answer()
    await state.update_data(location_key=key)
    await state.set_state(LocationFlow.code)
    await callback.message.answer(
        '<b>Архив услышал ваш шаг.</b>\n'
        'Введите знак, который передал Хранитель локации после офлайн-задания.'
    )


@router.message(LocationFlow.code)
async def location_code(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    key = data.get('location_key')
    user = await get_user(message.from_user.id)
    if not user or key not in LOCATIONS:
        await state.clear()
        await message.answer('Сессия устарела. Нажми «Следующая точка» ещё раз.')
        return
    entered = ''.join((message.text or '').split()).upper()
    expected = ''.join(settings.location_codes[key].split()).upper()
    if entered != expected:
        await message.answer(
            'Архив не узнаёт этот знак. Проверь код у Хранителя локации. '
            'Для отмены отправь /cancel.'
        )
        return
    await state.set_state(LocationFlow.choice)
    location = LOCATIONS[key]
    buttons = [(choice.button, f'choice:{key}:{choice.code}') for choice in location['choices']]
    await message.answer(
        '<b>Фрагмент найден.</b>\n\n'
        f'{location["prelude"]}\n\n'
        f'<b>{location["question"]}</b>\n'
        'Обсудите решение всей командой. После подтверждения изменить его сможет только Архивариус.',
        reply_markup=inline_buttons(buttons),
    )


@router.callback_query(LocationFlow.choice, F.data.startswith('choice:'))
async def choose_team_option(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    _, key, code = callback.data.split(':', 2)
    if key not in LOCATIONS:
        return
    choice = next((item for item in LOCATIONS[key]['choices'] if item.code == code), None)
    if not choice:
        return
    await state.update_data(location_key=key, choice_code=code)
    await callback.message.edit_text(
        f'Команда выбирает: <b>{choice.button}</b>\n\nПодтвердить решение?',
        reply_markup=inline_buttons([
            ('Подтвердить выбор', f'confirm:{key}:{code}'),
            ('Вернуться к вариантам', f'redo:{key}'),
        ]),
    )


@router.callback_query(LocationFlow.choice, F.data.startswith('redo:'))
async def redo_team_option(callback: CallbackQuery) -> None:
    await callback.answer()
    key = callback.data.split(':', 1)[1]
    if key not in LOCATIONS:
        return
    location = LOCATIONS[key]
    await callback.message.edit_text(
        f'<b>{location["question"]}</b>',
        reply_markup=inline_buttons([
            (choice.button, f'choice:{key}:{choice.code}') for choice in location['choices']
        ]),
    )


@router.callback_query(LocationFlow.choice, F.data.startswith('confirm:'))
async def confirm_team_option(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    await callback.answer()
    _, key, code = callback.data.split(':', 2)
    user = await get_user(callback.from_user.id)
    if not user or key not in LOCATIONS:
        await state.clear()
        return
    choice = next((item for item in LOCATIONS[key]['choices'] if item.code == code), None)
    if not choice:
        await state.clear()
        return
    try:
        await db.execute(
            '''INSERT INTO team_choices(
                event_date, team, location_key, choice_code, selected_by, effects_json,
                immediate_text, hidden_text, video_symbol, narrator_hint, created_at
            ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
            (
                user['event_date'], user['team'], key, code, callback.from_user.id,
                json.dumps(choice.effects, ensure_ascii=False), choice.immediate,
                choice.hidden, choice.symbol, choice.narrator_hint, utcnow(),
            ),
        )
        await db.execute(
            '''INSERT OR REPLACE INTO route_marks(event_date, team, route_key, marked_by, marked_at)
               VALUES(?, ?, ?, ?, ?)''',
            (user['event_date'], user['team'], key, callback.from_user.id, utcnow()),
        )
    except aiosqlite.IntegrityError:
        await state.clear()
        await callback.message.edit_text('Эта страница уже восстановлена вашей командой.')
        return
    await db.log(callback.from_user.id, 'team_choice', {
        'event_date': user['event_date'], 'team': user['team'], 'location': key, 'choice': code,
    })
    await state.clear()
    await callback.message.edit_text(
        '<b>Выбор зафиксирован.</b>\n\n'
        f'{choice.immediate}\n\n'
        'След уже вошёл в контур последствий. Полный смысл решения проявится только в финале.'
    )
    await notify_team(
        bot,
        user,
        f'<b>Команда приняла решение в локации «{LOCATIONS[key]["title"]}».</b>\n\n{choice.immediate}',
    )


@router.message(Command('progress'))
@router.message(F.text == 'Мой прогресс')
async def progress(message: Message) -> None:
    user = await require_user(message)
    if not user:
        return
    personal_rows = await db.all(
        'SELECT location_key, passed, artifact, attempts FROM personal_progress WHERE user_id = ?',
        (message.from_user.id,),
    )
    personal = {row['location_key']: row for row in personal_rows}
    choices = await team_choices(user['event_date'], user['team'])
    values = await team_parameters(user['event_date'], user['team'])
    current = await current_route_key(user)

    artifact_lines = []
    for key, location in LOCATIONS.items():
        row = personal.get(key)
        artifact_lines.append(
            f'{"✓" if row and row["passed"] else "○"} {location["artifact"]}'
        )
    strongest = sorted(values.items(), key=lambda item: item[1], reverse=True)[:2]
    weak = sorted(values.items(), key=lambda item: item[1])[:1]
    state_text = (
        f'Сильнее всего проявляются: {", ".join(PARAMETER_LABELS[k] for k, v in strongest if v > 0) or "контур ещё не сформирован"}. '
        f'Хрупкая линия: {PARAMETER_LABELS[weak[0][0]]}.' if choices else
        'Командный контур ещё не сформирован: первый выбор появится после локации.'
    )
    next_text = 'маршрут завершён' if not current else (
        OPEN_SPACES['title'] if current[1] == 'open' else LOCATIONS[current[1]]['title']
    )
    await message.answer(
        '<b>Личный контур</b>\n' + '\n'.join(artifact_lines) + '\n\n'
        f'<b>Команда «{escape(user["team"])}»</b>\n'
        f'Решений: {len(choices)} из 4\n'
        f'Следующая точка: {next_text}\n\n'
        f'{state_text}',
        reply_markup=inline_buttons([
            ('Маршрут команды', 'program:route'),
            ('Итоговый контур', 'progress:final'),
        ]),
    )


@router.callback_query(F.data == 'progress:final')
async def progress_final(callback: CallbackQuery) -> None:
    await callback.answer()
    user = await get_user(callback.from_user.id)
    if not user:
        return
    choices = await team_choices(user['event_date'], user['team'])
    if len(choices) < 4:
        await callback.message.answer(
            f'Архив восстановлен на {len(choices)} из 4 ключевых фрагментов. '
            'Финальный архетип пока скрыт: преждевременный ответ изменил бы обсуждение команды.'
        )
        return
    title, text, _ = final_archetype(await team_parameters(user['event_date'], user['team']))
    final_open = await db.setting('final_open', '0')
    if final_open != '1' and not await is_admin(callback.from_user.id):
        await callback.message.answer(
            'Контур собран, но Архивариусы ещё не открыли общий финал. '
            'Сохраните тишину перед последним последствием.'
        )
        return
    await callback.message.answer(
        f'<b>Версия Архива вашей команды: «{title}»</b>\n\n{text}'
    )


@router.message(F.text == 'Задать вопрос')
async def ask_question(message: Message) -> None:
    user = await require_user(message)
    if not user:
        return
    await message.answer(
        '<b>Позвать Архивариуса</b>\nВыбери тему. В экстренной ситуации сразу обратись к волонтёру рядом.',
        reply_markup=inline_buttons([
            (label, f'support:{key}') for key, label in CATEGORY_LABELS.items()
        ]),
    )


@router.callback_query(F.data.startswith('support:'))
async def support_category(callback: CallbackQuery, state: FSMContext) -> None:
    key = callback.data.split(':', 1)[1]
    if key not in CATEGORY_LABELS:
        return
    await callback.answer()
    await state.update_data(category=key)
    await state.set_state(SupportFlow.text)
    await callback.message.answer(
        f'<b>{CATEGORY_LABELS[key]}</b>\nКоротко опиши ситуацию. Сообщение увидят только Архивариусы.'
    )


@router.message(SupportFlow.text)
async def support_text(message: Message, state: FSMContext, bot: Bot) -> None:
    user = await get_user(message.from_user.id)
    if not user:
        await state.clear()
        return
    data = await state.get_data()
    body = ' '.join((message.text or '').split())[:1000]
    if not body:
        await message.answer('Опиши вопрос одним сообщением или отправь /cancel.')
        return
    request_id = await db.execute_returning_id(
        '''INSERT INTO support_requests(user_id, category, message, created_at)
           VALUES(?, ?, ?, ?)''',
        (message.from_user.id, data.get('category', 'other'), body, utcnow()),
    )
    await state.clear()
    admin_text = (
        f'<b>Обращение #{request_id}</b>\n'
        f'Хранитель: {escape(user["full_name"])}\n'
        f'Команда: {escape(user["team"])}\n'
        f'Тема: {CATEGORY_LABELS.get(data.get("category"), "Другой вопрос")}\n'
        f'Сообщение: {escape(body)}\n\n'
        f'Ответить: <code>/reply {request_id} текст ответа</code>'
    )
    for admin_id in await admin_recipients():
        try:
            await bot.send_message(admin_id, admin_text)
        except Exception:
            log.warning('Could not notify admin %s', admin_id, exc_info=True)
    await message.answer(
        f'Обращение #{request_id} передано Архивариусам. Ответ придёт сюда.',
        reply_markup=main_menu(await is_admin(message.from_user.id)),
    )


@router.message(Command('reply'))
async def reply_support_command(message: Message, bot: Bot) -> None:
    if not await is_admin(message.from_user.id):
        return
    parts = (message.text or '').split(maxsplit=2)
    if len(parts) < 3 or not parts[1].isdigit():
        await message.answer('Формат: <code>/reply НОМЕР текст ответа</code>')
        return
    request_id = int(parts[1])
    body = parts[2][:1000]
    request = await db.one('SELECT * FROM support_requests WHERE id = ?', (request_id,))
    if not request:
        await message.answer('Обращение не найдено.')
        return
    await db.execute(
        '''UPDATE support_requests SET status = 'answered', answer = ?, answered_by = ?, answered_at = ?
           WHERE id = ?''',
        (body, message.from_user.id, utcnow(), request_id),
    )
    await db.log(message.from_user.id, 'support_answer', {'request_id': request_id})
    try:
        await bot.send_message(
            request['user_id'],
            f'<b>Ответ Архивариуса на обращение #{request_id}</b>\n\n{escape(body)}',
        )
        await message.answer('Ответ отправлен участнику.')
    except Exception:
        await message.answer('Ответ сохранён, но Telegram не смог доставить сообщение.')


@router.message(Command('cancel'))
async def cancel(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer(
        'Действие отменено.',
        reply_markup=main_menu(await is_admin(message.from_user.id)),
    )


@router.message(Command('whoami'))
async def whoami(message: Message) -> None:
    user = await get_user(message.from_user.id)
    role = user['role'] if user else 'не зарегистрирован'
    access = 'суперадминистратор' if is_superadmin(message.from_user.id) else (
        'администратор' if await is_admin(message.from_user.id) else 'нет'
    )
    await message.answer(
        f'Telegram ID: <code>{message.from_user.id}</code>\n'
        f'Игровая роль: {escape(role)}\n'
        f'Админ-доступ: {access}'
    )


@router.message(F.text == 'Панель Архивариуса')
@router.message(Command('admin'))
async def admin_panel(message: Message) -> None:
    if not await is_admin(message.from_user.id):
        await message.answer('Эта часть Архива закрыта.')
        return
    await show_admin_panel(message)


async def show_admin_panel(message: Message) -> None:
    users = await db.one('SELECT COUNT(*) AS total FROM users')
    open_requests = await db.one("SELECT COUNT(*) AS total FROM support_requests WHERE status = 'open'")
    choices = await db.one('SELECT COUNT(*) AS total FROM team_choices')
    game_status = await db.setting('game_status', 'open')
    buttons = [
        ('Команды', 'admin:teams'),
        ('Участники', 'admin:users'),
        ('Обращения', 'admin:support'),
        ('Назначить капитана', 'admin:captains'),
        ('Рассылка', 'admin:broadcast'),
        ('Экспорт', 'admin:export'),
        ('Открыть финал', 'admin:final'),
        ('Пауза игры' if game_status == 'open' else 'Возобновить игру', 'admin:toggle-game'),
    ]
    if is_superadmin(message.from_user.id):
        buttons.append(('Администраторы', 'admin:admins'))
    await message.answer(
        '<b>Панель Архивариуса</b>\n\n'
        f'Участников: {users["total"]}\n'
        f'Командных решений: {choices["total"]} из 20 возможных на один поток\n'
        f'Открытых обращений: {open_requests["total"]}\n'
        f'Статус игры: {"открыта" if game_status == "open" else "пауза"}',
        reply_markup=inline_buttons(buttons, columns=2),
    )


@router.callback_query(F.data == 'admin:teams')
async def admin_teams(callback: CallbackQuery) -> None:
    if not await is_admin(callback.from_user.id):
        return
    await callback.answer()
    rows = await db.all(
        '''SELECT event_date, team, COUNT(*) AS users,
                  SUM(CASE WHEN role = 'captain' THEN 1 ELSE 0 END) AS captains
           FROM users GROUP BY event_date, team ORDER BY event_date, team'''
    )
    if not rows:
        await callback.message.answer('Пока нет зарегистрированных команд.')
        return
    lines = ['<b>Команды и готовность</b>']
    for row in rows:
        completed = await db.one(
            'SELECT COUNT(*) AS total FROM team_choices WHERE event_date = ? AND team = ?',
            (row['event_date'], row['team']),
        )
        lines.append(
            f'\n<b>{escape(row["team"])}</b> · {format_event_date(row["event_date"])}\n'
            f'Участников: {row["users"]} · капитанов: {row["captains"] or 0} · решений: {completed["total"]}/4'
        )
    await callback.message.answer('\n'.join(lines))


@router.callback_query(F.data == 'admin:users')
async def admin_users(callback: CallbackQuery) -> None:
    if not await is_admin(callback.from_user.id):
        return
    await callback.answer()
    rows = await db.all('SELECT * FROM users ORDER BY created_at DESC LIMIT 30')
    if not rows:
        await callback.message.answer('Участников пока нет.')
        return
    lines = ['<b>Последние регистрации</b>']
    for row in rows:
        marker = ' ★' if row['role'] == 'captain' else ''
        lines.append(
            f'{escape(row["full_name"])} — {escape(row["team"])}{marker} · '
            f'<code>{row["telegram_id"]}</code>'
        )
    lines.append('\n★ — капитан. Для полного списка используй экспорт.')
    await callback.message.answer('\n'.join(lines))


@router.callback_query(F.data == 'admin:captains')
async def admin_captains(callback: CallbackQuery) -> None:
    if not await is_admin(callback.from_user.id):
        return
    await callback.answer()
    buttons = [(team, f'admin:captain-team:{TEAM_COLORS.index(team)}') for team in TEAM_COLORS]
    await callback.message.answer('Выбери команду:', reply_markup=inline_buttons(buttons))


@router.callback_query(F.data.startswith('admin:captain-team:'))
async def admin_captain_team(callback: CallbackQuery) -> None:
    if not await is_admin(callback.from_user.id):
        return
    await callback.answer()
    index = int(callback.data.rsplit(':', 1)[1])
    team = TEAM_COLORS[index]
    rows = await db.all(
        'SELECT telegram_id, full_name, event_date, role FROM users WHERE team = ? ORDER BY event_date, full_name LIMIT 50',
        (team,),
    )
    if not rows:
        await callback.message.answer('В этой команде пока нет участников.')
        return
    buttons = [
        (f'{format_event_date(row["event_date"])} · {row["full_name"]}', f'admin:set-captain:{row["telegram_id"]}')
        for row in rows
    ]
    await callback.message.answer(
        f'<b>Капитан команды «{team}»</b>\nВыбери участника. Предыдущий капитан этого дня и команды будет снят.',
        reply_markup=inline_buttons(buttons),
    )


@router.callback_query(F.data.startswith('admin:set-captain:'))
async def admin_set_captain(callback: CallbackQuery, bot: Bot) -> None:
    if not await is_admin(callback.from_user.id):
        return
    target_id = int(callback.data.rsplit(':', 1)[1])
    target = await get_user(target_id)
    if not target:
        await callback.answer('Участник не найден.', show_alert=True)
        return
    await callback.answer()
    await db.execute(
        "UPDATE users SET role = 'participant' WHERE event_date = ? AND team = ? AND role = 'captain'",
        (target['event_date'], target['team']),
    )
    await db.execute("UPDATE users SET role = 'captain' WHERE telegram_id = ?", (target_id,))
    await db.log(callback.from_user.id, 'set_captain', {'target_id': target_id})
    try:
        await bot.send_message(
            target_id,
            '<b>Архив доверил тебе право последней записи.</b>\n'
            'Ты назначен капитаном команды. После каждой офлайн-локации именно ты вводишь код и подтверждаешь общее решение.'
        )
    except Exception:
        pass
    await callback.message.edit_text(
        f'Капитан назначен: <b>{escape(target["full_name"])}</b>, команда {escape(target["team"])}.'
    )


@router.callback_query(F.data == 'admin:support')
async def admin_support(callback: CallbackQuery) -> None:
    if not await is_admin(callback.from_user.id):
        return
    await callback.answer()
    rows = await db.all(
        "SELECT * FROM support_requests WHERE status = 'open' ORDER BY id LIMIT 20"
    )
    if not rows:
        await callback.message.answer('Открытых обращений нет.')
        return
    buttons = []
    for row in rows:
        user = await get_user(row['user_id'])
        name = user['full_name'] if user else str(row['user_id'])
        buttons.append((f'#{row["id"]} · {name}', f'admin:support-item:{row["id"]}'))
    await callback.message.answer('Открытые обращения:', reply_markup=inline_buttons(buttons))


@router.callback_query(F.data.startswith('admin:support-item:'))
async def admin_support_item(callback: CallbackQuery) -> None:
    if not await is_admin(callback.from_user.id):
        return
    await callback.answer()
    request_id = int(callback.data.rsplit(':', 1)[1])
    row = await db.one('SELECT * FROM support_requests WHERE id = ?', (request_id,))
    if not row:
        return
    user = await get_user(row['user_id'])
    await callback.message.answer(
        f'<b>Обращение #{request_id}</b>\n'
        f'Участник: {escape(user["full_name"] if user else row["user_id"])}\n'
        f'Тема: {CATEGORY_LABELS.get(row["category"], row["category"])}\n'
        f'Сообщение: {escape(row["message"])}\n\n'
        f'Ответ: <code>/reply {request_id} ваш текст</code>'
    )


@router.callback_query(F.data == 'admin:broadcast')
async def admin_broadcast(callback: CallbackQuery, state: FSMContext) -> None:
    if not await is_admin(callback.from_user.id):
        return
    await callback.answer()
    await state.set_state(AdminFlow.broadcast)
    await callback.message.answer(
        '<b>Рассылка всем зарегистрированным участникам</b>\n'
        'Отправь одно сообщение. Перед отправкой бот покажет подтверждение. /cancel — отмена.'
    )


@router.message(AdminFlow.broadcast)
async def admin_broadcast_text(message: Message, state: FSMContext) -> None:
    text = (message.text or '').strip()
    if not text or len(text) > 3500:
        await message.answer('Сообщение должно содержать от 1 до 3500 символов.')
        return
    await state.update_data(broadcast_text=text)
    await state.set_state(AdminFlow.broadcast_confirm)
    await message.answer(
        '<b>Предпросмотр рассылки</b>\n\n' + escape(text),
        reply_markup=inline_buttons([
            ('Отправить всем', 'admin:broadcast-confirm'),
            ('Отменить', 'admin:broadcast-cancel'),
        ]),
    )


@router.callback_query(AdminFlow.broadcast_confirm, F.data == 'admin:broadcast-cancel')
async def admin_broadcast_cancel(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    await state.clear()
    await callback.message.edit_text('Рассылка отменена.')


@router.callback_query(AdminFlow.broadcast_confirm, F.data == 'admin:broadcast-confirm')
async def admin_broadcast_confirm(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    if not await is_admin(callback.from_user.id):
        return
    await callback.answer()
    data = await state.get_data()
    text = data.get('broadcast_text', '')
    rows = await db.all('SELECT telegram_id FROM users')
    sent = 0
    for row in rows:
        try:
            await bot.send_message(row['telegram_id'], escape(text))
            sent += 1
        except Exception:
            pass
    await db.log(callback.from_user.id, 'broadcast', {'sent': sent, 'total': len(rows)})
    await state.clear()
    await callback.message.edit_text(f'Рассылка завершена: {sent} из {len(rows)} сообщений доставлены.')


@router.callback_query(F.data == 'admin:toggle-game')
async def admin_toggle_game(callback: CallbackQuery) -> None:
    if not await is_admin(callback.from_user.id):
        return
    await callback.answer()
    current = await db.setting('game_status', 'open')
    new_value = 'paused' if current == 'open' else 'open'
    await db.set_setting('game_status', new_value)
    await db.log(callback.from_user.id, 'toggle_game', {'status': new_value})
    await callback.message.answer(
        'Игра приостановлена: новые коды временно не принимаются.'
        if new_value == 'paused' else
        'Игра возобновлена: капитаны снова могут фиксировать решения.'
    )


@router.callback_query(F.data == 'admin:final')
async def admin_open_final(callback: CallbackQuery, bot: Bot) -> None:
    if not await is_admin(callback.from_user.id):
        return
    await callback.answer()
    await db.set_setting('final_open', '1')
    teams = await db.all('SELECT DISTINCT event_date, team FROM users')
    sent = 0
    for team_row in teams:
        choices = await team_choices(team_row['event_date'], team_row['team'])
        if len(choices) < 4:
            continue
        title, text, _ = final_archetype(
            await team_parameters(team_row['event_date'], team_row['team'])
        )
        members = await db.all(
            'SELECT telegram_id FROM users WHERE event_date = ? AND team = ?',
            (team_row['event_date'], team_row['team']),
        )
        for member in members:
            try:
                await bot.send_message(
                    member['telegram_id'],
                    f'<b>Архив собрал все решения вашей команды.</b>\n\n'
                    f'Итог: <b>{title}</b>\n{text}'
                )
                sent += 1
            except Exception:
                pass
    await db.log(callback.from_user.id, 'open_final', {'messages_sent': sent})
    await callback.message.answer(f'Финал открыт. Отправлено сообщений: {sent}.')


@router.callback_query(F.data == 'admin:export')
async def admin_export(callback: CallbackQuery) -> None:
    if not await is_admin(callback.from_user.id):
        return
    await callback.answer()
    users = await db.all('SELECT * FROM users ORDER BY event_date, team, full_name')
    choices = await db.all('SELECT * FROM team_choices ORDER BY event_date, team, id')
    supports = await db.all('SELECT * FROM support_requests ORDER BY id')

    user_stream = io.StringIO()
    writer = csv.writer(user_stream)
    user_fields = ['telegram_id', 'username', 'full_name', 'age', 'organization', 'event_date', 'team', 'role', 'status']
    writer.writerow(user_fields)
    for row in users:
        writer.writerow([row[field] for field in user_fields])

    summary: list[dict[str, Any]] = []
    grouped: dict[tuple[str, str], list[Any]] = defaultdict(list)
    for row in choices:
        grouped[(row['event_date'], row['team'])].append(row)
    for (event_date, team), rows in grouped.items():
        parameters = await team_parameters(event_date, team)
        title, final_text, archetype = final_archetype(parameters)
        summary.append({
            'event_date': event_date,
            'team': team,
            'archetype': archetype,
            'title': title,
            'final_text': final_text,
            'parameters': parameters,
            'choices': [
                {
                    'location': row['location_key'],
                    'choice': row['choice_code'],
                    'hidden_text': row['hidden_text'],
                    'video_symbol': row['video_symbol'],
                    'narrator_hint': row['narrator_hint'],
                }
                for row in rows
            ],
        })

    support_stream = io.StringIO()
    writer = csv.writer(support_stream)
    writer.writerow(['id', 'user_id', 'category', 'message', 'status', 'answer', 'created_at'])
    for row in supports:
        writer.writerow([row[field] for field in ['id', 'user_id', 'category', 'message', 'status', 'answer', 'created_at']])

    await callback.message.answer_document(
        BufferedInputFile(user_stream.getvalue().encode('utf-8-sig'), filename='participants.csv')
    )
    await callback.message.answer_document(
        BufferedInputFile(
            json.dumps(summary, ensure_ascii=False, indent=2).encode('utf-8'),
            filename='archive_video_summary.json',
        )
    )
    await callback.message.answer_document(
        BufferedInputFile(support_stream.getvalue().encode('utf-8-sig'), filename='support_requests.csv')
    )


@router.callback_query(F.data == 'admin:admins')
async def admin_admins(callback: CallbackQuery) -> None:
    if not is_superadmin(callback.from_user.id):
        await callback.answer('Только суперадминистратор управляет доступом.', show_alert=True)
        return
    await callback.answer()
    rows = await db.all('SELECT * FROM admin_users ORDER BY added_at')
    lines = ['<b>Администраторы</b>', 'Суперадминистраторы задаются только в Render.']
    for admin_id in sorted(settings.superadmin_ids):
        lines.append(f'• <code>{admin_id}</code> — суперадминистратор')
    for row in rows:
        lines.append(f'• <code>{row["telegram_id"]}</code> — добавлен из панели')
    buttons = [('Добавить администратора', 'admin:add-admin')]
    buttons.extend((f'Удалить {row["telegram_id"]}', f'admin:remove-admin:{row["telegram_id"]}') for row in rows)
    await callback.message.answer('\n'.join(lines), reply_markup=inline_buttons(buttons))


@router.callback_query(F.data == 'admin:add-admin')
async def admin_add_admin(callback: CallbackQuery, state: FSMContext) -> None:
    if not is_superadmin(callback.from_user.id):
        return
    await callback.answer()
    await state.set_state(AdminFlow.add_admin)
    await callback.message.answer(
        'Отправь Telegram ID нового администратора. Он может узнать его командой /whoami. /cancel — отмена.'
    )


@router.message(AdminFlow.add_admin)
async def admin_add_admin_id(message: Message, state: FSMContext, bot: Bot) -> None:
    if not is_superadmin(message.from_user.id):
        await state.clear()
        return
    value = (message.text or '').strip()
    if not value.isdigit():
        await message.answer('Нужен числовой Telegram ID.')
        return
    target_id = int(value)
    if target_id in settings.superadmin_ids:
        await message.answer('Этот ID уже является суперадминистратором.')
        return
    await db.execute(
        '''INSERT INTO admin_users(telegram_id, added_by, added_at) VALUES(?, ?, ?)
           ON CONFLICT(telegram_id) DO NOTHING''',
        (target_id, message.from_user.id, utcnow()),
    )
    await db.log(message.from_user.id, 'add_admin', {'target_id': target_id})
    await state.clear()
    try:
        await bot.send_message(
            target_id,
            '<b>Тебе открыт доступ Архивариуса.</b>\n'
            'Команда /admin открывает панель управления проектом «Последний хранитель». '
            'Доступ можно отозвать только суперадминистратором.'
        )
    except Exception:
        pass
    await message.answer(f'Администратор <code>{target_id}</code> добавлен.')


@router.callback_query(F.data.startswith('admin:remove-admin:'))
async def admin_remove_admin(callback: CallbackQuery) -> None:
    if not is_superadmin(callback.from_user.id):
        return
    target_id = int(callback.data.rsplit(':', 1)[1])
    await callback.answer()
    await db.execute('DELETE FROM admin_users WHERE telegram_id = ?', (target_id,))
    await db.log(callback.from_user.id, 'remove_admin', {'target_id': target_id})
    await callback.message.edit_text(f'Доступ администратора <code>{target_id}</code> отозван.')


@router.message(Command('resetme'))
async def reset_me(message: Message, state: FSMContext) -> None:
    if not await is_admin(message.from_user.id):
        return
    await db.execute('DELETE FROM personal_progress WHERE user_id = ?', (message.from_user.id,))
    await db.execute('DELETE FROM users WHERE telegram_id = ?', (message.from_user.id,))
    await state.clear()
    await message.answer('Тестовая регистрация удалена. Отправь /start.')


@router.message(Command('help'))
async def help_command(message: Message) -> None:
    await message.answer(
        '<b>Что делает цифровой Архивариус</b>\n\n'
        '• показывает программу и маршрут;\n'
        '• проводит личные игровые испытания;\n'
        '• принимает код и командное решение от капитана;\n'
        '• показывает прогресс без раскрытия скрытых параметров;\n'
        '• передаёт вопросы организаторам.\n\n'
        'Основная игра проходит в реальных пространствах Дома Москвы. Бот связывает её фрагменты в единый финал.'
    )

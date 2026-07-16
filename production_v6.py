from __future__ import annotations

from datetime import datetime, timezone

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, KeyboardButton, Message, ReplyKeyboardMarkup

import app as game
from game_data import final_archetype
from quest_common import (
    LOCATION_TITLES, completed_locations, game_is_unlocked, is_assigned,
    option_keyboard, option_text, progress_bar,
)
from team_games import GAMES_BY_ID, presented_options

router = Router(name='last_keeper_production_v6')

SPACES = (
    ('pushkin', 'Пушкин. Код слова'), ('catherine', 'Екатерина Великая. Кабинет эпохи'),
    ('culture', 'Культурный код России'), ('gagarin', 'Гагарин. Первый шаг'),
    ('memory', 'Лица памяти'), ('vr_izba', 'VR: Русская изба'),
    ('vr_history', 'VR: История России'),
)

HOST_SCRIPTS = {
    'culture': ('Добро пожаловать в сектор живого слова. Здесь важно понять, как передать наследие дальше без потери смысла.', 'Что важнее сохранить: точную форму или возможность быть понятым новым поколением?'),
    'science': ('Перед вами лаборатория ответственности. Любое открытие создаёт не только возможность, но и цену ошибки.', 'В какой момент общество получает право использовать открытие?'),
    'history': ('Прошлое говорит разными источниками. Задача — проверить, чему можно доверять.', 'Что делает исторический источник убедительным, а не просто эффектным?'),
    'memory': ('Здесь память имеет человеческий голос. За каждым свидетельством стоит прожитая история.', 'Можно ли сохранить общую память, не услышав личные истории?'),
    'open': ('Открытые пространства — не пауза для фотографии. Выберите точку, которая оставила вопрос.', 'Какой вопрос команда уносит дальше и почему он важен?'),
}

MECHANICS = (
    ('🧩 Реконструкция', 'Соберите наиболее точную версию фрагмента.'),
    ('🔎 Проверка источника', 'Определите вариант, которому можно доверять.'),
    ('🔗 Культурная связь', 'Найдите связь между образом, человеком и контекстом.'),
    ('⚖️ Последствие выбора', 'Выберите наиболее обоснованное последствие.'),
    ('🗝 Архивный шифр', 'Расшифруйте подсказку и восстановите смысл.'),
)

class SpaceFlow(StatesGroup):
    question = State()


def compact_menu(admin: bool = False, host: bool = False) -> ReplyKeyboardMarkup:
    keyboard = [
        [KeyboardButton(text='📍 Сейчас'), KeyboardButton(text='🎮 Играть')],
        [KeyboardButton(text='📜 Мой путь'), KeyboardButton(text='❓ Помощь')],
    ]
    if host:
        keyboard.append([KeyboardButton(text='🎭 Ведущий')])
    if admin:
        keyboard.append([KeyboardButton(text='🛡 Управление')])
    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True, input_field_placeholder='Выберите действие')


game.main_menu = compact_menu


def mechanic_for(game_id: str) -> tuple[str, str]:
    return MECHANICS[sum(ord(ch) for ch in game_id) % len(MECHANICS)]


async def init_v6() -> None:
    await game.db.execute('''CREATE TABLE IF NOT EXISTS open_space_reflections(
        event_date TEXT NOT NULL, team TEXT NOT NULL, space_key TEXT NOT NULL,
        question_text TEXT NOT NULL, submitted_by INTEGER NOT NULL, submitted_at TEXT NOT NULL,
        PRIMARY KEY(event_date, team))''')


@router.message(F.text == '📍 Сейчас')
async def compact_current(message: Message) -> None:
    await message.answer('Открываю текущую точку.', reply_markup=game.inline_buttons([('📍 Показать', 'tq:current')]))


@router.message(F.text == '🎮 Играть')
async def compact_games(message: Message) -> None:
    await message.answer('Открываю доступные миссии.', reply_markup=game.inline_buttons([('🎮 Миссии', 'tq:games')]))


@router.message(F.text == '📜 Мой путь')
async def compact_path(message: Message) -> None:
    await message.answer('Здесь собраны маршрут, прогресс и коллекция.', reply_markup=game.inline_buttons([
        ('🗺 Маршрут', 'tq:route'), ('📊 Прогресс', 'tq:progress'),
        ('🗃 Коллекция', 'v4:collection'), ('◻️ Финал', 'v6:final'),
        ('🗓 Программа', 'program:route'), ('🤝 Партнёры', 'partners:show'),
    ], columns=2))


@router.message(F.text == '❓ Помощь')
async def compact_help(message: Message) -> None:
    await message.answer('Что нужно?', reply_markup=game.inline_buttons([
        ('ℹ️ Как играть', 'demo:rules'), ('💬 Задать вопрос', 'support:start'),
        ('🪐 Пространства', 'program:spaces'),
    ]))


@router.message(F.text == '🛡 Управление')
async def compact_admin_alias(message: Message) -> None:
    await message.answer('Открываю панель.', reply_markup=game.inline_buttons([('🛡 Панель', 'v6:admin')]))


@router.message(F.text == '🎭 Ведущий')
async def compact_host_alias(message: Message) -> None:
    await message.answer('Открываю панель ведущего. Команда: /host')


@router.callback_query(F.data.startswith('tq:game:'))
async def varied_game(callback: CallbackQuery) -> None:
    game_id = callback.data.split(':', 2)[2]
    item = GAMES_BY_ID.get(game_id)
    user = await game.get_user(callback.from_user.id)
    if not item or not is_assigned(user) or item.team != user['team']:
        await callback.answer('Эта миссия не принадлежит вашей команде.', show_alert=True)
        return
    if not await game_is_unlocked(user, item):
        await callback.answer('Миссия пока закрыта живым маршрутом.', show_alert=True)
        return
    options = presented_options(item)
    label, instruction = mechanic_for(game_id)
    await callback.answer()
    await callback.message.answer(
        f'<b>{label} · {game.escape(item.title)}</b>\n'
        f'<i>{game.escape(instruction)}</i>\n\n{game.escape(item.prompt)}\n\n'
        f'{option_text(options)}\n\n<i>Ответы полностью показаны в сообщении; кнопки содержат только номера.</i>',
        reply_markup=option_keyboard(f'tq:answer:{item.game_id}', len(options)))


@router.callback_query(F.data == 'v6:spaces')
async def spaces_start(callback: CallbackQuery) -> None:
    await init_v6()
    user = await game.get_user(callback.from_user.id)
    if not is_assigned(user):
        await callback.answer('Сначала получите команду.', show_alert=True)
        return
    await callback.answer()
    await callback.message.answer('<b>Открытые пространства Архива</b>\n\nВыберите пространство, после которого у команды появился новый вопрос — не только удачная фотография.', reply_markup=game.inline_buttons([(title, f'v6:space:{key}') for key, title in SPACES]))


@router.callback_query(F.data.startswith('v6:space:'))
async def space_selected(callback: CallbackQuery, state: FSMContext) -> None:
    key = callback.data.rsplit(':', 1)[1]
    if key not in dict(SPACES):
        return
    await state.update_data(space_key=key)
    await state.set_state(SpaceFlow.question)
    await callback.answer()
    await callback.message.answer(f'<b>{game.escape(dict(SPACES)[key])}</b>\n\nНапишите вопрос, который команда уносит из этого пространства. Начните с мысли «мы задумались, почему…».')


@router.message(SpaceFlow.question)
async def save_reflection(message: Message, state: FSMContext) -> None:
    await init_v6()
    user = await game.get_user(message.from_user.id)
    text = (message.text or '').strip()
    if not is_assigned(user) or len(text) < 15:
        await message.answer('Сформулируйте вопрос подробнее — не менее 15 символов.')
        return
    data = await state.get_data()
    await game.db.execute('''INSERT INTO open_space_reflections(event_date, team, space_key, question_text, submitted_by, submitted_at)
        VALUES(?, ?, ?, ?, ?, ?) ON CONFLICT(event_date, team) DO UPDATE SET space_key=excluded.space_key,
        question_text=excluded.question_text, submitted_by=excluded.submitted_by, submitted_at=excluded.submitted_at''',
        (user['event_date'], user['team'], data['space_key'], text, message.from_user.id, datetime.now(timezone.utc).isoformat()))
    await state.clear()
    await message.answer(f'<b>Вопрос команды сохранён.</b>\n\n«{game.escape(text)}»\n\nОн войдёт в итоговый контур команды.')


@router.callback_query(F.data.startswith('v6:hostscript:'))
async def host_script(callback: CallbackQuery) -> None:
    key = callback.data.rsplit(':', 1)[1]
    script = HOST_SCRIPTS.get(key)
    if not script:
        return
    await callback.answer()
    await callback.message.answer(f'<b>Сценарий ведущего · {LOCATION_TITLES[key]}</b>\n\n<b>Вступление</b>\n{script[0]}\n\n<b>Ход</b>\n1. Объясните правила.\n2. Дайте выполнить действие.\n3. Попросите объяснить выбор.\n4. Зафиксируйте общий ответ.\n\n<b>Вопрос перед завершением</b>\n{script[1]}')


async def final_report(target: Message, user_id: int) -> None:
    await init_v6()
    user = await game.get_user(user_id)
    if not is_assigned(user):
        await target.answer('Финал откроется после назначения команды.')
        return
    final_open = await game.db.setting('final_open', '0')
    done = await completed_locations(user)
    choices = await game.team_choices(user['event_date'], user['team'])
    if final_open != '1' or len(done) < 5 or len(choices) < 4:
        await target.answer('<b>◻️ Эффект бабочки закрыт</b>\n\n' f'Маршрут: {progress_bar(len(done), 5)} {len(done)}/5\nРешения: {progress_bar(len(choices), 4)} {len(choices)}/4\n\nПоследствия не показываются до подтверждения главного Архивариуса.')
        return
    title, text, _ = final_archetype(await game.team_parameters(user['event_date'], user['team']))
    reflection = await game.db.one('SELECT question_text FROM open_space_reflections WHERE event_date=? AND team=?', (user['event_date'], user['team']))
    games = await game.db.all('''SELECT DISTINCT p.game_id FROM team_game_progress p JOIN users u ON u.telegram_id=p.user_id WHERE u.event_date=? AND u.team=? AND p.passed=1 LIMIT 5''', (user['event_date'], user['team']))
    themes = [GAMES_BY_ID[row['game_id']].title for row in games if row['game_id'] in GAMES_BY_ID][:3]
    lines = ['<b>🦋 ЭФФЕКТ БАБОЧКИ</b>', '', f'Версия Архива команды «{game.escape(user["team"])}»: <b>«{game.escape(title)}»</b>', '', game.escape(text)]
    if themes:
        lines += ['', '<b>Что команда помогла сохранить</b>', *(f'• {game.escape(item)}' for item in themes)]
    if reflection:
        lines += ['', '<b>Вопрос, который команда уносит дальше</b>', f'«{game.escape(reflection["question_text"])}»']
    lines += ['', '<i>Итог собран из живого маршрута, цифровых миссий, решений и вопроса открытых пространств.</i>']
    await target.answer('\n'.join(lines))


async def stats_text() -> str:
    await init_v6()
    total = await game.db.one('SELECT COUNT(*) AS total FROM users')
    games = await game.db.one('SELECT COUNT(*) AS total FROM team_game_progress WHERE passed=1')
    questions = await game.db.one('SELECT COUNT(*) AS total FROM open_space_reflections')
    support = await game.db.one('SELECT COUNT(*) AS total FROM support_requests')
    return f'<b>Статистика проекта</b>\n\nУчастников: <b>{total["total"]}</b>\nПройдено игр: <b>{games["total"]}</b>\nКомандных вопросов: <b>{questions["total"]}</b>\nОбращений: <b>{support["total"]}</b>'


@router.callback_query(F.data == 'v6:stats')
async def stats_callback(callback: CallbackQuery) -> None:
    if await game.is_admin(callback.from_user.id):
        await callback.answer(); await callback.message.answer(await stats_text())


@router.callback_query(F.data == 'v6:emergency')
async def emergency_callback(callback: CallbackQuery) -> None:
    if not await game.is_admin(callback.from_user.id):
        return
    await callback.answer()
    await callback.message.answer('<b>Аварийный режим</b>\n\nИспользуйте только при реальном сбое.', reply_markup=game.inline_buttons([
        ('⏸ Пауза', 'admin:pause'), ('▶️ Продолжить', 'admin:resume'),
        ('🎛 Команды', 'ac:home'), ('📣 Рассылка', 'admin:broadcast'),
        ('📊 Прогресс', 'tq:admin:teams'), ('💬 Вопросы', 'admin:support'),
    ], columns=2))


@router.callback_query(F.data == 'v6:final')
async def final_callback(callback: CallbackQuery) -> None:
    await callback.answer(); await final_report(callback.message, callback.from_user.id)

from __future__ import annotations

from datetime import datetime, timezone

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

import app as game
from game_data import final_archetype
from quest_common import LOCATION_TITLES, completed_locations, is_assigned, progress_bar
from team_games import GAMES_BY_ID

router = Router(name='last_keeper_production_v6')

SPACES = (
    ('pushkin', 'Пушкин. Код слова'),
    ('catherine', 'Екатерина Великая. Кабинет эпохи'),
    ('culture', 'Культурный код России'),
    ('gagarin', 'Гагарин. Первый шаг'),
    ('memory', 'Лица памяти'),
    ('vr_izba', 'VR: Русская изба'),
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


def mechanic_for(game_id: str) -> tuple[str, str]:
    return MECHANICS[sum(ord(ch) for ch in game_id) % len(MECHANICS)]


async def init_v6() -> None:
    await game.db.execute('''CREATE TABLE IF NOT EXISTS open_space_reflections(
        event_date TEXT NOT NULL, team TEXT NOT NULL, space_key TEXT NOT NULL,
        question_text TEXT NOT NULL, submitted_by INTEGER NOT NULL, submitted_at TEXT NOT NULL,
        PRIMARY KEY(event_date, team))''')


@router.callback_query(F.data == 'v6:spaces')
async def spaces_start(callback: CallbackQuery) -> None:
    user = await game.get_user(callback.from_user.id)
    if not is_assigned(user):
        await callback.answer('Сначала получите команду.', show_alert=True)
        return
    await callback.answer()
    await callback.message.answer(
        '<b>Открытые пространства Архива</b>\n\nВыберите пространство, после которого у команды появился новый вопрос — не только удачная фотография.',
        reply_markup=game.inline_buttons([(title, f'v6:space:{key}') for key, title in SPACES]))


@router.callback_query(F.data.startswith('v6:space:'))
async def space_selected(callback: CallbackQuery, state: FSMContext) -> None:
    key = callback.data.rsplit(':', 1)[1]
    if key not in dict(SPACES):
        return
    await state.update_data(space_key=key)
    await state.set_state(SpaceFlow.question)
    await callback.answer()
    await callback.message.answer(
        f'<b>{game.escape(dict(SPACES)[key])}</b>\n\nНапишите вопрос, который команда уносит из этого пространства. Начните с мысли «мы задумались, почему…».')


@router.message(SpaceFlow.question)
async def save_reflection(message: Message, state: FSMContext) -> None:
    user = await game.get_user(message.from_user.id)
    text = (message.text or '').strip()
    if not is_assigned(user) or len(text) < 15:
        await message.answer('Сформулируйте вопрос подробнее — не менее 15 символов.')
        return
    data = await state.get_data()
    await game.db.execute('''INSERT INTO open_space_reflections(event_date, team, space_key, question_text, submitted_by, submitted_at)
        VALUES(?, ?, ?, ?, ?, ?) ON CONFLICT(event_date, team) DO UPDATE SET
        space_key=excluded.space_key, question_text=excluded.question_text, submitted_by=excluded.submitted_by, submitted_at=excluded.submitted_at''',
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
    await callback.message.answer(
        f'<b>Сценарий ведущего · {LOCATION_TITLES[key]}</b>\n\n<b>Вступление</b>\n{script[0]}\n\n'
        '<b>Ход</b>\n1. Коротко объясните правила.\n2. Дайте команде выполнить действие.\n3. Попросите объяснить один выбор.\n4. Зафиксируйте общий ответ.\n\n'
        f'<b>Вопрос перед завершением</b>\n{script[1]}')


async def final_report(target: Message, user_id: int) -> None:
    user = await game.get_user(user_id)
    if not is_assigned(user):
        await target.answer('Финал откроется после назначения команды.')
        return
    final_open = await game.db.setting('final_open', '0')
    done = await completed_locations(user)
    choices = await game.team_choices(user['event_date'], user['team'])
    if final_open != '1' or len(done) < 5 or len(choices) < 4:
        await target.answer('<b>◻️ Эффект бабочки закрыт</b>\n\n'
            f'Маршрут: {progress_bar(len(done), 5)} {len(done)}/5\nРешения: {progress_bar(len(choices), 4)} {len(choices)}/4\n\n'
            'Последствия не показываются до подтверждения главного Архивариуса.')
        return
    title, text, _ = final_archetype(await game.team_parameters(user['event_date'], user['team']))
    reflection = await game.db.one('SELECT question_text FROM open_space_reflections WHERE event_date=? AND team=?', (user['event_date'], user['team']))
    games = await game.db.all('''SELECT DISTINCT p.game_id FROM team_game_progress p JOIN users u ON u.telegram_id=p.user_id
        WHERE u.event_date=? AND u.team=? AND p.passed=1 LIMIT 5''', (user['event_date'], user['team']))
    themes = [GAMES_BY_ID[row['game_id']].title for row in games if row['game_id'] in GAMES_BY_ID][:3]
    lines = ['<b>🦋 ЭФФЕКТ БАБОЧКИ</b>', '', f'Версия Архива команды «{game.escape(user["team"])}»: <b>«{game.escape(title)}»</b>', '', game.escape(text)]
    if themes:
        lines += ['', '<b>Что команда помогла сохранить</b>', *(f'• {game.escape(item)}' for item in themes)]
    if reflection:
        lines += ['', '<b>Вопрос, который команда уносит дальше</b>', f'«{game.escape(reflection["question_text"])}»']
    await target.answer('\n'.join(lines))


@router.callback_query(F.data == 'v6:final')
async def final_callback(callback: CallbackQuery) -> None:
    await callback.answer()
    await final_report(callback.message, callback.from_user.id)

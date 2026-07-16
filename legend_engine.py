from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message

import app as game
from game_data import PARAMETER_LABELS, TEAM_COLORS
from quest_common import completed_locations, is_assigned, passed_games, progress_bar
from team_games import GAMES_BY_ID, TeamGame
from storage import utcnow

router = Router(name='last_keeper_legend_engine')

VALUE_LABELS = {
    'memory': 'Память',
    'truth': 'Точность',
    'living_language': 'Живое слово',
    'responsibility': 'Ответственность',
    'progress': 'Будущее',
    'unity': 'Связь поколений',
    'cultural_code': 'Культурный код',
    'courage': 'Смелость',
    'human_voice': 'Человеческий голос',
    'curiosity': 'Любознательность',
}

VALUE_ICONS = {
    'memory': '📜', 'truth': '🔎', 'living_language': '💬', 'responsibility': '⚖️',
    'progress': '🚀', 'unity': '🤝', 'cultural_code': '🪆', 'courage': '🔥',
    'human_voice': '🕯', 'curiosity': '🧭',
}

TEAM_FOUNDATIONS = {
    'Красные': ('Огненная летопись', 'Вы не ждали, пока память спасёт кто-то другой. Вы входили в неизвестность первыми и возвращали Архиву движение.'),
    'Белые': ('Светлый свод', 'Вы искали ясность там, где проще было поверить красивой версии. Ваш Архив держится на точности и внутренней честности.'),
    'Оранжевые': ('Мост эпох', 'Вы соединяли то, что обычно разделяют: прошлое и будущее, традицию и новый язык, личный опыт и общую историю.'),
    'Зелёные': ('Живая память', 'Вы сохраняли не только документы, но и человеческое присутствие — голос, интонацию, вопрос и право быть услышанным.'),
    'Синие': ('Карта будущего', 'Вы смотрели на наследие как на маршрут вперёд. Для вас память ценна не потому, что она закончена, а потому, что продолжает действовать.'),
}

PAIR_TITLES = {
    frozenset(('memory', 'truth')): 'Стражи подлинной памяти',
    frozenset(('memory', 'human_voice')): 'Хранители живых свидетельств',
    frozenset(('living_language', 'unity')): 'Проводники живого слова',
    frozenset(('progress', 'responsibility')): 'Архитекторы ответственного будущего',
    frozenset(('cultural_code', 'living_language')): 'Переводчики культурного кода',
    frozenset(('courage', 'progress')): 'Первые за горизонтом',
    frozenset(('truth', 'curiosity')): 'Исследователи скрытых связей',
    frozenset(('unity', 'human_voice')): 'Собиратели голосов поколений',
}


@dataclass(frozen=True)
class ValueOption:
    code: str
    title: str
    note: str
    effects: dict[str, int]


@dataclass(frozen=True)
class ValueDilemma:
    title: str
    prompt: str
    options: tuple[ValueOption, ...]


LOCATION_DILEMMAS: dict[str, tuple[ValueDilemma, ValueDilemma]] = {
    'culture': (
        ValueDilemma('Слово меняет форму', 'Старинный текст понятен не всем. Что ты сохранишь в первую очередь?', (
            ValueOption('form', 'Оставлю исходную форму', 'Подлинность важнее удобства.', {'memory': 2, 'truth': 2}),
            ValueOption('voice', 'Переведу на живой язык', 'Смысл должен снова заговорить.', {'living_language': 2, 'unity': 1}),
            ValueOption('dialogue', 'Дам обе версии рядом', 'Прошлое и настоящее должны спорить честно.', {'cultural_code': 1, 'curiosity': 2}),
        )),
        ValueDilemma('Символ без подписи', 'Ты находишь культурный символ, который узнают многие, но объяснить могут не все. Твой шаг?', (
            ValueOption('protect', 'Сохраню без изменений', 'Не всё наследие обязано быть упрощено.', {'memory': 2, 'cultural_code': 2}),
            ValueOption('explain', 'Расскажу через личную историю', 'Смысл начинается с человеческой связи.', {'human_voice': 2, 'living_language': 1}),
            ValueOption('rebuild', 'Создам новую форму', 'Иногда традиции нужен новый носитель.', {'progress': 2, 'courage': 1}),
        )),
    ),
    'science': (
        ValueDilemma('Цена открытия', 'Открытие готово, но последствия ещё не ясны. Что важнее сейчас?', (
            ValueOption('launch', 'Дать миру возможность', 'Прогресс не ждёт полной уверенности.', {'progress': 2, 'courage': 2}),
            ValueOption('verify', 'Остановиться и проверить', 'Ответственность начинается до запуска.', {'responsibility': 2, 'truth': 2}),
            ValueOption('share', 'Открыть данные для обсуждения', 'Сложные решения должны быть коллективными.', {'unity': 2, 'curiosity': 1}),
        )),
        ValueDilemma('Неудачный эксперимент', 'Результат не подтвердил гипотезу. Как поступить с этой страницей Архива?', (
            ValueOption('publish', 'Сохранить неудачу целиком', 'Ошибка тоже является знанием.', {'truth': 2, 'responsibility': 1}),
            ValueOption('repeat', 'Повторить другим способом', 'Сомнение может открыть новый путь.', {'curiosity': 2, 'courage': 1}),
            ValueOption('teach', 'Превратить её в урок', 'Знание становится сильнее, когда передаётся.', {'unity': 2, 'progress': 1}),
        )),
    ),
    'history': (
        ValueDilemma('Неполный источник', 'Документ сохранился частично. Как его представить будущим читателям?', (
            ValueOption('literal', 'Показать только сохранившееся', 'Пробел честнее красивой догадки.', {'truth': 2, 'memory': 1}),
            ValueOption('context', 'Добавить проверенный контекст', 'Фрагменту нужен исторический горизонт.', {'curiosity': 2, 'responsibility': 1}),
            ValueOption('voices', 'Сопоставить разные свидетельства', 'История не обязана говорить одним голосом.', {'human_voice': 2, 'unity': 1}),
        )),
        ValueDilemma('Спор об эпохе', 'Два свидетельства противоречат друг другу. Что станет основой рассказа?', (
            ValueOption('evidence', 'То, что лучше подтверждено', 'Точность важнее удобной версии.', {'truth': 2, 'responsibility': 1}),
            ValueOption('both', 'Оба взгляда рядом', 'Противоречие тоже часть памяти.', {'curiosity': 2, 'human_voice': 1}),
            ValueOption('question', 'Открытый вопрос для будущего', 'Не каждый спор нужно закрывать сегодня.', {'courage': 1, 'progress': 2}),
        )),
    ),
    'memory': (
        ValueDilemma('Имя или число', 'В Архиве осталось мало места. Что нельзя потерять?', (
            ValueOption('names', 'Имена и личные судьбы', 'Память начинается с человека.', {'human_voice': 2, 'memory': 1}),
            ValueOption('facts', 'Проверенные факты и даты', 'Общая память требует точного основания.', {'truth': 2, 'responsibility': 1}),
            ValueOption('letters', 'Письма и голоса очевидцев', 'Интонация иногда говорит больше справки.', {'human_voice': 2, 'unity': 1}),
        )),
        ValueDilemma('Трудная память', 'История вызывает спор и боль. Как говорить о ней?', (
            ValueOption('quiet', 'Бережно и без громких выводов', 'Тишина тоже может быть формой уважения.', {'memory': 2, 'responsibility': 1}),
            ValueOption('direct', 'Прямо, не скрывая сложного', 'Честность важнее спокойствия.', {'truth': 2, 'courage': 1}),
            ValueOption('together', 'Через разговор поколений', 'Память живёт, когда её разделяют.', {'unity': 2, 'human_voice': 1}),
        )),
    ),
    'open': (
        ValueDilemma('Пространство, которое осталось с тобой', 'После открытых пространств что ты унесёшь дальше?', (
            ValueOption('question', 'Новый вопрос', 'Любознательность продолжает маршрут после события.', {'curiosity': 2, 'progress': 1}),
            ValueOption('image', 'Образ, который хочется сохранить', 'Культурная память часто начинается с символа.', {'cultural_code': 2, 'memory': 1}),
            ValueOption('story', 'Историю, которую расскажу другому', 'Наследие живёт в передаче.', {'living_language': 2, 'unity': 1}),
        )),
        ValueDilemma('Последний свободный фрагмент', 'Архив позволяет сохранить только один след открытого пространства. Что выберешь?', (
            ValueOption('past', 'Подлинный фрагмент прошлого', 'Основание должно остаться узнаваемым.', {'memory': 2, 'truth': 1}),
            ValueOption('person', 'Личную реакцию участника', 'Культура продолжается через человека.', {'human_voice': 2, 'living_language': 1}),
            ValueOption('future', 'Идею для нового проекта', 'Сохранение может стать началом действия.', {'progress': 2, 'courage': 1}),
        )),
    ),
}


async def init_legend_engine() -> None:
    await game.db.execute('''CREATE TABLE IF NOT EXISTS personal_value_choices(
        user_id INTEGER NOT NULL,
        game_id TEXT NOT NULL,
        option_code TEXT NOT NULL,
        effects_json TEXT NOT NULL,
        choice_title TEXT NOT NULL,
        choice_note TEXT NOT NULL,
        created_at TEXT NOT NULL,
        PRIMARY KEY(user_id, game_id)
    )''')
    await game.db.execute('CREATE INDEX IF NOT EXISTS idx_value_choices_user ON personal_value_choices(user_id)')


def dilemma_for(item: TeamGame) -> ValueDilemma:
    pair = tuple(game_item for game_item in GAMES_BY_ID.values() if game_item.team == item.team and game_item.location == item.location)
    index = 0 if pair and pair[0].game_id == item.game_id else 1
    return LOCATION_DILEMMAS[item.location][index]


async def value_choice_count(user_id: int) -> int:
    row = await game.db.one('SELECT COUNT(*) AS total FROM personal_value_choices WHERE user_id = ?', (user_id,))
    return int(row['total']) if row else 0


async def personal_values(user_id: int) -> Counter[str]:
    rows = await game.db.all('SELECT effects_json FROM personal_value_choices WHERE user_id = ?', (user_id,))
    values: Counter[str] = Counter()
    for row in rows:
        values.update({key: int(value) for key, value in json.loads(row['effects_json']).items()})
    return values


async def team_personal_values(event_date: str, team: str) -> Counter[str]:
    rows = await game.db.all('''SELECT c.effects_json FROM personal_value_choices c
        JOIN users u ON u.telegram_id = c.user_id
        WHERE u.event_date = ? AND u.team = ?''', (event_date, team))
    values: Counter[str] = Counter()
    for row in rows:
        values.update({key: int(value) for key, value in json.loads(row['effects_json']).items()})
    return values


def top_values(values: Counter[str], limit: int = 3) -> list[tuple[str, int]]:
    return sorted(values.items(), key=lambda item: (-item[1], item[0]))[:limit]


def legend_title(values: Counter[str], fallback: str) -> str:
    strongest = [key for key, value in top_values(values, 2) if value > 0]
    if len(strongest) == 2:
        return PAIR_TITLES.get(frozenset(strongest), fallback)
    if strongest:
        return f'Хранители: {VALUE_LABELS[strongest[0]]}'
    return fallback


def values_visual(values: Counter[str], limit: int = 5) -> str:
    strongest = top_values(values, limit)
    if not strongest:
        return '◻️ Контур ещё не проявился'
    maximum = max(value for _, value in strongest) or 1
    lines = []
    for key, value in strongest:
        filled = max(1, round(value / maximum * 5))
        lines.append(f'{VALUE_ICONS.get(key, "•")} <b>{VALUE_LABELS.get(key, key)}</b>  {"■" * filled}{"□" * (5 - filled)}')
    return '\n'.join(lines)


def legend_paragraph(values: Counter[str]) -> str:
    strongest = [key for key, value in top_values(values, 3) if value > 0]
    clauses = {
        'memory': 'вы оставляли опору, когда легче было начать с чистого листа',
        'truth': 'вы проверяли источник, даже когда красивая версия звучала убедительнее',
        'living_language': 'вы давали наследию новый голос, не превращая его в пустой знак',
        'responsibility': 'вы думали о последствиях раньше, чем о громком результате',
        'progress': 'вы видели в памяти не конец истории, а начало следующего шага',
        'unity': 'вы искали мост между людьми, поколениями и разными взглядами',
        'cultural_code': 'вы замечали символы, в которых страна узнаёт себя',
        'courage': 'вы принимали решение там, где готового ответа не существовало',
        'human_voice': 'вы возвращали в историю имя, интонацию и личную судьбу',
        'curiosity': 'вы сохраняли право задавать вопрос вместо удобного финального ответа',
    }
    selected = [clauses[key] for key in strongest if key in clauses]
    if not selected:
        return 'Ваш путь ещё только начинает складываться в легенду.'
    return 'Вы не искали единственно правильный путь: ' + '; '.join(selected) + '.'


async def send_value_dilemma(target: Message, user_id: int, game_id: str) -> None:
    item = GAMES_BY_ID.get(game_id)
    user = await game.get_user(user_id)
    if not item or not is_assigned(user) or item.team != user['team']:
        await target.answer('Этот фрагмент не принадлежит твоему пути.')
        return
    passed = await passed_games(user_id)
    if game_id not in passed:
        await target.answer('Сначала восстанови знание в этой миссии.')
        return
    existing = await game.db.one('SELECT choice_title FROM personal_value_choices WHERE user_id = ? AND game_id = ?', (user_id, game_id))
    if existing:
        await target.answer(f'Выбор уже сохранён: <b>{game.escape(existing["choice_title"])}</b>. Изменить его после фиксации нельзя.')
        return
    dilemma = dilemma_for(item)
    lines = [
        '╭──────────────╮',
        '   <b>ВЫБОР ХРАНИТЕЛЯ</b>',
        '╰──────────────╯',
        '',
        f'<b>{game.escape(dilemma.title)}</b>',
        game.escape(dilemma.prompt),
        '',
        '<i>Здесь нет правильного ответа. Архив запомнит не знание, а твою позицию.</i>',
    ]
    buttons = [(f'{index + 1} · {option.title}', f'legend:pick:{game_id}:{option.code}') for index, option in enumerate(dilemma.options)]
    await target.answer('\n'.join(lines), reply_markup=game.inline_buttons(buttons))


@router.callback_query(F.data.startswith('legend:start:'))
async def start_value_choice(callback: CallbackQuery) -> None:
    await callback.answer()
    await send_value_dilemma(callback.message, callback.from_user.id, callback.data.split(':', 2)[2])


@router.callback_query(F.data.startswith('legend:pick:'))
async def pick_value(callback: CallbackQuery) -> None:
    parts = callback.data.split(':')
    if len(parts) != 4:
        return
    _, _, game_id, option_code = parts
    item = GAMES_BY_ID.get(game_id)
    if not item:
        return
    dilemma = dilemma_for(item)
    option = next((value for value in dilemma.options if value.code == option_code), None)
    if not option:
        return
    await callback.answer()
    await callback.message.edit_text(
        '╭──────────────╮\n'
        '   <b>ПЕРЕД ФИКСАЦИЕЙ</b>\n'
        '╰──────────────╯\n\n'
        f'Ты выбираешь: <b>{game.escape(option.title)}</b>\n\n'
        f'{game.escape(option.note)}\n\n'
        '<i>Этот след войдёт в твою личную легенду и общий характер команды.</i>',
        reply_markup=game.inline_buttons([
            ('✓ Сохранить выбор', f'legend:save:{game_id}:{option.code}'),
            ('↩ Вернуться', f'legend:start:{game_id}'),
        ]),
    )


@router.callback_query(F.data.startswith('legend:save:'))
async def save_value(callback: CallbackQuery) -> None:
    parts = callback.data.split(':')
    if len(parts) != 4:
        return
    _, _, game_id, option_code = parts
    item = GAMES_BY_ID.get(game_id)
    if not item:
        return
    dilemma = dilemma_for(item)
    option = next((value for value in dilemma.options if value.code == option_code), None)
    if not option:
        return
    await game.db.execute('''INSERT INTO personal_value_choices(
        user_id, game_id, option_code, effects_json, choice_title, choice_note, created_at
    ) VALUES(?, ?, ?, ?, ?, ?, ?)
    ON CONFLICT(user_id, game_id) DO NOTHING''', (
        callback.from_user.id, game_id, option.code,
        json.dumps(option.effects, ensure_ascii=False), option.title, option.note, utcnow(),
    ))
    count = await value_choice_count(callback.from_user.id)
    await callback.answer('Выбор сохранён', show_alert=True)
    await callback.message.edit_text(
        '┏━━━━━━━━━━━━━━┓\n'
        '   <b>СЛЕД СОХРАНЁН</b>\n'
        '┗━━━━━━━━━━━━━━┛\n\n'
        f'<b>{game.escape(option.title)}</b>\n'
        f'{game.escape(option.note)}\n\n'
        f'Личная легенда: {progress_bar(count, 10)}  {count}/10\n\n'
        '<i>Полный смысл выбора проявится только после открытия финала.</i>',
        reply_markup=game.inline_buttons([
            ('🎮 К играм', 'tq:games'),
            ('◻️ Моя легенда', 'legend:final'),
        ]),
    )


async def final_readiness(user) -> tuple[bool, str]:
    route_done = len(await completed_locations(user))
    team_choices = await game.team_choices(user['event_date'], user['team'])
    final_open = await game.db.setting('final_open', '0')
    if route_done < 5:
        return False, f'Маршрут восстановлен на {route_done}/5. Завершите все живые главы.'
    if len(team_choices) < 4:
        return False, f'Командных решений: {len(team_choices)}/4. Архиву не хватает ключевых фрагментов.'
    if final_open != '1':
        return False, 'Контур собран. Последствие остаётся закрытым до решения главного Архивариуса.'
    return True, ''


async def reveal_final(target: Message, user_id: int) -> None:
    user = await game.get_user(user_id)
    if not is_assigned(user):
        await target.answer('Легенда откроется после назначения команды.')
        return
    ready, reason = await final_readiness(user)
    if not ready and not await game.is_admin(user_id):
        count = await value_choice_count(user_id)
        await target.answer(
            '╭──────────────╮\n'
            '   <b>ЭФФЕКТ БАБОЧКИ</b>\n'
            '╰──────────────╯\n\n'
            '◻️ <b>Финал закрыт</b>\n\n'
            f'{game.escape(reason)}\n\n'
            f'Личных выборов сохранено: {count}/10\n'
            '<i>До открытия бот не показывает скрытые параметры, будущий архетип или последствия решений.</i>'
        )
        return

    personal = await personal_values(user_id)
    team_values = await team_personal_values(user['event_date'], user['team'])
    team_parameters = await game.team_parameters(user['event_date'], user['team'])
    team_values.update(team_parameters)
    foundation_title, foundation_text = TEAM_FOUNDATIONS[user['team']]
    team_title = legend_title(team_values, foundation_title)
    personal_title = legend_title(personal, 'Хранитель незавершённой страницы')
    saved = top_values(team_values, 1)
    fragile = sorted(team_values.items(), key=lambda item: (item[1], item[0]))[:1]
    saved_label = VALUE_LABELS.get(saved[0][0], saved[0][0]) if saved else 'право продолжать память'
    fragile_label = VALUE_LABELS.get(fragile[0][0], fragile[0][0]) if fragile else 'то, что ещё предстоит сохранить'

    await target.answer('…\n\n<b>Архив завершает реконструкцию.</b>\nНе закрывайте эту страницу.')
    await target.answer('▓▓▓▓░░░░░░  41%\n<i>Сопоставляем выборы, маршруты и человеческие голоса…</i>')
    await target.answer('▓▓▓▓▓▓▓▓▓▓  100%\n\n<b>АРХИВ ВОССТАНОВЛЕН</b>\nНо он стал другим — потому что его сохраняли вы.')
    await target.answer(
        '┏━━━━━━━━━━━━━━━━━━┓\n'
        f'   <b>ЛЕГЕНДА КОМАНДЫ «{game.escape(user["team"].upper())}»</b>\n'
        '┗━━━━━━━━━━━━━━━━━━┛\n\n'
        f'<b>{game.escape(team_title)}</b>\n\n'
        f'{game.escape(foundation_text)}\n\n'
        f'{game.escape(legend_paragraph(team_values))}\n\n'
        '<b>Сильные линии Архива</b>\n'
        f'{values_visual(team_values)}\n\n'
        f'✓ Сохранено сильнее всего: <b>{game.escape(saved_label)}</b>\n'
        f'◌ Осталось хрупким: <b>{game.escape(fragile_label)}</b>\n\n'
        '<i>Это не оценка и не победа над другими командами. Это версия памяти, которую создали ваши решения.</i>'
    )
    await target.answer(
        '╭──────────────╮\n'
        '   <b>ТВОЯ ЛИЧНАЯ ЛЕГЕНДА</b>\n'
        '╰──────────────╯\n\n'
        f'<b>{game.escape(personal_title)}</b>\n\n'
        f'{game.escape(legend_paragraph(personal))}\n\n'
        f'{values_visual(personal)}\n\n'
        '<b>Архив закрывается. Память — нет.</b>\n'
        '<i>Теперь твои выборы нельзя изменить, но к этой легенде можно вернуться в любой момент.</i>'
    )


@router.callback_query(F.data.in_({'legend:final', 'progress:final'}))
async def final_callback(callback: CallbackQuery) -> None:
    await callback.answer()
    await reveal_final(callback.message, callback.from_user.id)


@router.message(Command('legend'))
@router.message(F.text == '◻️ Моя легенда')
@router.message(F.text == '🦋 Моя легенда')
async def legend_command(message: Message) -> None:
    await reveal_final(message, message.from_user.id)

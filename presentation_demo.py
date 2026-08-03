from __future__ import annotations

import asyncio
from dataclasses import dataclass

from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

import app as game
from demo_visuals import visual
from storage import utcnow

router = Router(name='last_keeper_presentation_demo')


@dataclass(frozen=True)
class DemoChoice:
    code: str
    title: str
    consequence: str
    value: str


FIRST_CHOICES = (
    DemoChoice('word', 'Сохранить русский язык', 'Слова остались живыми — и снова связали поколения.', 'Живое слово'),
    DemoChoice('discovery', 'Сохранить великое открытие', 'Будущее получило опору для следующего шага.', 'Будущее'),
    DemoChoice('culture', 'Сохранить культурный образ', 'Россия осталась узнаваемой через символы, музыку и искусство.', 'Культурный код'),
)

SECOND_BRANCHES = {
    'word': (
        'Архив запомнил: вы выбрали живое слово. Теперь решите, как передать его дальше.',
        (
            DemoChoice('original', 'Оставить только оригинал', 'Подлинность сохранена, но путь к ней стал сложнее.', 'Память'),
            DemoChoice('living', 'Дать современное объяснение', 'Смысл стал доступнее молодым читателям.', 'Живое слово'),
            DemoChoice('bridge', 'Показать обе версии рядом', 'Прошлое и настоящее вступили в диалог.', 'Связь поколений'),
        ),
    ),
    'discovery': (
        'Архив запомнил: вы выбрали открытие. Теперь решите, что важнее сохранить вместе с ним.',
        (
            DemoChoice('fact', 'Точные факты', 'История сохранила надёжные координаты.', 'Точность'),
            DemoChoice('person', 'Историю человека', 'Достижение получило лицо и голос.', 'Человеческий голос'),
            DemoChoice('future', 'Вопрос к будущему', 'Память превратилась в приглашение продолжать путь.', 'Будущее'),
        ),
    ),
    'culture': (
        'Архив запомнил: вы выбрали культурный образ. Теперь решите, как он должен жить дальше.',
        (
            DemoChoice('protect', 'Бережно сохранить форму', 'Образ остался узнаваемым и подлинным.', 'Память'),
            DemoChoice('rethink', 'Переосмыслить для молодёжи', 'Культурный код получил новую форму.', 'Смелость'),
            DemoChoice('create', 'Создать новый проект на его основе', 'Наследие стало действием, а не экспонатом.', 'Культурный код'),
        ),
    ),
}

LEGENDS = {
    ('word', 'original'): ('Страж подлинного слова', 'Вы сохраняете язык в его исторической глубине.'),
    ('word', 'living'): ('Проводник живого слова', 'Вы помогаете наследию говорить с новым поколением.'),
    ('word', 'bridge'): ('Создатель моста эпох', 'Вы соединяете оригинал и современное прочтение.'),
    ('discovery', 'fact'): ('Архивариус точного пути', 'Вы сохраняете достижения России через проверенный факт.'),
    ('discovery', 'person'): ('Хранитель имени', 'Для вас открытие невозможно отделить от человека.'),
    ('discovery', 'future'): ('Архитектор будущего', 'Вы превращаете память о достижении в импульс к новому.'),
    ('culture', 'protect'): ('Страж культурного кода', 'Вы бережёте форму, в которой Россия узнаёт себя.'),
    ('culture', 'rethink'): ('Переводчик культурного кода', 'Вы открываете наследие современному зрителю.'),
    ('culture', 'create'): ('Продолжатель традиции', 'Вы доказываете, что любовь к культуре проявляется в созидании.'),
}

QUOTE_OPENINGS = (
    'Любовь к России начинается', 'Память о России становится живой', 'Наследие России остаётся с нами',
    'Россия звучит в будущем', 'История России не заканчивается', 'Культурная связь с Россией крепнет',
    'Россия становится ближе', 'Память поколений сохраняет Россию', 'Будущее России начинается', 'Сила России раскрывается',
)
QUOTE_ENDINGS = (
    'когда мы бережно передаём её истории дальше.', 'когда её язык продолжает объединять людей.',
    'когда достижения прошлого вдохновляют на новые открытия.', 'когда за великими событиями мы видим судьбы людей.',
    'когда молодое поколение открывает её культуру по-своему.', 'когда память становится не обязанностью, а личным выбором.',
    'когда традиция не замирает, а продолжает развиваться.', 'когда мы сохраняем правду, смысл и человеческий голос.',
    'когда прошлое помогает нам ответственнее строить будущее.', 'когда каждый становится хранителем хотя бы одной истории.',
)


async def init_presentation_demo() -> None:
    await game.db.execute('''CREATE TABLE IF NOT EXISTS presentation_demo_sessions(
        user_id INTEGER PRIMARY KEY,
        first_choice TEXT NOT NULL DEFAULT '',
        second_choice TEXT NOT NULL DEFAULT '',
        quote_index INTEGER NOT NULL UNIQUE,
        stage TEXT NOT NULL DEFAULT '',
        attempts INTEGER NOT NULL DEFAULT 0,
        started_at TEXT NOT NULL,
        completed_at TEXT
    )''')
    for column, definition in [('stage', "TEXT NOT NULL DEFAULT ''"), ('attempts', 'INTEGER NOT NULL DEFAULT 0')]:
        try:
            await game.db.execute(f'ALTER TABLE presentation_demo_sessions ADD COLUMN {column} {definition}')
        except Exception:
            pass
    for key, value in (('showcase_mode', 'mixed'), ('demo_enabled', '1')):
        if not await game.db.setting(key, ''):
            await game.db.set_setting(key, value)


async def showcase_mode() -> str:
    return await game.db.setting('showcase_mode', 'mixed')


async def quote_for(user_id: int) -> tuple[int, str]:
    row = await game.db.one('SELECT quote_index FROM presentation_demo_sessions WHERE user_id = ?', (user_id,))
    if row:
        index = int(row['quote_index'])
    else:
        used = {int(item['quote_index']) for item in await game.db.all('SELECT quote_index FROM presentation_demo_sessions')}
        index = next((number for number in range(100) if number not in used), user_id % 100)
        await game.db.execute(
            'INSERT OR IGNORE INTO presentation_demo_sessions(user_id, quote_index, started_at) VALUES(?, ?, ?)',
            (user_id, index, utcnow()),
        )
    return index + 1, f'{QUOTE_OPENINGS[index // 10]} {QUOTE_ENDINGS[index % 10]}'


async def send_entry(target: Message, user_id: int, state: FSMContext | None = None) -> None:
    if state:
        await state.clear()
    mode = await showcase_mode()
    user = await game.get_user(user_id)
    admin = await game.is_admin(user_id)
    if user and mode != 'presentation':
        await target.answer('<b>АРХИВ УЗНАЛ ВАС</b>\n\nВаш путь сохранён.', reply_markup=game.main_menu(admin))
        return
    if mode == 'closed' and not admin:
        await target.answer('<b>Архив временно закрыт.</b>')
        return
    buttons = []
    if await game.db.setting('demo_enabled', '1') == '1':
        buttons.append(('🔓 Открыть Архив', 'show:demo'))
    if mode in {'mixed', 'event'}:
        buttons.append(('📝 Регистрация', 'show:register'))
    if admin:
        buttons.append(('🎛 Режим показа', 'show:admin'))
    await target.answer_photo(
        visual('entry'),
        caption=(
            '<b>АРХИВ ПАМЯТИ</b>\n\n'
            'Из памяти начинают исчезать слова, открытия, культурные символы и человеческие истории России.\n\n'
            '<b>До необратимых изменений: 01:59</b>\n\n'
            'Архив ищет человека, готового вмешаться.'
        ),
        reply_markup=game.inline_buttons(buttons),
    )


@router.message(CommandStart())
async def presentation_start(message: Message, state: FSMContext) -> None:
    await init_presentation_demo()
    await send_entry(message, message.from_user.id, state)


@router.callback_query(F.data == 'show:register')
async def begin_registration(callback: CallbackQuery, state: FSMContext) -> None:
    if await showcase_mode() not in {'mixed', 'event'}:
        await callback.answer('Регистрация сейчас отключена.', show_alert=True)
        return
    await callback.answer()
    await state.set_state(game.Registration.consent)
    await callback.message.answer(
        '<b>КНИГА ХРАНИТЕЛЕЙ</b>\n\nДля участия Архиву потребуются имя, возраст и Telegram ID.',
        reply_markup=game.inline_buttons([('Продолжить регистрацию', 'reg:yes')]),
    )


@router.callback_query(F.data == 'show:demo')
async def demo_start(callback: CallbackQuery) -> None:
    if await game.db.setting('demo_enabled', '1') != '1':
        await callback.answer('Демонстрация временно отключена.', show_alert=True)
        return
    await init_presentation_demo()
    await quote_for(callback.from_user.id)
    await game.db.execute(
        "UPDATE presentation_demo_sessions SET first_choice='', second_choice='', stage='choice1', attempts=0, completed_at=NULL WHERE user_id=?",
        (callback.from_user.id,),
    )
    await callback.answer()
    msg = await callback.message.answer('<b>Соединение с Архивом…</b>\n\n▓░░░░░░░░ 12%')
    await asyncio.sleep(0.55)
    await msg.edit_text('<b>Соединение с Архивом…</b>\n\n▓▓▓▓░░░░░ 43%')
    await asyncio.sleep(0.55)
    await msg.edit_text('<b>Соединение с Архивом…</b>\n\n▓▓▓▓▓▓▓░░ 78%')
    await asyncio.sleep(0.55)
    await msg.edit_text('<b>▓▓▓▓▓▓▓▓▓ 100%</b>\n\nСовпадение найдено.\n\n<b>Добро пожаловать, Хранитель.</b>', reply_markup=game.inline_buttons([('Начать реконструкцию', 'show:first')]))


@router.callback_query(F.data == 'show:first')
async def demo_first(callback: CallbackQuery) -> None:
    await callback.answer()
    await callback.message.answer(
        '<b>ФРАГМЕНТ №1 · ЧТО СОХРАНИТЬ?</b>\n\n'
        'Архив повреждён. Времени хватит только на один фрагмент.\n\n'
        '<i>Здесь нет правильного ответа. Выбор изменит следующую ситуацию.</i>',
        reply_markup=game.inline_buttons([(item.title, f'show:first:{item.code}') for item in FIRST_CHOICES]),
    )


@router.callback_query(F.data.startswith('show:first:'))
async def demo_first_choice(callback: CallbackQuery) -> None:
    code = callback.data.rsplit(':', 1)[1]
    choice = next((item for item in FIRST_CHOICES if item.code == code), None)
    if not choice:
        return
    await game.db.execute("UPDATE presentation_demo_sessions SET first_choice=?, stage='awaiting_key' WHERE user_id=?", (code, callback.from_user.id))
    await callback.answer()
    await callback.message.answer(
        f'<b>ВЫБОР СОХРАНЁН</b>\n\n{choice.consequence}\n\n'
        f'Проявившаяся линия: <b>{choice.value}</b>\n\n'
        'Но следующий фрагмент закрыт. Ключ находится не в телефоне — он спрятан <b>на слайде презентации</b>.',
    )
    await callback.message.answer_photo(
        visual('riddle'),
        caption=(
            '<b>ЗАГАДКА ХРАНИТЕЛЯ</b>\n\n'
            'Найдите на презентации строку из пролога к поэме А. С. Пушкина «Руслан и Людмила».\n\n'
            'Введите в бот слово, которое завершает строку:\n'
            '<b>«У лукоморья дуб …»</b>\n\n'
            '<i>Ответ нужно написать сообщением. Без живой подсказки цифровой путь не откроется.</i>'
        ),
    )


@router.message(F.text)
async def presentation_text_answer(message: Message) -> None:
    await init_presentation_demo()
    row = await game.db.one('SELECT first_choice, stage, attempts FROM presentation_demo_sessions WHERE user_id=?', (message.from_user.id,))
    if not row or row['stage'] != 'awaiting_key':
        return
    answer = message.text.strip().lower().replace('ё', 'е').strip(' .,!?:;"«»')
    if answer not in {'зеленый', 'зелёный'}:
        attempts = int(row['attempts']) + 1
        await game.db.execute('UPDATE presentation_demo_sessions SET attempts=? WHERE user_id=?', (attempts, message.from_user.id))
        hint = 'Подсказка: это цвет дуба.' if attempts == 1 else 'Посмотрите на первую строку: «У лукоморья дуб …»'
        await message.answer(f'<b>КЛЮЧ НЕ ПОДОШЁЛ</b>\n\n{hint}\n\nПопробуйте ещё раз.')
        return
    first_code = row['first_choice']
    await game.db.execute("UPDATE presentation_demo_sessions SET stage='choice2' WHERE user_id=?", (message.from_user.id,))
    await message.answer_photo(
        visual('restored'),
        caption=(
            '<b>КЛЮЧ ПРИНЯТ</b>\n\n'
            'Живая подсказка открыла цифровой фрагмент. Именно так офлайн-локации проекта соединяются с Telegram-ботом.\n\n'
            '<b>Архив перестроил следующую ситуацию с учётом вашего первого выбора.</b>'
        ),
        reply_markup=game.inline_buttons([('Открыть изменённую ветвь', f'show:second:{first_code}')]),
    )


@router.callback_query(F.data.startswith('show:second:'))
async def demo_second(callback: CallbackQuery) -> None:
    first_code = callback.data.rsplit(':', 1)[1]
    branch = SECOND_BRANCHES.get(first_code)
    if not branch:
        return
    prompt, options = branch
    await callback.answer()
    await callback.message.answer(
        '<b>ФРАГМЕНТ №2 · ПОСЛЕДСТВИЕ</b>\n\n'
        f'{prompt}\n\n<i>Этот вопрос уже изменён вашим первым решением.</i>',
        reply_markup=game.inline_buttons([(item.title, f'show:finish:{first_code}:{item.code}') for item in options]),
    )


@router.callback_query(F.data.startswith('show:finish:'))
async def demo_finish(callback: CallbackQuery) -> None:
    parts = callback.data.split(':')
    if len(parts) != 4:
        return
    first_code, second_code = parts[2], parts[3]
    branch = SECOND_BRANCHES.get(first_code)
    if not branch:
        return
    second = next((item for item in branch[1] if item.code == second_code), None)
    if not second:
        return
    title, legend = LEGENDS[(first_code, second_code)]
    quote_number, quote = await quote_for(callback.from_user.id)
    await game.db.execute("UPDATE presentation_demo_sessions SET second_choice=?, stage='done', completed_at=? WHERE user_id=?", (second_code, utcnow(), callback.from_user.id))
    await callback.answer()
    msg = await callback.message.answer('<b>Архив анализирует последствия…</b>\n\n▓▓▓▓░░░░░ 41%')
    await asyncio.sleep(0.65)
    await msg.edit_text('<b>Архив анализирует последствия…</b>\n\n▓▓▓▓▓▓▓░░ 78%')
    await asyncio.sleep(0.65)
    await msg.edit_text(
        '<b>━━━━━━━━━━━━━━━━━━\nДЕМО-ЛЕГЕНДА СОЗДАНА\n━━━━━━━━━━━━━━━━━━</b>\n\n'
        f'<b>{title}</b>\n\n{legend}\n\n{second.consequence}\n\n'
        '<b>2 решения создали отдельную ветвь истории.</b>\n'
        'В полном маршруте 10 решений формируют до <b>59 049</b> индивидуальных сценариев.\n\n'
        f'<b>Ваша цитата Архива №{quote_number}</b>\n<i>«{quote}»</i>\n\n'
        'Россия раскрывается здесь не как набор дат, а как живое наследие языка, культуры, науки и человеческих судеб.\n\n'
        '<b>Архив закрывается. Память — нет.</b>',
        reply_markup=game.inline_buttons([('📝 Перейти к регистрации', 'show:register'), ('↻ Пройти ещё раз', 'show:demo')]),
    )


@router.message(Command('showmode'))
async def showmode_command(message: Message) -> None:
    if await game.is_admin(message.from_user.id):
        await send_admin_modes(message)


@router.callback_query(F.data == 'show:admin')
async def show_admin(callback: CallbackQuery) -> None:
    if not await game.is_admin(callback.from_user.id):
        return
    await callback.answer()
    await send_admin_modes(callback.message)


async def send_admin_modes(target: Message) -> None:
    mode = await showcase_mode()
    demo = await game.db.setting('demo_enabled', '1')
    await target.answer(
        '<b>🎬 РЕЖИМ БОТА</b>\n\n'
        f'Режим: <b>{mode}</b>\nДемо: <b>{"включено" if demo == "1" else "выключено"}</b>',
        reply_markup=game.inline_buttons([
            ('🎤 Презентация', 'show:mode:presentation'), ('✨ Демо + регистрация', 'show:mode:mixed'),
            ('🚀 Мероприятие', 'show:mode:event'), ('🔒 Закрыть', 'show:mode:closed'),
            ('Вкл./выкл. демо', 'show:toggle-demo'),
        ], columns=2),
    )


@router.callback_query(F.data.startswith('show:mode:'))
async def set_show_mode(callback: CallbackQuery) -> None:
    if not await game.is_admin(callback.from_user.id):
        return
    mode = callback.data.rsplit(':', 1)[1]
    if mode not in {'presentation', 'mixed', 'event', 'closed'}:
        return
    await game.db.set_setting('showcase_mode', mode)
    await callback.answer(f'Режим: {mode}', show_alert=True)
    await send_admin_modes(callback.message)


@router.callback_query(F.data == 'show:toggle-demo')
async def toggle_demo(callback: CallbackQuery) -> None:
    if not await game.is_admin(callback.from_user.id):
        return
    current = await game.db.setting('demo_enabled', '1')
    value = '0' if current == '1' else '1'
    await game.db.set_setting('demo_enabled', value)
    await callback.answer('Демо включено' if value == '1' else 'Демо выключено', show_alert=True)
    await send_admin_modes(callback.message)

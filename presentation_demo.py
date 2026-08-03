from __future__ import annotations

import asyncio
from dataclasses import dataclass

from aiogram import F, Router
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

import app as game
from storage import utcnow

router = Router(name='last_keeper_presentation_demo')


@dataclass(frozen=True)
class Choice:
    code: str
    title: str
    value: str
    consequence: str


VALUES = {
    'memory': 'Память',
    'voice': 'Живое слово',
    'future': 'Будущее',
    'truth': 'Точность',
    'human': 'Человеческий голос',
}

TASK1 = (
    Choice('memory', 'Сохранить подлинную форму', 'memory', 'Архив сохранил глубину оригинала.'),
    Choice('voice', 'Сделать понятным молодёжи', 'voice', 'Наследие снова заговорило современным языком.'),
    Choice('future', 'Создать новую форму на основе оригинала', 'future', 'Память превратилась в импульс к созиданию.'),
)

TASK5 = (
    Choice('truth', 'Сначала проверить каждый факт', 'truth', 'Архив стал точнее, но восстановление заняло больше времени.'),
    Choice('human', 'Сначала вернуть имена и судьбы людей', 'human', 'История обрела человеческий голос.'),
    Choice('future', 'Сначала открыть материалы молодому поколению', 'future', 'Архив начал жить дальше, а не остался закрытым хранилищем.'),
)

LEGENDS = {
    'memory': ('Страж подлинной памяти', 'Вы сохраняете опору, без которой будущее теряет смысл.'),
    'voice': ('Проводник живого слова', 'Вы умеете делать наследие понятным, не превращая его в пустой знак.'),
    'future': ('Архитектор будущего', 'Вы превращаете память о России в действие и новый замысел.'),
    'truth': ('Архивариус точного пути', 'Вы не позволяете эффектной версии вытеснить проверенный факт.'),
    'human': ('Хранитель человеческих историй', 'Для вас история России начинается с имени, голоса и судьбы человека.'),
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
    'когда прошлое помогает ответственнее строить будущее.', 'когда каждый становится хранителем хотя бы одной истории.',
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
    for key, value in (('showcase_mode', 'mixed'), ('demo_enabled', '1')):
        if not await game.db.setting(key, ''):
            await game.db.set_setting(key, value)


async def showcase_mode() -> str:
    return await game.db.setting('showcase_mode', 'mixed')


async def quote_for(user_id: int) -> tuple[int, str]:
    row = await game.db.one('SELECT quote_index FROM presentation_demo_sessions WHERE user_id=?', (user_id,))
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
    await target.answer(
        '<b>━━━━━━━━━━━━━━━━━━\nАРХИВ ПАМЯТИ\n━━━━━━━━━━━━━━━━━━</b>\n\n'
        'Повреждены пять фрагментов: слово, открытие, источник, живая память и связь поколений.\n\n'
        '<b>На восстановление — около 3 минут.</b>\n\n'
        'Каждое действие меняет итоговую легенду Хранителя.',
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
        "UPDATE presentation_demo_sessions SET first_choice='', second_choice='', stage='task1', attempts=0, completed_at=NULL WHERE user_id=?",
        (callback.from_user.id,),
    )
    await callback.answer()
    msg = await callback.message.answer('<b>Подключение к Архиву…</b>\n\n▰▱▱▱▱ 18%')
    await asyncio.sleep(0.55)
    await msg.edit_text('<b>Сопоставляем культурные фрагменты…</b>\n\n▰▰▰▱▱ 57%')
    await asyncio.sleep(0.55)
    await msg.edit_text('<b>Хранитель найден.</b>\n\n▰▰▰▰▰ 100%', reply_markup=game.inline_buttons([('Начать 5 испытаний', 'show:t1')]))


@router.callback_query(F.data == 'show:t1')
async def task1(callback: CallbackQuery) -> None:
    await callback.answer()
    await callback.message.answer(
        '<b>1/5 · ЦЕНА СОХРАНЕНИЯ</b>\n\n'
        'Старинный текст дошёл до будущего, но его почти перестали понимать. Что вы сохраните в первую очередь?\n\n'
        '<i>Правильного ответа нет: выбор формирует вашу легенду.</i>',
        reply_markup=game.inline_buttons([(item.title, f'show:t1:{item.code}') for item in TASK1]),
    )


@router.callback_query(F.data.startswith('show:t1:'))
async def task1_answer(callback: CallbackQuery) -> None:
    code = callback.data.rsplit(':', 1)[1]
    item = next((x for x in TASK1 if x.code == code), None)
    if not item:
        return
    await game.db.execute("UPDATE presentation_demo_sessions SET first_choice=?, stage='task2' WHERE user_id=?", (code, callback.from_user.id))
    await callback.answer()
    await callback.message.answer(
        f'<b>ВЕТВЬ СОХРАНЕНА</b>\n\n{item.consequence}\n\nЛиния: <b>{VALUES[item.value]}</b>',
        reply_markup=game.inline_buttons([('Перейти к шифру', 'show:t2')]),
    )


@router.callback_query(F.data == 'show:t2')
async def task2(callback: CallbackQuery) -> None:
    await callback.answer()
    await callback.message.answer(
        '<b>2/5 · ЭМОДЗИ-ШИФР</b>\n\n🚀 🌍 1️⃣ 👨‍🚀 🇷🇺\n\n'
        'Какое событие российской истории зашифровано?',
        reply_markup=game.inline_buttons([
            ('Первый полёт человека в космос', 'show:t2:ok'),
            ('Создание первой подводной лодки', 'show:t2:no'),
            ('Первая экспедиция к Северному полюсу', 'show:t2:no'),
        ]),
    )


@router.callback_query(F.data == 'show:t2:no')
async def task2_wrong(callback: CallbackQuery) -> None:
    await callback.answer('Подсказка: Земля, единица и космонавт.', show_alert=True)


@router.callback_query(F.data == 'show:t2:ok')
async def task2_ok(callback: CallbackQuery) -> None:
    await game.db.execute("UPDATE presentation_demo_sessions SET stage='task3' WHERE user_id=?", (callback.from_user.id,))
    await callback.answer('Фрагмент восстановлен', show_alert=True)
    await callback.message.answer(
        '<b>ГАГАРИН. ПЕРВЫЙ ШАГ</b>\n\n'
        'Архив вернул событие, которое показало миру масштаб научной мысли и человеческой смелости России.',
        reply_markup=game.inline_buttons([('Проверить источник', 'show:t3')]),
    )


@router.callback_query(F.data == 'show:t3')
async def task3(callback: CallbackQuery) -> None:
    await callback.answer()
    await callback.message.answer(
        '<b>3/5 · ПРОВЕРКА ИСТОЧНИКА</b>\n\n'
        'В Архив попали три карточки. Какая выглядит наиболее надёжной?\n\n'
        '① «Так говорят в сети»\n'
        '② Документ с автором, датой и местом хранения\n'
        '③ Яркий ролик без указания источника',
        reply_markup=game.inline_buttons([
            ('①', 'show:t3:no'), ('②', 'show:t3:ok'), ('③', 'show:t3:no')
        ], columns=3),
    )


@router.callback_query(F.data == 'show:t3:no')
async def task3_wrong(callback: CallbackQuery) -> None:
    await callback.answer('Архив просит проверить происхождение информации.', show_alert=True)


@router.callback_query(F.data == 'show:t3:ok')
async def task3_ok(callback: CallbackQuery) -> None:
    await game.db.execute("UPDATE presentation_demo_sessions SET stage='live_key' WHERE user_id=?", (callback.from_user.id,))
    await callback.answer('Источник подтверждён', show_alert=True)
    await callback.message.answer(
        '<b>ИСТОЧНИК ПРИНЯТ</b>\n\n'
        'Но следующий сектор нельзя открыть только телефоном. Ключ находится в живой презентации.\n\n'
        '<b>Посмотрите на слайд и введите показанное кодовое слово.</b>\n\n'
        '<i>Во время защиты на слайде должно быть слово: ПАМЯТЬ</i>'
    )


@router.message(F.text)
async def live_key_answer(message: Message) -> None:
    await init_presentation_demo()
    row = await game.db.one('SELECT stage, attempts FROM presentation_demo_sessions WHERE user_id=?', (message.from_user.id,))
    if not row or row['stage'] != 'live_key':
        return
    answer = message.text.strip().lower().replace('ё', 'е').strip(' .,!?:;"«»')
    if answer != 'память':
        attempts = int(row['attempts']) + 1
        await game.db.execute('UPDATE presentation_demo_sessions SET attempts=? WHERE user_id=?', (attempts, message.from_user.id))
        await message.answer('<b>КЛЮЧ НЕ ПОДОШЁЛ</b>\n\nПосмотрите на выделенное слово на слайде презентации.')
        return
    await game.db.execute("UPDATE presentation_demo_sessions SET stage='task4' WHERE user_id=?", (message.from_user.id,))
    await message.answer(
        '<b>4/5 · ЖИВОЙ КЛЮЧ ПРИНЯТ</b>\n\n'
        'Офлайн-действие открыло цифровую ветвь. Именно так пять живых локаций проекта связаны с Telegram-ботом.',
        reply_markup=game.inline_buttons([('Открыть фрагмент памяти', 'show:t4')]),
    )


@router.callback_query(F.data == 'show:t4')
async def task4(callback: CallbackQuery) -> None:
    await callback.answer()
    await callback.message.answer(
        '<b>4/5 · ЛИЦА ПАМЯТИ</b>\n\n'
        'Что важнее сохранить вместе с историческим событием?',
        reply_markup=game.inline_buttons([
            ('Только дату и итог', 'show:t4:fact'),
            ('Личные письма и голоса людей', 'show:t4:human'),
            ('Только официальный символ', 'show:t4:symbol'),
        ]),
    )


@router.callback_query(F.data.startswith('show:t4:'))
async def task4_answer(callback: CallbackQuery) -> None:
    code = callback.data.rsplit(':', 1)[1]
    mapping = {
        'fact': ('truth', 'Архив сохранил точные координаты события.'),
        'human': ('human', 'История обрела лицо, голос и личную судьбу.'),
        'symbol': ('memory', 'Архив сохранил образ, который объединяет поколения.'),
    }
    if code not in mapping:
        return
    value, consequence = mapping[code]
    await game.db.execute("UPDATE presentation_demo_sessions SET second_choice=?, stage='task5' WHERE user_id=?", (value, callback.from_user.id))
    await callback.answer()
    await callback.message.answer(
        f'<b>СЛЕД СОХРАНЁН</b>\n\n{consequence}\n\nЛиния: <b>{VALUES[value]}</b>',
        reply_markup=game.inline_buttons([('Принять финальное решение', 'show:t5')]),
    )


@router.callback_query(F.data == 'show:t5')
async def task5(callback: CallbackQuery) -> None:
    await callback.answer()
    await callback.message.answer(
        '<b>5/5 · КАКИМ СТАНЕТ АРХИВ?</b>\n\n'
        'Восстановить всё сразу невозможно. Какой принцип станет главным?',
        reply_markup=game.inline_buttons([(item.title, f'show:finish:{item.code}') for item in TASK5]),
    )


@router.callback_query(F.data.startswith('show:finish:'))
async def finish(callback: CallbackQuery) -> None:
    code = callback.data.rsplit(':', 1)[1]
    final_choice = next((x for x in TASK5 if x.code == code), None)
    if not final_choice:
        return
    row = await game.db.one('SELECT first_choice, second_choice FROM presentation_demo_sessions WHERE user_id=?', (callback.from_user.id,))
    if not row:
        return
    values = [row['first_choice'], row['second_choice'], final_choice.value]
    dominant = max(set(values), key=values.count)
    title, legend = LEGENDS.get(dominant, LEGENDS['memory'])
    quote_number, quote = await quote_for(callback.from_user.id)
    await game.db.execute(
        "UPDATE presentation_demo_sessions SET stage='done', completed_at=? WHERE user_id=?",
        (utcnow(), callback.from_user.id),
    )
    await callback.answer()
    msg = await callback.message.answer('<b>Архив собирает последствия пяти решений…</b>\n\n▰▰▱▱▱ 36%')
    await asyncio.sleep(0.6)
    await msg.edit_text('<b>Сопоставляем знания, выборы и живой ключ…</b>\n\n▰▰▰▰▱ 78%')
    await asyncio.sleep(0.6)
    await msg.edit_text(
        '<b>━━━━━━━━━━━━━━━━━━\nВАША ЛЕГЕНДА СОЗДАНА\n━━━━━━━━━━━━━━━━━━</b>\n\n'
        f'<b>{title}</b>\n\n{legend}\n\n{final_choice.consequence}\n\n'
        '<b>Вы прошли 5 разных механик:</b>\n'
        '✓ ценностный выбор\n✓ эмодзи-шифр\n✓ проверка источника\n✓ живой ключ со слайда\n✓ итоговая дилемма\n\n'
        'В полном маршруте 10 решений создают до <b>59 049</b> индивидуальных путей.\n\n'
        f'<b>Ваша цитата Архива №{quote_number}</b>\n<i>«{quote}»</i>\n\n'
        '<b>Архив закрывается. Память — нет.</b>',
        reply_markup=game.inline_buttons([('↻ Пройти ещё раз', 'show:demo'), ('📝 Регистрация', 'show:register')]),
    )

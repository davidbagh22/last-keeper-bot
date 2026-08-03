from __future__ import annotations

import asyncio
from dataclasses import dataclass

from aiogram import F, Router
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

import app as game
from storage import utcnow

router = Router(name='last_keeper_presentation_demo')


class DemoFlow(StatesGroup):
    live_key = State()


@dataclass(frozen=True)
class DemoChoice:
    code: str
    title: str
    consequence: str
    value: str


FIRST_CHOICES = (
    DemoChoice('word', 'Сохранить слово', 'Вы сохранили язык — пространство, в котором поколения продолжают понимать друг друга.', 'Живое слово'),
    DemoChoice('discovery', 'Сохранить открытие', 'Вы сохранили научный импульс — способность превращать мечту в следующий шаг человечества.', 'Будущее'),
    DemoChoice('memory', 'Сохранить имя', 'Вы сохранили человеческую историю — потому что память начинается не с даты, а с человека.', 'Человеческий голос'),
)

SECOND_BRANCHES = {
    'word': (
        'Вы выбрали слово. Как передать наследие так, чтобы оно не стало музейной тишиной?',
        (
            DemoChoice('original', 'Сохранить оригинал', 'Подлинная речь эпохи осталась нетронутой.', 'Память'),
            DemoChoice('living', 'Объяснить современно', 'Смысл стал понятнее новому поколению.', 'Живое слово'),
            DemoChoice('bridge', 'Показать обе версии', 'Прошлое и настоящее вступили в диалог.', 'Связь поколений'),
        ),
    ),
    'discovery': (
        'Вы выбрали открытие. Что должно пережить время вместе с ним?',
        (
            DemoChoice('fact', 'Точный факт', 'Архив сохранил проверенные координаты события.', 'Точность'),
            DemoChoice('person', 'Историю человека', 'За достижением сохранились характер, сомнения и смелость.', 'Человеческий голос'),
            DemoChoice('future', 'Вопрос к будущему', 'Память стала приглашением продолжить начатое.', 'Будущее'),
        ),
    ),
    'memory': (
        'Вы выбрали имя. Как личная судьба должна войти в общую историю?',
        (
            DemoChoice('voice', 'Сохранить голос', 'Свидетельство осталось живым и личным.', 'Человеческий голос'),
            DemoChoice('context', 'Добавить контекст', 'Личная история стала частью большой картины.', 'Точность'),
            DemoChoice('dialogue', 'Передать молодёжи', 'Память превратилась в разговор поколений.', 'Связь поколений'),
        ),
    ),
}

LEGENDS = {
    ('word', 'original'): ('Страж подлинного слова', 'Вы бережёте язык в его исторической глубине.'),
    ('word', 'living'): ('Проводник живого слова', 'Вы помогаете наследию России говорить с новым поколением.'),
    ('word', 'bridge'): ('Создатель моста эпох', 'Вы соединяете подлинность прошлого и язык настоящего.'),
    ('discovery', 'fact'): ('Архивариус точного пути', 'Вы сохраняете достижения России через проверенный факт.'),
    ('discovery', 'person'): ('Хранитель имени', 'Для вас великое открытие невозможно отделить от человека.'),
    ('discovery', 'future'): ('Архитектор будущего', 'Вы превращаете память о достижении в импульс к новому.'),
    ('memory', 'voice'): ('Собиратель живых голосов', 'Вы возвращаете истории человеческое присутствие.'),
    ('memory', 'context'): ('Хранитель целостной памяти', 'Вы соединяете личную судьбу и историческую правду.'),
    ('memory', 'dialogue'): ('Связующий поколения', 'Вы делаете память личным разговором, а не формальным знанием.'),
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
    await target.answer(
        '<b>━━━━━━━━━━━━━━━━━━\nПОСЛЕДНИЙ ХРАНИТЕЛЬ\n━━━━━━━━━━━━━━━━━━</b>\n\n'
        'Архив памяти повреждён. Из него исчезают слова, открытия и человеческие истории России.\n\n'
        'За несколько минут вы восстановите пять фрагментов. Один из них откроется только через подсказку в живой презентации.\n\n'
        '<i>Здесь важно не только знать, но и решить, что передать дальше.</i>',
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
async def demo_start(callback: CallbackQuery, state: FSMContext) -> None:
    if await game.db.setting('demo_enabled', '1') != '1':
        await callback.answer('Демонстрация временно отключена.', show_alert=True)
        return
    await state.clear()
    await init_presentation_demo()
    await quote_for(callback.from_user.id)
    await game.db.execute(
        "UPDATE presentation_demo_sessions SET first_choice='', second_choice='', stage='choice1', attempts=0, completed_at=NULL WHERE user_id=?",
        (callback.from_user.id,),
    )
    await callback.answer()
    msg = await callback.message.answer('<b>Сканируем повреждённые сектора…</b>\n\n▰▱▱▱▱ 18%')
    await asyncio.sleep(0.55)
    await msg.edit_text('<b>Сопоставляем слова, имена и открытия…</b>\n\n▰▰▰▱▱ 57%')
    await asyncio.sleep(0.55)
    await msg.edit_text('<b>Контур памяти найден</b>\n\n▰▰▰▰▰ 100%')
    await asyncio.sleep(0.45)
    await msg.edit_text(
        '<b>ВЫ НАЗНАЧЕНЫ ПОСЛЕДНИМ ХРАНИТЕЛЕМ</b>\n\n'
        'Пять испытаний проверят культурную память, умение отличать факт от шума и готовность отвечать за сделанный выбор.',
        reply_markup=game.inline_buttons([('Начать восстановление', 'show:first')]),
    )


@router.callback_query(F.data == 'show:first')
async def demo_first(callback: CallbackQuery) -> None:
    await callback.answer()
    await callback.message.answer(
        '<b>1/5 · ЦЕНА ВЫБОРА</b>\n\n'
        'Архив успевает вывести только один фрагмент. Что вы сохраните первым?',
        reply_markup=game.inline_buttons([(item.title, f'show:first:{item.code}') for item in FIRST_CHOICES]),
    )


@router.callback_query(F.data.startswith('show:first:'))
async def demo_first_choice(callback: CallbackQuery) -> None:
    code = callback.data.rsplit(':', 1)[1]
    choice = next((item for item in FIRST_CHOICES if item.code == code), None)
    if not choice:
        return
    await game.db.execute(
        "UPDATE presentation_demo_sessions SET first_choice=?, stage='space' WHERE user_id=?",
        (code, callback.from_user.id),
    )
    await callback.answer()
    await callback.message.answer(
        f'<b>ВЫБОР СОХРАНЁН</b>\n\n{choice.consequence}\n\n'
        f'Проявившаяся линия: <b>{choice.value}</b>\n\n'
        '<i>Архив не оценивает выбор. Он запоминает его.</i>'
    )
    await callback.message.answer(
        '<b>2/5 · КОСМИЧЕСКИЙ ШИФР</b>\n\n'
        '🚀 🌍 1️⃣ 👨‍🚀 1️⃣0️⃣8️⃣ ⏱️\n\n'
        'Какое событие зашифровано?',
        reply_markup=game.inline_buttons([
            ('Первый полёт человека в космос', 'show:space:correct'),
            ('Первая высадка на Луну', 'show:space:wrong'),
            ('Запуск первого спутника', 'show:space:wrong'),
        ]),
    )


@router.callback_query(F.data == 'show:space:wrong')
async def space_wrong(callback: CallbackQuery) -> None:
    await callback.answer('Обратите внимание: человек, первый полёт и 108 минут.', show_alert=True)


@router.callback_query(F.data == 'show:space:correct')
async def space_correct(callback: CallbackQuery) -> None:
    await game.db.execute("UPDATE presentation_demo_sessions SET stage='source' WHERE user_id=?", (callback.from_user.id,))
    await callback.answer('Фрагмент восстановлен', show_alert=True)
    await callback.message.answer(
        '<b>КОСМИЧЕСКИЙ ФРАГМЕНТ ВОССТАНОВЛЕН</b>\n\n'
        '12 апреля 1961 года Юрий Гагарин на корабле «Восток-1» совершил первый в истории орбитальный полёт человека. Он продолжался 108 минут.\n\n'
        'Это был результат труда огромной научной и инженерной школы и событие, после которого космос стал частью общего будущего человечества.\n\n'
        '<i>Россия вошла в мировую историю не только как страна мечты о космосе, но и как страна, которая первой превратила эту мечту в реальность.</i>',
        reply_markup=game.inline_buttons([('Продолжить', 'show:source')]),
    )


@router.callback_query(F.data == 'show:source')
async def source_task(callback: CallbackQuery) -> None:
    await callback.answer()
    await callback.message.answer(
        '<b>3/5 · ПРОВЕРКА ИСТОЧНИКА</b>\n\n'
        'Архив нашёл три сообщения об историческом событии. Какое можно использовать как основу памяти?',
        reply_markup=game.inline_buttons([
            ('Пост без автора', 'show:source:wrong'),
            ('Ролик без ссылок', 'show:source:wrong'),
            ('Документ с автором и датой', 'show:source:correct'),
        ]),
    )


@router.callback_query(F.data == 'show:source:wrong')
async def source_wrong(callback: CallbackQuery) -> None:
    await callback.answer('Яркая подача ещё не делает источник надёжным.', show_alert=True)


@router.callback_query(F.data == 'show:source:correct')
async def source_correct(callback: CallbackQuery, state: FSMContext) -> None:
    await game.db.execute("UPDATE presentation_demo_sessions SET stage='awaiting_key' WHERE user_id=?", (callback.from_user.id,))
    await state.set_state(DemoFlow.live_key)
    await callback.answer('Источник подтверждён', show_alert=True)
    await callback.message.answer(
        '<b>ИСТОЧНИК ПОДТВЕРЖДЁН</b>\n\n'
        'Историческая память начинается с проверяемого источника: автора, даты, контекста и места хранения. Именно это отличает знание от убедительной выдумки.\n\n'
        '<b>4/5 · ЖИВОЙ ШИФР</b>\n\n'
        'Следующий ключ находится на слайде презентации. Введите пропущенное слово:\n\n'
        '<b>«У лукоморья дуб …»</b>\n\n'
        '<i>Это единственное испытание, где ответ нужно вписать вручную.</i>'
    )


@router.message(DemoFlow.live_key)
async def presentation_text_answer(message: Message, state: FSMContext) -> None:
    answer = (message.text or '').strip().lower().replace('ё', 'е').strip(' .,!?:;"«»')
    row = await game.db.one(
        'SELECT first_choice, attempts FROM presentation_demo_sessions WHERE user_id=?',
        (message.from_user.id,),
    )
    if not row:
        await state.clear()
        return
    if answer != 'зеленый':
        attempts = int(row['attempts']) + 1
        await game.db.execute('UPDATE presentation_demo_sessions SET attempts=? WHERE user_id=?', (attempts, message.from_user.id))
        hint = 'Подсказка: это цвет дуба.' if attempts == 1 else 'Посмотрите на слайд: «У лукоморья дуб …»'
        await message.answer(f'<b>КЛЮЧ НЕ ПОДОШЁЛ</b>\n\n{hint}\n\nПопробуйте ещё раз.')
        return
    await state.clear()
    first_code = row['first_choice']
    await game.db.execute("UPDATE presentation_demo_sessions SET stage='choice2' WHERE user_id=?", (message.from_user.id,))
    msg = await message.answer('<b>ЖИВОЙ КЛЮЧ ПРИНЯТ</b>\n\n▰▱▱▱▱ 21%\nСверяем ответ со слайдом…')
    await asyncio.sleep(0.55)
    await msg.edit_text('<b>ЖИВОЙ КЛЮЧ ПРИНЯТ</b>\n\n▰▰▰▱▱ 64%\nСоединяем сцену и цифровой маршрут…')
    await asyncio.sleep(0.55)
    await msg.edit_text(
        '<b>ОФЛАЙН-ФРАГМЕНТ ОТКРЫЛ ЦИФРОВУЮ ВЕТВЬ</b>\n\n'
        'Строка открывает пролог к поэме Александра Пушкина «Руслан и Людмила» и стала одним из самых узнаваемых образов русской литературы.\n\n'
        'Так работает проект: действие в живом пространстве открывает продолжение в Telegram-боте.\n\n'
        '<b>Ваш первый выбор уже изменил последнее испытание.</b>',
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
        '<b>5/5 · ЭХО ВАШЕГО ВЫБОРА</b>\n\n'
        f'{prompt}\n\n<i>Этот вопрос появился именно из вашего первого решения.</i>',
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
    await game.db.execute(
        "UPDATE presentation_demo_sessions SET second_choice=?, stage='done', completed_at=? WHERE user_id=?",
        (second_code, utcnow(), callback.from_user.id),
    )
    await callback.answer()
    msg = await callback.message.answer('<b>Архив сопоставляет решения…</b>\n\n▰▰▱▱▱ 39%')
    await asyncio.sleep(0.65)
    await msg.edit_text('<b>Формируем личную легенду…</b>\n\n▰▰▰▰▱ 82%')
    await asyncio.sleep(0.65)
    await msg.edit_text(
        '<b>━━━━━━━━━━━━━━━━━━\nЛЕГЕНДА ПОСЛЕДНЕГО ХРАНИТЕЛЯ\n━━━━━━━━━━━━━━━━━━</b>\n\n'
        f'<b>{title}</b>\n\n{legend}\n{second.consequence}\n\n'
        '<b>Вы восстановили</b>\n'
        '• факт о первом полёте человека в космос;\n'
        '• принцип проверки исторического источника;\n'
        '• строку, объединяющую поколения читателей;\n'
        '• собственный способ сохранять память.\n\n'
        '<b>Это демонстрационная ветвь.</b> В полном маршруте 10 решений создают до <b>59 049</b> индивидуальных сценариев.\n\n'
        f'<b>Ваша цитата Архива №{quote_number}</b>\n<i>«{quote}»</i>\n\n'
        '<b>Последний Хранитель — не тот, кто знает всё.</b> Это тот, кто понимает ценность наследия России и передаёт его дальше.\n\n'
        '<b>Архив закрывается. Память — нет.</b>',
        reply_markup=game.inline_buttons([('📝 Регистрация', 'show:register'), ('↻ Пройти ещё раз', 'show:demo')]),
    )

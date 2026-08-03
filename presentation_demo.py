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
class DemoChoice:
    code: str
    title: str
    consequence: str
    value: str


FIRST_CHOICES = (
    DemoChoice(
        'word',
        'Сохранить слово',
        'Вы сохранили язык — пространство, в котором поколения России продолжают понимать друг друга.',
        'Живое слово',
    ),
    DemoChoice(
        'discovery',
        'Сохранить открытие',
        'Вы сохранили научный импульс — способность России превращать мечту в следующий шаг человечества.',
        'Будущее',
    ),
    DemoChoice(
        'memory',
        'Сохранить имя',
        'Вы сохранили человеческую историю — потому что память начинается не с даты, а с человека.',
        'Человеческий голос',
    ),
)

SECOND_BRANCHES = {
    'word': (
        'Вы выбрали слово. Теперь решите, как передать наследие так, чтобы оно не стало музейной тишиной.',
        (
            DemoChoice('original', 'Сохранить оригинал', 'Подлинная речь эпохи осталась нетронутой.', 'Память'),
            DemoChoice('living', 'Объяснить современно', 'Смысл стал понятнее новому поколению.', 'Живое слово'),
            DemoChoice('bridge', 'Показать обе версии', 'Прошлое и настоящее вступили в диалог.', 'Связь поколений'),
        ),
    ),
    'discovery': (
        'Вы выбрали открытие. Теперь решите, что именно должно пережить время вместе с ним.',
        (
            DemoChoice('fact', 'Точный факт', 'Архив сохранил проверенные координаты события.', 'Точность'),
            DemoChoice('person', 'Историю человека', 'За достижением сохранились характер, сомнения и смелость.', 'Человеческий голос'),
            DemoChoice('future', 'Вопрос к будущему', 'Память стала приглашением продолжить начатое.', 'Будущее'),
        ),
    ),
    'memory': (
        'Вы выбрали имя. Теперь решите, как личная судьба должна войти в общую историю.',
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
    ('memory', 'dialogue'): ('Связующий поколения', 'Вы делаете память предметом личного разговора, а не формального знания.'),
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
        'У вас есть несколько минут, чтобы вернуть один фрагмент и увидеть, как даже небольшой выбор меняет будущее Архива.\n\n'
        '<i>Здесь не проверяют, сколько вы помните. Здесь важно, что вы решите сохранить.</i>',
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
    msg = await callback.message.answer('<b>Сканируем повреждённые сектора…</b>\n\n▰▱▱▱▱ 18%')
    await asyncio.sleep(0.6)
    await msg.edit_text('<b>Сопоставляем слова, имена и открытия…</b>\n\n▰▰▰▱▱ 57%')
    await asyncio.sleep(0.6)
    await msg.edit_text('<b>Контур памяти найден</b>\n\n▰▰▰▰▰ 100%')
    await asyncio.sleep(0.5)
    await msg.edit_text(
        '<b>ВЫ НАЗНАЧЕНЫ ПОСЛЕДНИМ ХРАНИТЕЛЕМ</b>\n\n'
        'Архив откроет пять коротких испытаний. Одно потребует не только телефона, но и живой подсказки со сцены.',
        reply_markup=game.inline_buttons([('Начать восстановление', 'show:first')]),
    )


@router.callback_query(F.data == 'show:first')
async def demo_first(callback: CallbackQuery) -> None:
    await callback.answer()
    await callback.message.answer(
        '<b>1/5 · ЧТО СОХРАНИТЬ ПЕРВЫМ?</b>\n\n'
        'Архив успевает вывести только один фрагмент. Выберите не правильный ответ, а то, без чего Россия будущего потеряет важную часть себя.',
        reply_markup=game.inline_buttons([(item.title, f'show:first:{item.code}') for item in FIRST_CHOICES]),
    )


@router.callback_query(F.data.startswith('show:first:'))
async def demo_first_choice(callback: CallbackQuery) -> None:
    code = callback.data.rsplit(':', 1)[1]
    choice = next((item for item in FIRST_CHOICES if item.code == code), None)
    if not choice:
        return
    await game.db.execute(
        "UPDATE presentation_demo_sessions SET first_choice=?, stage='emoji' WHERE user_id=?",
        (code, callback.from_user.id),
    )
    await callback.answer()
    await callback.message.answer(
        f'<b>ВЫБОР СОХРАНЁН</b>\n\n{choice.consequence}\n\n'
        f'Проявившаяся линия: <b>{choice.value}</b>\n\n'
        '<i>Архив не оценивает ваш выбор. Он запоминает его.</i>'
    )
    await asyncio.sleep(0.4)
    await callback.message.answer(
        '<b>2/5 · КУЛЬТУРНЫЙ ШИФР</b>\n\n'
        '🌊 🌳 🟢 ⛓️ 🐈 📖 🌙\n\n'
        'Какой известный фрагмент русской литературы здесь зашифрован?',
        reply_markup=game.inline_buttons([
            ('«У лукоморья дуб зелёный…»', 'show:emoji:correct'),
            ('«Мороз и солнце; день чудесный…»', 'show:emoji:wrong'),
            ('«Белеет парус одинокий…»', 'show:emoji:wrong'),
        ]),
    )


@router.callback_query(F.data == 'show:emoji:wrong')
async def emoji_wrong(callback: CallbackQuery) -> None:
    await callback.answer('Посмотрите на море, дуб, цепь и кота.', show_alert=True)


@router.callback_query(F.data == 'show:emoji:correct')
async def emoji_correct(callback: CallbackQuery) -> None:
    row = await game.db.one('SELECT first_choice FROM presentation_demo_sessions WHERE user_id=?', (callback.from_user.id,))
    if not row:
        return
    await game.db.execute("UPDATE presentation_demo_sessions SET stage='source' WHERE user_id=?", (callback.from_user.id,))
    await callback.answer('Фрагмент распознан', show_alert=True)
    await callback.message.answer(
        '<b>ФРАГМЕНТ ВОССТАНОВЛЕН</b>\n\n'
        'Эта строка открывает пролог к поэме Александра Пушкина «Руслан и Людмила». '
        'Она стала одним из самых узнаваемых образов русской литературы: в нескольких словах соединены природа, сказка, устная традиция и музыкальность русского языка.\n\n'
        '<i>Память живёт не только в датах. Иногда она начинается с одной строки, которую узнают поколения.</i>',
        reply_markup=game.inline_buttons([('Продолжить', 'show:source')]),
    )


@router.callback_query(F.data == 'show:source')
async def source_task(callback: CallbackQuery) -> None:
    await callback.answer()
    await callback.message.answer(
        '<b>3/5 · ПРОВЕРКА ИСТОЧНИКА</b>\n\n'
        'Архив нашёл три сообщения о первом полёте человека в космос. Какое можно считать надёжной основой исторической памяти?',
        reply_markup=game.inline_buttons([
            ('Пост без автора', 'show:source:wrong'),
            ('Яркий ролик без ссылок', 'show:source:wrong'),
            ('Документ с датой и автором', 'show:source:correct'),
        ]),
    )


@router.callback_query(F.data == 'show:source:wrong')
async def source_wrong(callback: CallbackQuery) -> None:
    await callback.answer('Эффектная подача ещё не делает источник проверенным.', show_alert=True)


@router.callback_query(F.data == 'show:source:correct')
async def source_correct(callback: CallbackQuery) -> None:
    await game.db.execute("UPDATE presentation_demo_sessions SET stage='awaiting_key' WHERE user_id=?", (callback.from_user.id,))
    await callback.answer('Источник подтверждён', show_alert=True)
    await callback.message.answer(
        '<b>ИСТОЧНИК ПОДТВЕРЖДЁН</b>\n\n'
        '12 апреля 1961 года Юрий Гагарин совершил первый в истории человечества орбитальный космический полёт на корабле «Восток-1». '
        'Полёт продолжался 108 минут и стал событием мирового масштаба.\n\n'
        'Его значение не только в рекорде. Советская наука, инженерная школа и мужество человека доказали: граница возможного может быть передвинута.\n\n'
        '<i>Архив сохраняет не легенду вместо факта, а факт, который сам стал легендой.</i>\n\n'
        '<b>Теперь нужен живой ключ.</b> Найдите на слайде пропущенное слово и отправьте его сообщением:\n\n'
        '<b>«У лукоморья дуб …»</b>'
    )


@router.message(F.text)
async def presentation_text_answer(message: Message) -> None:
    await init_presentation_demo()
    row = await game.db.one(
        'SELECT first_choice, stage, attempts FROM presentation_demo_sessions WHERE user_id=?',
        (message.from_user.id,),
    )
    if not row or row['stage'] != 'awaiting_key':
        return
    answer = message.text.strip().lower().replace('ё', 'е').strip(' .,!?:;"«»')
    if answer != 'зеленый':
        attempts = int(row['attempts']) + 1
        await game.db.execute(
            'UPDATE presentation_demo_sessions SET attempts=? WHERE user_id=?',
            (attempts, message.from_user.id),
        )
        hint = 'Ключ обозначает цвет.' if attempts == 1 else 'Посмотрите на слайд: «У лукоморья дуб …»'
        await message.answer(f'<b>КЛЮЧ НЕ ПОДОШЁЛ</b>\n\n{hint}\n\nПопробуйте ещё раз.')
        return
    first_code = row['first_choice']
    await game.db.execute("UPDATE presentation_demo_sessions SET stage='choice2' WHERE user_id=?", (message.from_user.id,))
    msg = await message.answer('<b>4/5 · ЖИВОЙ КЛЮЧ ПРИНЯТ</b>\n\n▰▱▱▱▱ 21%\nСверяем ответ со слайда…')
    await asyncio.sleep(0.6)
    await msg.edit_text('<b>ЖИВОЙ КЛЮЧ ПРИНЯТ</b>\n\n▰▰▰▱▱ 64%\nСоединяем сцену и цифровой маршрут…')
    await asyncio.sleep(0.6)
    await msg.edit_text(
        '<b>ОФЛАЙН-ФРАГМЕНТ ОТКРЫЛ ЦИФРОВУЮ ВЕТВЬ</b>\n\n'
        'Так работает весь проект: команда выполняет действие в живом пространстве, получает ключ и только после этого продолжает путь в Telegram-боте.\n\n'
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
        reply_markup=game.inline_buttons([
            (item.title, f'show:finish:{first_code}:{item.code}') for item in options
        ]),
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
    await asyncio.sleep(0.7)
    await msg.edit_text('<b>Формируем личную легенду…</b>\n\n▰▰▰▰▱ 82%')
    await asyncio.sleep(0.7)
    await msg.edit_text(
        '<b>━━━━━━━━━━━━━━━━━━\nЛЕГЕНДА ПОСЛЕДНЕГО ХРАНИТЕЛЯ\n━━━━━━━━━━━━━━━━━━</b>\n\n'
        f'<b>{title}</b>\n\n{legend}\n{second.consequence}\n\n'
        '<b>Что вы успели восстановить</b>\n'
        '• литературный образ Пушкина;\n'
        '• проверенный факт о полёте Гагарина;\n'
        '• связь живого пространства и цифрового маршрута;\n'
        '• собственный принцип сохранения памяти.\n\n'
        '<b>Это только демонстрационная ветвь.</b>\n'
        'В полном маршруте 10 решений формируют до <b>59 049</b> индивидуальных сценариев.\n\n'
        f'<b>Ваша цитата Архива №{quote_number}</b>\n<i>«{quote}»</i>\n\n'
        '<b>Последний Хранитель — не тот, кто знает всё.</b>\n'
        'Это тот, кто понимает ценность наследия России и принимает решение передать его дальше.\n\n'
        '<b>Архив закрывается. Память — нет.</b>',
        reply_markup=game.inline_buttons([
            ('📝 Регистрация', 'show:register'),
            ('↻ Пройти ещё раз', 'show:demo'),
        ]),
    )

from __future__ import annotations

import asyncio
from dataclasses import dataclass

from aiogram import F, Router
from aiogram.filters import Command, CommandStart
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
    DemoChoice('word', 'Сохранить русский язык', 'Слова остались живыми — и снова связали поколения.', 'Живое слово'),
    DemoChoice('discovery', 'Сохранить великое открытие', 'Будущее получило опору для следующего шага.', 'Будущее'),
    DemoChoice('culture', 'Сохранить культурный образ', 'Россия осталась узнаваемой через символы, музыку и искусство.', 'Культурный код'),
)

SECOND_BRANCHES = {
    'word': ('Архив запомнил: вы выбрали живое слово. Теперь решите, как передать его дальше.', (
        DemoChoice('original', 'Оставить только оригинал', 'Подлинность сохранена, но путь к ней стал сложнее.', 'Память'),
        DemoChoice('living', 'Дать современное объяснение', 'Смысл стал доступнее молодым читателям.', 'Живое слово'),
        DemoChoice('bridge', 'Показать обе версии рядом', 'Прошлое и настоящее вступили в диалог.', 'Связь поколений'),
    )),
    'discovery': ('Архив запомнил: вы выбрали открытие. Теперь решите, что важнее сохранить вместе с ним.', (
        DemoChoice('fact', 'Точные факты', 'История сохранила надёжные координаты.', 'Точность'),
        DemoChoice('person', 'Историю человека', 'Достижение получило лицо и голос.', 'Человеческий голос'),
        DemoChoice('future', 'Вопрос к будущему', 'Память превратилась в приглашение продолжать путь.', 'Будущее'),
    )),
    'culture': ('Архив запомнил: вы выбрали культурный образ. Теперь решите, как он должен жить дальше.', (
        DemoChoice('protect', 'Бережно сохранить форму', 'Образ остался узнаваемым и подлинным.', 'Память'),
        DemoChoice('rethink', 'Переосмыслить для молодёжи', 'Культурный код получил новую форму.', 'Смелость'),
        DemoChoice('create', 'Создать новый проект на его основе', 'Наследие стало действием, а не экспонатом.', 'Культурный код'),
    )),
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
        user_id INTEGER PRIMARY KEY, first_choice TEXT NOT NULL DEFAULT '', second_choice TEXT NOT NULL DEFAULT '',
        quote_index INTEGER NOT NULL UNIQUE, stage TEXT NOT NULL DEFAULT '', attempts INTEGER NOT NULL DEFAULT 0,
        started_at TEXT NOT NULL, completed_at TEXT)''')
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
        await game.db.execute('INSERT OR IGNORE INTO presentation_demo_sessions(user_id, quote_index, started_at) VALUES(?, ?, ?)', (user_id, index, utcnow()))
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
        'Зафиксировано исчезновение слов, открытий и культурных образов России.\n\n'
        '<b>До необратимых изменений: 03:00</b>\n\nАрхив ищет человека, готового не наблюдать, а вмешаться.',
        reply_markup=game.inline_buttons(buttons),
    )


@router.message(CommandStart())
async def presentation_start(message: Message, state: FSMContext) -> None:
    await init_presentation_demo(); await send_entry(message, message.from_user.id, state)


@router.callback_query(F.data == 'show:register')
async def begin_registration(callback: CallbackQuery, state: FSMContext) -> None:
    if await showcase_mode() not in {'mixed', 'event'}:
        await callback.answer('Регистрация сейчас отключена.', show_alert=True); return
    await callback.answer(); await state.set_state(game.Registration.consent)
    await callback.message.answer('<b>КНИГА ХРАНИТЕЛЕЙ</b>\n\nДля участия Архиву потребуются имя, возраст и Telegram ID.', reply_markup=game.inline_buttons([('Продолжить регистрацию', 'reg:yes')]))


@router.callback_query(F.data == 'show:demo')
async def demo_start(callback: CallbackQuery) -> None:
    if await game.db.setting('demo_enabled', '1') != '1':
        await callback.answer('Демонстрация временно отключена.', show_alert=True); return
    await init_presentation_demo(); await quote_for(callback.from_user.id)
    await game.db.execute("UPDATE presentation_demo_sessions SET first_choice='', second_choice='', stage='choice1', attempts=0, completed_at=NULL WHERE user_id=?", (callback.from_user.id,))
    await callback.answer()
    msg = await callback.message.answer('<b>Сканирование Архива…</b>\n\n▰▱▱▱▱ 16%')
    await asyncio.sleep(0.7); await msg.edit_text('<b>Восстанавливаем связь времён…</b>\n\n▰▰▰▱▱ 58%')
    await asyncio.sleep(0.7); await msg.edit_text('<b>Проверяем контур памяти…</b>\n\n▰▰▰▰▰ 100%')
    await asyncio.sleep(0.6); await msg.edit_text('<b>ХРАНИТЕЛЬ НАЙДЕН</b>\n\nАрхив даст вам несколько минут.\nКаждое решение изменит то, что откроется дальше.', reply_markup=game.inline_buttons([('Начать реконструкцию', 'show:first')]))


@router.callback_query(F.data == 'show:first')
async def demo_first(callback: CallbackQuery) -> None:
    await callback.answer()
    await callback.message.answer('<b>ФРАГМЕНТ №1 · ЦЕНА ВЫБОРА</b>\n\nИз повреждённого сектора можно вывести только один фрагмент. Остальные временно исчезнут из маршрута.\n\n<i>Здесь нет правильного ответа. Есть только последствия.</i>', reply_markup=game.inline_buttons([(item.title, f'show:first:{item.code}') for item in FIRST_CHOICES]))


@router.callback_query(F.data.startswith('show:first:'))
async def demo_first_choice(callback: CallbackQuery) -> None:
    code = callback.data.rsplit(':', 1)[1]
    choice = next((item for item in FIRST_CHOICES if item.code == code), None)
    if not choice: return
    await game.db.execute("UPDATE presentation_demo_sessions SET first_choice=?, stage='emoji' WHERE user_id=?", (code, callback.from_user.id))
    await callback.answer()
    await callback.message.answer(f'<b>ВЫБОР СОХРАНЁН</b>\n\n{choice.consequence}\n\nПроявившаяся линия: <b>{choice.value}</b>\n\nНо Архив не откроет следующую ветвь без проверки культурной памяти.')
    await asyncio.sleep(0.5)
    await callback.message.answer('<b>ЭМОДЗИ-ШИФР</b>\n\n🌊 🌳 🟢 ⛓️ 🐈 📖 🌙\n\nКакой известный фрагмент русской литературы здесь зашифрован?', reply_markup=game.inline_buttons([
        ('«У лукоморья дуб зелёный…»', 'show:emoji:correct'),
        ('«Мороз и солнце; день чудесный…»', 'show:emoji:wrong'),
        ('«Белеет парус одинокий…»', 'show:emoji:wrong'),
    ]))


@router.callback_query(F.data == 'show:emoji:wrong')
async def emoji_wrong(callback: CallbackQuery) -> None:
    await callback.answer('Архив не распознал фрагмент. Посмотрите на море, дуб, цепь и кота.', show_alert=True)


@router.callback_query(F.data == 'show:emoji:correct')
async def emoji_correct(callback: CallbackQuery) -> None:
    row = await game.db.one('SELECT first_choice FROM presentation_demo_sessions WHERE user_id=?', (callback.from_user.id,))
    if not row: return
    await game.db.execute("UPDATE presentation_demo_sessions SET stage='awaiting_key' WHERE user_id=?", (callback.from_user.id,))
    await callback.answer('Фрагмент распознан', show_alert=True)
    await callback.message.answer('<b>ФРАГМЕНТ РАСПОЗНАН</b>\n\nВы узнали строку Пушкина. Но цифрового знания недостаточно.\n\nСледующий ключ находится <b>в живой презентации</b>. Найдите на слайде пропущенное слово и отправьте его сообщением:\n\n<b>«У лукоморья дуб …»</b>\n\n<i>Без офлайн-подсказки цифровой маршрут не продолжится.</i>')


@router.message(F.text)
async def presentation_text_answer(message: Message) -> None:
    await init_presentation_demo()
    row = await game.db.one('SELECT first_choice, stage, attempts FROM presentation_demo_sessions WHERE user_id=?', (message.from_user.id,))
    if not row or row['stage'] != 'awaiting_key': return
    answer = message.text.strip().lower().replace('ё', 'е').strip(' .,!?:;"«»')
    if answer != 'зеленый':
        attempts = int(row['attempts']) + 1
        await game.db.execute('UPDATE presentation_demo_sessions SET attempts=? WHERE user_id=?', (attempts, message.from_user.id))
        hint = 'Подсказка: это цвет.' if attempts == 1 else 'Посмотрите на слайд: «У лукоморья дуб …»'
        await message.answer(f'<b>КЛЮЧ НЕ ПОДОШЁЛ</b>\n\n{hint}\n\nПопробуйте ещё раз.'); return
    first_code = row['first_choice']
    await game.db.execute("UPDATE presentation_demo_sessions SET stage='choice2' WHERE user_id=?", (message.from_user.id,))
    msg = await message.answer('<b>ЖИВОЙ КЛЮЧ ПРИНЯТ</b>\n\n▰▱▱▱▱ 18%\nСопоставляем ответ со слайда…')
    await asyncio.sleep(0.7); await msg.edit_text('<b>ЖИВОЙ КЛЮЧ ПРИНЯТ</b>\n\n▰▰▰▱▱ 63%\nПерестраиваем следующую ветвь…')
    await asyncio.sleep(0.7); await msg.edit_text('<b>ФРАГМЕНТ ВОССТАНОВЛЕН</b>\n\nЖивой формат открыл цифровой путь. Именно так офлайн-локации проекта соединяются с Telegram-ботом.\n\n<b>Следующая ситуация уже изменена вашим первым решением.</b>', reply_markup=game.inline_buttons([('Открыть изменённую ветвь', f'show:second:{first_code}')]))


@router.callback_query(F.data.startswith('show:second:'))
async def demo_second(callback: CallbackQuery) -> None:
    first_code = callback.data.rsplit(':', 1)[1]; branch = SECOND_BRANCHES.get(first_code)
    if not branch: return
    prompt, options = branch; await callback.answer()
    await callback.message.answer('<b>ФРАГМЕНТ №2 · ЭХО ВЫБОРА</b>\n\n' + prompt + '\n\n<i>Этот вопрос появился именно из вашего первого решения.</i>', reply_markup=game.inline_buttons([(item.title, f'show:finish:{first_code}:{item.code}') for item in options]))


@router.callback_query(F.data.startswith('show:finish:'))
async def demo_finish(callback: CallbackQuery) -> None:
    parts = callback.data.split(':')
    if len(parts) != 4: return
    first_code, second_code = parts[2], parts[3]; branch = SECOND_BRANCHES.get(first_code)
    if not branch: return
    second = next((item for item in branch[1] if item.code == second_code), None)
    if not second: return
    title, legend = LEGENDS[(first_code, second_code)]; quote_number, quote = await quote_for(callback.from_user.id)
    await game.db.execute("UPDATE presentation_demo_sessions SET second_choice=?, stage='done', completed_at=? WHERE user_id=?", (second_code, utcnow(), callback.from_user.id))
    await callback.answer(); msg = await callback.message.answer('<b>Архив анализирует последствия…</b>\n\n▰▰▱▱▱ 41%')
    await asyncio.sleep(0.8); await msg.edit_text('<b>Сопоставляем решения и ценности…</b>\n\n▰▰▰▰▱ 82%')
    await asyncio.sleep(0.8); await msg.edit_text('<b>━━━━━━━━━━━━━━━━━━\nВАША ДЕМО-ЛЕГЕНДА\n━━━━━━━━━━━━━━━━━━</b>\n\n' + f'<b>{title}</b>\n\n{legend}\n{second.consequence}\n\n' + '<b>Вы сделали 2 выбора и уже изменили сюжет.</b>\nВ полном маршруте 10 решений создают до <b>59 049</b> индивидуальных сценариев.\n\n' + f'<b>Цитата Архива №{quote_number}</b>\n<i>«{quote}»</i>\n\nРоссия раскрывается здесь не как набор дат, а как живое наследие языка, культуры, науки и человеческих судеб.\n\n<b>Архив закрывается. Память — нет.</b>', reply_markup=game.inline_buttons([('📝 Регистрация', 'show:register'), ('↻ Пройти ещё раз', 'show:demo')]))


@router.message(Command('showmode'))
async def showmode_command(message: Message) -> None:
    if await game.is_admin(message.from_user.id): await send_admin_modes(message)


@router.callback_query(F.data == 'show:admin')
async def show_admin(callback: CallbackQuery) -> None:
    if not await game.is_admin(callback.from_user.id): return
    await callback.answer(); await send_admin_modes(callback.message)


async def send_admin_modes(target: Message) -> None:
    mode = await showcase_mode(); demo = await game.db.setting('demo_enabled', '1')
    await target.answer('<b>🎬 РЕЖИМ БОТА</b>\n\n' + f'Режим: <b>{mode}</b>\nДемо: <b>{"включено" if demo == "1" else "выключено"}</b>', reply_markup=game.inline_buttons([
        ('🎤 Презентация', 'show:mode:presentation'), ('✨ Демо + регистрация', 'show:mode:mixed'),
        ('🚀 Мероприятие', 'show:mode:event'), ('🔒 Закрыть', 'show:mode:closed'),
        ('Вкл./выкл. демо', 'show:toggle-demo'), ('↻ Моё демо', 'show:restart-self'), ('♻️ Сбросить всем', 'show:restart-all'),
    ], columns=2))


@router.callback_query(F.data.startswith('show:mode:'))
async def set_show_mode(callback: CallbackQuery) -> None:
    if not await game.is_admin(callback.from_user.id): return
    mode = callback.data.rsplit(':', 1)[1]
    if mode not in {'presentation', 'mixed', 'event', 'closed'}: return
    await game.db.set_setting('showcase_mode', mode); await callback.answer(f'Режим: {mode}', show_alert=True); await send_admin_modes(callback.message)


@router.callback_query(F.data == 'show:toggle-demo')
async def toggle_demo(callback: CallbackQuery) -> None:
    if not await game.is_admin(callback.from_user.id): return
    current = await game.db.setting('demo_enabled', '1'); value = '0' if current == '1' else '1'
    await game.db.set_setting('demo_enabled', value); await callback.answer('Демо включено' if value == '1' else 'Демо выключено', show_alert=True); await send_admin_modes(callback.message)

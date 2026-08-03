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
    'word': ('Вы спасли слово. Теперь Архив просит решить, как передать его дальше.', (
        DemoChoice('original', 'Оставить только оригинал', 'Подлинность сохранена, но путь к ней стал сложнее.', 'Память'),
        DemoChoice('living', 'Дать современное объяснение', 'Смысл стал доступнее молодым читателям.', 'Живое слово'),
        DemoChoice('bridge', 'Показать обе версии рядом', 'Прошлое и настоящее вступили в диалог.', 'Связь поколений'))),
    'discovery': ('Вы спасли открытие. Теперь Архив спрашивает, что сохранить рядом с ним.', (
        DemoChoice('fact', 'Точные факты', 'История сохранила надёжные координаты.', 'Точность'),
        DemoChoice('person', 'Историю человека', 'Достижение получило лицо и голос.', 'Человеческий голос'),
        DemoChoice('future', 'Вопрос к будущему', 'Память превратилась в приглашение продолжать путь.', 'Будущее'))),
    'culture': ('Вы спасли культурный образ. Теперь решите, как он должен жить дальше.', (
        DemoChoice('protect', 'Бережно сохранить форму', 'Образ остался узнаваемым и подлинным.', 'Память'),
        DemoChoice('rethink', 'Переосмыслить для молодёжи', 'Культурный код получил новую форму.', 'Смелость'),
        DemoChoice('create', 'Создать новый проект', 'Наследие стало действием, а не экспонатом.', 'Культурный код'))),
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

QUOTE_OPENINGS = ('Любовь к России начинается', 'Память о России становится живой', 'Наследие России остаётся с нами', 'Россия звучит в будущем', 'История России не заканчивается', 'Культурная связь с Россией крепнет', 'Россия становится ближе', 'Память поколений сохраняет Россию', 'Будущее России начинается', 'Сила России раскрывается')
QUOTE_ENDINGS = ('когда мы бережно передаём её истории дальше.', 'когда её язык продолжает объединять людей.', 'когда достижения прошлого вдохновляют на новые открытия.', 'когда за великими событиями мы видим судьбы людей.', 'когда молодое поколение открывает её культуру по-своему.', 'когда память становится не обязанностью, а личным выбором.', 'когда традиция не замирает, а продолжает развиваться.', 'когда мы сохраняем правду, смысл и человеческий голос.', 'когда прошлое помогает нам ответственнее строить будущее.', 'когда каждый становится хранителем хотя бы одной истории.')


async def init_presentation_demo() -> None:
    await game.db.execute('''CREATE TABLE IF NOT EXISTS presentation_demo_sessions(
        user_id INTEGER PRIMARY KEY, first_choice TEXT NOT NULL DEFAULT '', second_choice TEXT NOT NULL DEFAULT '',
        quote_index INTEGER NOT NULL UNIQUE, stage TEXT NOT NULL DEFAULT '', attempts INTEGER NOT NULL DEFAULT 0,
        started_at TEXT NOT NULL, completed_at TEXT)''')
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
    row = await game.db.one('SELECT quote_index FROM presentation_demo_sessions WHERE user_id=?', (user_id,))
    if row:
        index = int(row['quote_index'])
    else:
        used = {int(r['quote_index']) for r in await game.db.all('SELECT quote_index FROM presentation_demo_sessions')}
        index = next((n for n in range(100) if n not in used), user_id % 100)
        await game.db.execute('INSERT OR IGNORE INTO presentation_demo_sessions(user_id,quote_index,started_at) VALUES(?,?,?)', (user_id, index, utcnow()))
    return index + 1, f'{QUOTE_OPENINGS[index // 10]} {QUOTE_ENDINGS[index % 10]}'


async def safe_photo(target: Message, kind: str, caption: str, reply_markup=None) -> None:
    try:
        await target.answer_photo(visual(kind), caption=caption, reply_markup=reply_markup)
    except Exception:
        await target.answer(caption, reply_markup=reply_markup)


async def reset_user(user_id: int) -> None:
    await quote_for(user_id)
    await game.db.execute("UPDATE presentation_demo_sessions SET first_choice='',second_choice='',stage='choice1',attempts=0,completed_at=NULL,started_at=? WHERE user_id=?", (utcnow(), user_id))


async def send_entry(target: Message, user_id: int, state: FSMContext | None = None) -> None:
    if state:
        await state.clear()
    mode, admin, user = await showcase_mode(), await game.is_admin(user_id), await game.get_user(user_id)
    if user and mode != 'presentation':
        await target.answer('<b>АРХИВ УЗНАЛ ВАС</b>\n\nВаш путь сохранён.', reply_markup=game.main_menu(admin))
        return
    if mode == 'closed' and not admin:
        await target.answer('<b>Архив временно закрыт.</b>')
        return
    buttons = []
    if await game.db.setting('demo_enabled', '1') == '1': buttons.append(('🔓 Открыть Архив', 'show:demo'))
    if mode in {'mixed', 'event'}: buttons.append(('📝 Регистрация', 'show:register'))
    if admin: buttons.append(('🎛 Режим показа', 'show:admin'))
    await safe_photo(target, 'entry', '<b>АРХИВ ПАМЯТИ</b>\n\nИз памяти исчезают слова, открытия, культурные символы и человеческие истории России.\n\n<b>До необратимых изменений: 03:00</b>\n\nАрхив ищет человека, готового вмешаться.', game.inline_buttons(buttons))


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
    await init_presentation_demo(); await reset_user(callback.from_user.id); await callback.answer()
    msg = await callback.message.answer('<b>Подключение к Архиву…</b>\n\n▓░░░░░░░░ 8%')
    for text in ('▓▓▓░░░░░░ 31%\n\nПроверяем целостность памяти…', '▓▓▓▓▓░░░░ 56%\n\nИщем утраченные связи…', '▓▓▓▓▓▓▓░░ 82%\n\nОпределяем Хранителя…'):
        await asyncio.sleep(.65); await msg.edit_text(f'<b>Подключение к Архиву…</b>\n\n{text}')
    await asyncio.sleep(.65); await msg.edit_text('<b>▓▓▓▓▓▓▓▓▓ 100%</b>\n\nСовпадение найдено.\n\n<b>Добро пожаловать, Хранитель.</b>', reply_markup=game.inline_buttons([('Начать реконструкцию', 'show:scan')]))


@router.callback_query(F.data == 'show:scan')
async def demo_scan(callback: CallbackQuery) -> None:
    await callback.answer()
    await safe_photo(callback.message, 'scan', '<b>СКАНИРОВАНИЕ АРХИВА</b>\n\nОбнаружены три повреждённых слоя:\n\n📖 слово\n🚀 открытие\n🎭 культурный образ\n\nСистема сможет удержать только один. Остальные изменятся.', game.inline_buttons([('Принять решение', 'show:first')]))


@router.callback_query(F.data == 'show:first')
async def demo_first(callback: CallbackQuery) -> None:
    await callback.answer()
    await callback.message.answer('<b>ФРАГМЕНТ №1 · ЧТО СОХРАНИТЬ?</b>\n\nЗдесь нет правильного ответа. Решение изменит следующий вопрос, финальную легенду и цену вашего пути.', reply_markup=game.inline_buttons([(x.title, f'show:first:{x.code}') for x in FIRST_CHOICES]))


@router.callback_query(F.data.startswith('show:first:'))
async def demo_first_choice(callback: CallbackQuery) -> None:
    code = callback.data.rsplit(':',1)[1]; choice = next((x for x in FIRST_CHOICES if x.code == code), None)
    if not choice: return
    await game.db.execute("UPDATE presentation_demo_sessions SET first_choice=?,stage='awaiting_key' WHERE user_id=?", (code, callback.from_user.id)); await callback.answer()
    await callback.message.answer(f'<b>ВЫБОР СОХРАНЁН</b>\n\n{choice.consequence}\n\nПроявившаяся линия: <b>{choice.value}</b>\n\nСледующий фрагмент закрыт. Ключ находится не в телефоне — он спрятан <b>на слайде презентации</b>.')
    await safe_photo(callback.message, 'riddle', '<b>ЗАГАДКА ХРАНИТЕЛЯ</b>\n\nВведите слово, завершающее строку:\n<b>«У лукоморья дуб …»</b>\n\nОтвет отправьте обычным сообщением. Без живой подсказки цифровой путь не откроется.')


@router.message(F.text)
async def presentation_text_answer(message: Message) -> None:
    await init_presentation_demo(); row = await game.db.one('SELECT first_choice,stage,attempts FROM presentation_demo_sessions WHERE user_id=?', (message.from_user.id,))
    if not row or row['stage'] != 'awaiting_key': return
    answer = message.text.strip().lower().replace('ё','е').strip(' .,!?:;"«»')
    if answer != 'зеленый':
        attempts = int(row['attempts']) + 1; await game.db.execute('UPDATE presentation_demo_sessions SET attempts=? WHERE user_id=?', (attempts, message.from_user.id))
        hint = 'Подсказка: это цвет дуба.' if attempts == 1 else 'Первая строка начинается: «У лукоморья дуб…»'
        await message.answer(f'<b>КЛЮЧ НЕ ПОДОШЁЛ</b>\n\n{hint}\n\nПопробуйте ещё раз.'); return
    first_code = row['first_choice']; await game.db.execute("UPDATE presentation_demo_sessions SET stage='choice2' WHERE user_id=?", (message.from_user.id,))
    await safe_photo(message, 'restored', '<b>КЛЮЧ ПРИНЯТ</b>\n\nЖивая подсказка открыла цифровой фрагмент. Так реальные локации проекта соединяются с Telegram-ботом.\n\nНо восстановленный фрагмент изменился из-за вашего первого решения.', game.inline_buttons([('Увидеть последствие', f'show:echo:{first_code}')]))


@router.callback_query(F.data.startswith('show:echo:'))
async def demo_echo(callback: CallbackQuery) -> None:
    code = callback.data.rsplit(':',1)[1]; await callback.answer()
    echoes = {'word':'Книги снова можно читать. Но часть старых выражений требует проводника.', 'discovery':'Формула сохранена. Но Архив почти потерял имя человека, который к ней пришёл.', 'culture':'Образ узнаваем. Но без нового прочтения он рискует стать только музейным экспонатом.'}
    await callback.message.answer(f'<b>ЭХО ВЫБОРА</b>\n\n{echoes.get(code, "Архив изменился.")}\n\n<i>Эффект бабочки уже проявился: следующий выбор возник как последствие предыдущего.</i>', reply_markup=game.inline_buttons([('Продолжить ветвь', f'show:second:{code}')]))


@router.callback_query(F.data.startswith('show:second:'))
async def demo_second(callback: CallbackQuery) -> None:
    first = callback.data.rsplit(':',1)[1]; branch = SECOND_BRANCHES.get(first)
    if not branch: return
    await callback.answer(); prompt, options = branch
    await callback.message.answer(f'<b>ФРАГМЕНТ №2 · ЦЕНА СОХРАНЕНИЯ</b>\n\n{prompt}\n\n<i>Этот вопрос существует только из-за вашего первого решения.</i>', reply_markup=game.inline_buttons([(x.title, f'show:finish:{first}:{x.code}') for x in options]))


@router.callback_query(F.data.startswith('show:finish:'))
async def demo_finish(callback: CallbackQuery) -> None:
    parts = callback.data.split(':')
    if len(parts) != 4: return
    first, second_code = parts[2], parts[3]; branch = SECOND_BRANCHES.get(first)
    if not branch: return
    second = next((x for x in branch[1] if x.code == second_code), None)
    if not second: return
    title, legend = LEGENDS[(first, second_code)]; number, quote = await quote_for(callback.from_user.id)
    await game.db.execute("UPDATE presentation_demo_sessions SET second_choice=?,stage='done',completed_at=? WHERE user_id=?", (second_code, utcnow(), callback.from_user.id)); await callback.answer()
    msg = await callback.message.answer('<b>Архив сопоставляет решения…</b>\n\n▓▓░░░░░░░ 19%')
    for text in ('▓▓▓▓░░░░░ 44%\n\nВосстанавливаем причинно-следственные связи…','▓▓▓▓▓▓░░░ 67%\n\nФормируем личную легенду…','▓▓▓▓▓▓▓▓░ 91%\n\nЗакрепляем цитату Хранителя…'):
        await asyncio.sleep(.7); await msg.edit_text(f'<b>Архив сопоставляет решения…</b>\n\n{text}')
    await asyncio.sleep(.7)
    await safe_photo(callback.message, 'final', f'<b>ДЕМО-ЛЕГЕНДА СОЗДАНА</b>\n\n<b>{title}</b>\n\n{legend}\n\n{second.consequence}\n\n<b>2 решения создали отдельную ветвь.</b> В полном маршруте 10 решений формируют до <b>59 049</b> индивидуальных сценариев.\n\n<b>Ваша цитата Архива №{number}</b>\n<i>«{quote}»</i>\n\n<b>Архив закрывается. Память — нет.</b>', game.inline_buttons([('📝 Регистрация', 'show:register'), ('↻ Пройти ещё раз', 'show:demo')]))


@router.message(Command('showmode'))
async def showmode_command(message: Message) -> None:
    if await game.is_admin(message.from_user.id): await send_admin_modes(message)


@router.callback_query(F.data == 'show:admin')
async def show_admin(callback: CallbackQuery) -> None:
    if not await game.is_admin(callback.from_user.id): return
    await callback.answer(); await send_admin_modes(callback.message)


async def send_admin_modes(target: Message) -> None:
    mode, demo = await showcase_mode(), await game.db.setting('demo_enabled','1')
    await target.answer(f'<b>🎬 РЕЖИМ БОТА</b>\n\nРежим: <b>{mode}</b>\nДемо: <b>{"включено" if demo=="1" else "выключено"}</b>', reply_markup=game.inline_buttons([
        ('🎤 Презентация','show:mode:presentation'),('✨ Демо + регистрация','show:mode:mixed'),('🚀 Мероприятие','show:mode:event'),('🔒 Закрыть','show:mode:closed'),('Вкл./выкл. демо','show:toggle-demo'),('↻ Перезапустить моё демо','show:restart-me'),('♻️ Сбросить демо всем','show:restart-all')], columns=2))


@router.callback_query(F.data.startswith('show:mode:'))
async def set_show_mode(callback: CallbackQuery) -> None:
    if not await game.is_admin(callback.from_user.id): return
    mode = callback.data.rsplit(':',1)[1]
    if mode not in {'presentation','mixed','event','closed'}: return
    await game.db.set_setting('showcase_mode',mode); await callback.answer(f'Режим: {mode}',show_alert=True); await send_admin_modes(callback.message)


@router.callback_query(F.data == 'show:toggle-demo')
async def toggle_demo(callback: CallbackQuery) -> None:
    if not await game.is_admin(callback.from_user.id): return
    current = await game.db.setting('demo_enabled','1'); value = '0' if current=='1' else '1'; await game.db.set_setting('demo_enabled',value)
    await callback.answer('Демо включено' if value=='1' else 'Демо выключено',show_alert=True); await send_admin_modes(callback.message)


@router.callback_query(F.data == 'show:restart-me')
async def restart_me(callback: CallbackQuery) -> None:
    if not await game.is_admin(callback.from_user.id): return
    await reset_user(callback.from_user.id); await callback.answer('Ваше демо перезапущено', show_alert=True)
    await callback.message.answer('Демо сброшено. Нажмите кнопку ниже.', reply_markup=game.inline_buttons([('🔓 Начать заново','show:demo')]))


@router.callback_query(F.data == 'show:restart-all')
async def restart_all(callback: CallbackQuery) -> None:
    if not await game.is_admin(callback.from_user.id): return
    await game.db.execute("UPDATE presentation_demo_sessions SET first_choice='',second_choice='',stage='',attempts=0,completed_at=NULL")
    await callback.answer('Демо перезапущено для всех', show_alert=True)
    await callback.message.answer('<b>Все презентационные сессии сброшены.</b>\n\nУчастники могут снова открыть Архив через /start.')

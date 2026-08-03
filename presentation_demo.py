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
    DemoChoice('original', 'Сохранить оригинал без изменений', 'Вы сохранили подлинный язык. Но доступ к нему потребует проводника.', 'Память'),
    DemoChoice('living', 'Перевести на живой язык', 'Текст снова заговорил с молодыми читателями. Но форма начала меняться.', 'Живое слово'),
    DemoChoice('bridge', 'Показать обе версии рядом', 'Прошлое и настоящее вступили в диалог. Архив стал сложнее — и честнее.', 'Связь поколений'),
)

SECOND_BRANCHES = {
    'original': (
        'Архив запомнил: вы защищаете подлинность.\n\nТеперь найден повреждённый дневник молодого инженера, чьи идеи позже приблизят космическую эру. Что нельзя потерять?',
        (
            DemoChoice('idea', 'Его главную идею', 'Будущее сохранило направление, но почти забыло человека.', 'Будущее'),
            DemoChoice('person', 'Историю самого человека', 'Открытие получило лицо, голос и человеческую цену.', 'Человеческий голос'),
            DemoChoice('errors', 'Ошибки и путь к открытию', 'Архив сохранил не только победу, но и честную дорогу к ней.', 'Точность'),
        ),
    ),
    'living': (
        'Архив запомнил: для вас наследие должно быть понятным.\n\nПеред вами запись о первом полёте Гагарина. Как рассказать о ней новому поколению?',
        (
            DemoChoice('fact', 'Через точные факты', 'Подвиг сохранил ясные координаты и историческую опору.', 'Точность'),
            DemoChoice('emotion', 'Через чувство первого шага', 'Космос стал личным переживанием, а не далёкой датой.', 'Смелость'),
            DemoChoice('dialogue', 'Через вопрос о нашем будущем', 'Память о полёте превратилась в приглашение продолжать путь.', 'Будущее'),
        ),
    ),
    'bridge': (
        'Архив запомнил: вы ищете мост между эпохами.\n\nВ нём осталась одна свободная страница. Чем вы её заполните?',
        (
            DemoChoice('source', 'Подлинным документом', 'Будущие поколения получили надёжную точку отсчёта.', 'Память'),
            DemoChoice('voice', 'Личной историей современника', 'История сохранила человеческую интонацию.', 'Человеческий голос'),
            DemoChoice('project', 'Идеей нового культурного проекта', 'Наследие перестало быть завершённым и стало действием.', 'Культурный код'),
        ),
    ),
}

LEGENDS = {
    ('original', 'idea'): ('Страж исходного замысла', 'Вы защищаете основу и позволяете будущему продолжить мысль.'),
    ('original', 'person'): ('Хранитель имени', 'Для вас великое достижение невозможно отделить от человека.'),
    ('original', 'errors'): ('Архивариус честного пути', 'Вы сохраняете не только вершину, но и дорогу, которая к ней привела.'),
    ('living', 'fact'): ('Проводник ясной памяти', 'Вы делаете наследие понятным, не лишая его точности.'),
    ('living', 'emotion'): ('Хранитель первого шага', 'Вы возвращаете истории чувство, способное вдохновить на действие.'),
    ('living', 'dialogue'): ('Архитектор будущего', 'Вы превращаете достижения России в вопрос: что создадим мы?'),
    ('bridge', 'source'): ('Строитель опоры', 'Вы соединяете эпохи через подлинный документ и проверенный смысл.'),
    ('bridge', 'voice'): ('Собиратель живых голосов', 'Вы создаёте мост между большой историей и личной памятью.'),
    ('bridge', 'project'): ('Продолжатель культурного кода', 'Для вас любовь к наследию проявляется в новом созидательном действии.'),
}

QUOTE_OPENINGS = (
    'Любовь к России начинается',
    'Память о России становится живой',
    'Наследие России остаётся с нами',
    'Россия звучит в будущем',
    'История России не заканчивается',
    'Культурная связь с Россией крепнет',
    'Россия становится ближе',
    'Память поколений сохраняет Россию',
    'Будущее России начинается',
    'Сила России раскрывается',
)
QUOTE_ENDINGS = (
    'когда мы бережно передаём её истории дальше.',
    'когда её язык продолжает объединять людей.',
    'когда достижения прошлого вдохновляют на новые открытия.',
    'когда за великими событиями мы видим судьбы людей.',
    'когда молодое поколение открывает её культуру по-своему.',
    'когда память становится не обязанностью, а личным выбором.',
    'когда традиция не замирает, а продолжает развиваться.',
    'когда мы сохраняем правду, смысл и человеческий голос.',
    'когда прошлое помогает нам ответственнее строить будущее.',
    'когда каждый становится хранителем хотя бы одной истории.',
)


async def init_presentation_demo() -> None:
    await game.db.execute('''CREATE TABLE IF NOT EXISTS presentation_demo_sessions(
        user_id INTEGER PRIMARY KEY,
        first_choice TEXT NOT NULL DEFAULT '',
        second_choice TEXT NOT NULL DEFAULT '',
        quote_index INTEGER NOT NULL UNIQUE,
        started_at TEXT NOT NULL,
        completed_at TEXT
    )''')
    for key, value in (
        ('showcase_mode', 'mixed'),
        ('demo_enabled', '1'),
    ):
        current = await game.db.setting(key, '')
        if not current:
            await game.db.set_setting(key, value)


async def showcase_mode() -> str:
    return await game.db.setting('showcase_mode', 'mixed')


async def quote_for(user_id: int) -> tuple[int, str]:
    row = await game.db.one('SELECT quote_index FROM presentation_demo_sessions WHERE user_id = ?', (user_id,))
    if row:
        index = int(row['quote_index'])
    else:
        used_rows = await game.db.all('SELECT quote_index FROM presentation_demo_sessions')
        used = {int(item['quote_index']) for item in used_rows}
        index = next((number for number in range(100) if number not in used), user_id % 100)
        try:
            await game.db.execute(
                '''INSERT INTO presentation_demo_sessions(user_id, quote_index, started_at)
                   VALUES(?, ?, ?)''',
                (user_id, index, utcnow()),
            )
        except Exception:
            row = await game.db.one('SELECT quote_index FROM presentation_demo_sessions WHERE user_id = ?', (user_id,))
            index = int(row['quote_index']) if row else user_id % 100
    opening = QUOTE_OPENINGS[index // 10]
    ending = QUOTE_ENDINGS[index % 10]
    return index + 1, f'{opening} {ending}'


async def send_entry(target: Message, user_id: int, state: FSMContext | None = None) -> None:
    if state:
        await state.clear()
    mode = await showcase_mode()
    user = await game.get_user(user_id)
    admin = await game.is_admin(user_id)

    if user and mode != 'presentation':
        role = 'капитан' if user['role'] == 'captain' else 'Хранитель'
        await target.answer(
            '<b>АРХИВ УЗНАЛ ВАС</b>\n\n'
            f'{role}: <b>{game.escape(user["full_name"])}</b>\n'
            f'Команда: <b>{game.escape(user["team"])}</b>\n\n'
            'Ваш путь сохранён. Продолжайте с того места, где остановились.',
            reply_markup=game.main_menu(admin),
        )
        return

    if mode == 'closed' and not admin:
        await target.answer('<b>Архив временно закрыт.</b>\n\nДоступ откроет главный Архивариус.')
        return

    buttons: list[tuple[str, str]] = []
    if await game.db.setting('demo_enabled', '1') == '1':
        buttons.append(('🔓 Открыть Архив', 'show:demo'))
    if mode in {'mixed', 'event'}:
        buttons.append(('📝 Регистрация', 'show:register'))
    if admin:
        buttons.append(('🎛 Режим показа', 'show:admin'))

    await target.answer(
        '<b>━━━━━━━━━━━━━━━━━━\n'
        'АРХИВ ПАМЯТИ\n'
        '━━━━━━━━━━━━━━━━━━</b>\n\n'
        'Зафиксировано повреждение.\n\n'
        'Из памяти начинают исчезать слова, открытия, культурные символы и человеческие истории России.\n\n'
        '<b>До необратимых изменений: 01:59</b>\n\n'
        'Архив ищет человека, готового вмешаться.',
        reply_markup=game.inline_buttons(buttons),
    )


@router.message(CommandStart())
async def presentation_start(message: Message, state: FSMContext) -> None:
    await init_presentation_demo()
    await send_entry(message, message.from_user.id, state)


@router.callback_query(F.data == 'show:register')
async def begin_registration(callback: CallbackQuery, state: FSMContext) -> None:
    mode = await showcase_mode()
    if mode not in {'mixed', 'event'}:
        await callback.answer('Регистрация сейчас отключена Архивариусом.', show_alert=True)
        return
    await callback.answer()
    await state.set_state(game.Registration.consent)
    await callback.message.edit_text(
        '<b>КНИГА ХРАНИТЕЛЕЙ</b>\n\n'
        'Для участия Архиву потребуются имя, возраст и Telegram ID. Данные используются только для организации проекта.',
        reply_markup=game.inline_buttons([('Продолжить регистрацию', 'reg:yes'), ('Вернуться', 'show:home')]),
    )


@router.callback_query(F.data == 'show:home')
async def show_home(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    await send_entry(callback.message, callback.from_user.id, state)


@router.callback_query(F.data == 'show:demo')
async def demo_start(callback: CallbackQuery) -> None:
    if await game.db.setting('demo_enabled', '1') != '1':
        await callback.answer('Демонстрация временно отключена.', show_alert=True)
        return
    await init_presentation_demo()
    await quote_for(callback.from_user.id)
    await callback.answer()
    await callback.message.edit_text('<b>Соединение с Архивом…</b>\n\n▓░░░░░░░░ 12%')
    await asyncio.sleep(0.7)
    await callback.message.edit_text('<b>Соединение с Архивом…</b>\n\n▓▓▓▓░░░░░ 43%')
    await asyncio.sleep(0.7)
    await callback.message.edit_text('<b>Соединение с Архивом…</b>\n\n▓▓▓▓▓▓▓░░ 78%')
    await asyncio.sleep(0.7)
    await callback.message.edit_text(
        '<b>▓▓▓▓▓▓▓▓▓ 100%</b>\n\n'
        'Совпадение найдено.\n\n'
        '<b>Добро пожаловать, Хранитель.</b>',
        reply_markup=game.inline_buttons([('Начать реконструкцию', 'show:first')]),
    )


@router.callback_query(F.data == 'show:first')
async def demo_first(callback: CallbackQuery) -> None:
    await callback.answer()
    await callback.message.edit_text(
        '<b>ФРАГМЕНТ №1 · КОД СЛОВА</b>\n\n'
        '2036 год. Последний полный экземпляр «Капитанской дочки» повреждён.\n\n'
        'Архив может сохранить произведение только одним способом. Что вы выберете?\n\n'
        '<i>Здесь нет правильного ответа. Есть только последствия.</i>',
        reply_markup=game.inline_buttons([(item.title, f'show:first:{item.code}') for item in FIRST_CHOICES]),
    )


@router.callback_query(F.data.startswith('show:first:'))
async def demo_first_choice(callback: CallbackQuery) -> None:
    code = callback.data.rsplit(':', 1)[1]
    choice = next((item for item in FIRST_CHOICES if item.code == code), None)
    if not choice:
        return
    await game.db.execute(
        'UPDATE presentation_demo_sessions SET first_choice = ? WHERE user_id = ?',
        (code, callback.from_user.id),
    )
    await callback.answer()
    await callback.message.edit_text(
        '<b>ВЫБОР СОХРАНЁН</b>\n\n'
        f'{game.escape(choice.consequence)}\n\n'
        f'Проявившаяся линия: <b>{choice.value}</b>\n\n'
        '<i>Архив перестраивает следующее событие с учётом вашего решения.</i>',
        reply_markup=game.inline_buttons([('Увидеть последствие', f'show:second:{code}')]),
    )


@router.callback_query(F.data.startswith('show:second:'))
async def demo_second(callback: CallbackQuery) -> None:
    first_code = callback.data.rsplit(':', 1)[1]
    branch = SECOND_BRANCHES.get(first_code)
    if not branch:
        return
    prompt, options = branch
    await callback.answer()
    await callback.message.edit_text(
        '<b>ФРАГМЕНТ №2 · ПЕРВЫЙ ШАГ</b>\n\n'
        f'{prompt}\n\n'
        '<i>Второй вопрос уже изменён вашим первым выбором.</i>',
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
        '''UPDATE presentation_demo_sessions
           SET second_choice = ?, completed_at = ? WHERE user_id = ?''',
        (second_code, utcnow(), callback.from_user.id),
    )
    await callback.answer()
    await callback.message.edit_text('<b>Архив анализирует последствия…</b>\n\n▓▓▓▓░░░░░ 41%')
    await asyncio.sleep(0.8)
    await callback.message.edit_text('<b>Архив анализирует последствия…</b>\n\n▓▓▓▓▓▓▓░░ 78%')
    await asyncio.sleep(0.8)
    await callback.message.edit_text(
        '<b>━━━━━━━━━━━━━━━━━━\n'
        'ДЕМО-ЛЕГЕНДА СОЗДАНА\n'
        '━━━━━━━━━━━━━━━━━━</b>\n\n'
        f'<b>{title}</b>\n\n{legend}\n\n'
        f'{second.consequence}\n\n'
        '<b>2 решения уже создали отдельную ветвь истории.</b>\n'
        'В полном маршруте 10 решений формируют до <b>59 049</b> индивидуальных сценариев.\n\n'
        f'<b>Ваша цитата Архива №{quote_number}</b>\n'
        f'<i>«{quote}»</i>\n\n'
        'Память невозможно сохранить, наблюдая. Её сохраняют участием.',
        reply_markup=game.inline_buttons([('📝 Перейти к регистрации', 'show:register'), ('↻ Пройти ещё раз', 'show:demo')]),
    )


@router.message(Command('showmode'))
async def showmode_command(message: Message) -> None:
    if not await game.is_admin(message.from_user.id):
        return
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
        f'Текущий режим: <b>{mode}</b>\n'
        f'Демо: <b>{"включено" if demo == "1" else "выключено"}</b>\n\n'
        '<b>Презентация</b> — доступно только двухминутное демо.\n'
        '<b>Смешанный</b> — демо и регистрация.\n'
        '<b>Мероприятие</b> — регистрация и основной маршрут.\n'
        '<b>Закрыт</b> — доступ только администраторам.',
        reply_markup=game.inline_buttons([
            ('🎤 Презентация', 'show:mode:presentation'),
            ('✨ Демо + регистрация', 'show:mode:mixed'),
            ('🚀 Мероприятие', 'show:mode:event'),
            ('🔒 Закрыть бот', 'show:mode:closed'),
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
    await game.db.log(callback.from_user.id, 'set_showcase_mode', {'mode': mode})
    await callback.answer(f'Режим: {mode}', show_alert=True)
    await send_admin_modes(callback.message)


@router.callback_query(F.data == 'show:toggle-demo')
async def toggle_demo(callback: CallbackQuery) -> None:
    if not await game.is_admin(callback.from_user.id):
        return
    current = await game.db.setting('demo_enabled', '1')
    value = '0' if current == '1' else '1'
    await game.db.set_setting('demo_enabled', value)
    await game.db.log(callback.from_user.id, 'toggle_demo', {'enabled': value})
    await callback.answer('Демо включено' if value == '1' else 'Демо выключено', show_alert=True)
    await send_admin_modes(callback.message)

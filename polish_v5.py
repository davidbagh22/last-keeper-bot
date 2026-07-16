from __future__ import annotations

from collections import Counter

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message

import app as game
from game_data import TEAM_COLORS, final_archetype
from quest_common import completed_locations, is_assigned, progress_bar

router = Router(name='last_keeper_polish_v5')

OPEN_SPACES_TEXT = (
    '<b>Открытые пространства Архива</b>\n'
    '<i>Работают в течение всего дня · 10:00–18:00</i>\n\n'
    '📖 <b>«Пушкин. Код слова»</b>\n'
    'Литературная фотозона · Фойе, 1 этаж\n\n'
    '👑 <b>«Екатерина Великая. Кабинет эпохи»</b>\n'
    'Историческая фотозона · Фойе выставочного зала, 2 этаж\n\n'
    '🎨 <b>«Культурный код России»</b>\n'
    'Фотовыставка о традициях, искусстве, архитектуре и символах России · '
    'Фойе выставочного зала, 2 этаж\n\n'
    '🚀 <b>«Гагарин. Первый шаг»</b>\n'
    'Космическая фотозона о первом полёте человека в космос · Фойе кинозала, 3 этаж\n\n'
    '🕯 <b>«Лица памяти»</b>\n'
    'Фотовыставка о Великой Отечественной войне, подвиге и памяти поколений · '
    'Фойе, −1 этаж\n\n'
    '🥽 <b>VR-зона «Русская изба»</b>\n'
    'Традиционный русский быт, семейные обычаи и народная культура · Лофт №3, −1 этаж\n\n'
    '🕰 <b>VR-зона «От Ивана IV до современной России»</b>\n'
    'Путешествие по ключевым историческим эпохам России · Фойе, 3 этаж\n\n'
    '<b>Задача команды</b>\n'
    'Выберите пространство, после которого возник новый вопрос или неожиданная связь. '
    'В Архиве важен не снимок сам по себе, а мысль, которую вы унесёте дальше.'
)


@router.callback_query(F.data == 'program:spaces')
async def open_spaces(callback: CallbackQuery) -> None:
    await callback.answer()
    await callback.message.answer(
        OPEN_SPACES_TEXT,
        reply_markup=game.inline_buttons([
            ('🗺 Мой маршрут', 'tq:route'),
            ('📍 Текущая точка', 'tq:current'),
        ]),
    )


async def send_compact_admin(target: Message, user_id: int) -> None:
    if not await game.is_admin(user_id):
        await target.answer('🔒 Панель доступна только назначенным администраторам.')
        return

    total = await game.db.one('SELECT COUNT(*) AS total FROM users')
    waiting = await game.db.one("SELECT COUNT(*) AS total FROM users WHERE team = '' OR status = 'waiting_team'")
    requests = await game.db.one("SELECT COUNT(*) AS total FROM support_requests WHERE status = 'open'")
    rows = await game.db.all("SELECT team, COUNT(*) AS total FROM users WHERE team <> '' GROUP BY team")
    counts = Counter({row['team']: int(row['total']) for row in rows})

    teams_line = ' · '.join(f'{team}: {counts[team]}' for team in TEAM_COLORS)
    buttons = [
        ('🎛 Команды', 'ac:home'),
        ('🎨 Распределить', 'tq:admin:queue'),
        ('📊 Прогресс', 'tq:admin:teams'),
        ('💬 Вопросы', 'admin:support'),
        ('📣 Рассылка', 'admin:broadcast'),
        ('📤 Экспорт', 'admin:export'),
        ('🦋 Финал', 'admin:final'),
        ('⚙️ Ещё', 'tq:admin:legacy'),
    ]
    if game.is_superadmin(user_id):
        buttons.insert(2, ('🎭 Ведущие', 'lh:admin:list'))
        buttons.insert(3, ('👤 Доступы', 'access:admins'))

    await target.answer(
        '<b>🛡 ПАНЕЛЬ УПРАВЛЕНИЯ</b>\n\n'
        f'👥 Участников: <b>{total["total"]}</b>\n'
        f'⏳ Ждут команду: <b>{waiting["total"]}</b>\n'
        f'💬 Новых вопросов: <b>{requests["total"]}</b>\n\n'
        f'<b>Команды</b>\n{teams_line}\n\n'
        '<i>Кнопки сокращены: полное пояснение открывается после выбора раздела.</i>',
        reply_markup=game.inline_buttons(buttons, columns=2),
    )


@router.message(Command('admin'))
@router.message(F.text == '🛡 Управление проектом')
async def compact_admin(message: Message) -> None:
    await send_compact_admin(message, message.from_user.id)


async def send_final(target: Message, user_id: int) -> None:
    user = await game.get_user(user_id)
    if not is_assigned(user):
        await target.answer('Финал откроется после назначения команды.')
        return

    final_open = await game.db.setting('final_open', '0')
    done = await completed_locations(user)
    choices = await game.team_choices(user['event_date'], user['team'])

    if final_open != '1':
        await target.answer(
            '<b>◻️ Эффект бабочки пока закрыт</b>\n\n'
            f'Маршрут команды: {progress_bar(len(done), 5)}  {len(done)}/5\n'
            f'Решения команды: {progress_bar(len(choices), 4)}  {len(choices)}/4\n\n'
            'На первых этапах Архив не показывает скрытые последствия — иначе выбор перестанет быть честным. '
            'Финальная версия откроется только после завершения маршрута и подтверждения главного Архивариуса.',
            reply_markup=game.inline_buttons([
                ('📍 Текущая точка', 'tq:current'),
                ('📜 Прогресс', 'tq:progress'),
            ]),
        )
        return

    if len(done) < 5 or len(choices) < 4:
        await target.answer(
            '<b>Архивариус открыл финальный зал, но контур ещё не собран.</b>\n\n'
            f'Маршрут: {len(done)}/5 · решения: {len(choices)}/4.\n'
            'Завершите недостающие этапы — только после этого появится итог команды.'
        )
        return

    title, text, _ = final_archetype(await game.team_parameters(user['event_date'], user['team']))
    await target.answer(
        '<b>🦋 ЭФФЕКТ БАБОЧКИ ОТКРЫТ</b>\n\n'
        f'Версия Архива команды «{game.escape(user["team"])}»: <b>«{game.escape(title)}»</b>\n\n'
        f'{game.escape(text)}\n\n'
        '<i>Этот результат сложился из решений команды на четырёх живых локациях.</i>'
    )


@router.message(Command('mission'))
@router.message(F.text.in_({'◻️ Эффект бабочки', '🦋 Состояние Архива', '🦋 Эффект бабочки'}))
async def final_message(message: Message) -> None:
    await send_final(message, message.from_user.id)


@router.callback_query(F.data.in_({'v4:mission', 'progress:final'}))
async def final_callback(callback: CallbackQuery) -> None:
    await callback.answer()
    await send_final(callback.message, callback.from_user.id)

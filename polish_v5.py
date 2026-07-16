from __future__ import annotations

from collections import Counter

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message

import app as game
import production_v6
from game_data import TEAM_COLORS

router = Router(name='last_keeper_polish_v5')
router.include_router(production_v6.router)

OPEN_SPACES_TEXT = (
    '<b>Открытые пространства Архива</b>\n'
    '<i>Работают в течение всего дня · 10:00–18:00</i>\n\n'
    '📖 <b>«Пушкин. Код слова»</b>\nЛитературная фотозона · Фойе, 1 этаж\n\n'
    '👑 <b>«Екатерина Великая. Кабинет эпохи»</b>\nИсторическая фотозона · Фойе выставочного зала, 2 этаж\n\n'
    '🎨 <b>«Культурный код России»</b>\nФотовыставка о традициях, искусстве, архитектуре и символах России · Фойе выставочного зала, 2 этаж\n\n'
    '🚀 <b>«Гагарин. Первый шаг»</b>\nКосмическая фотозона о первом полёте человека в космос · Фойе кинозала, 3 этаж\n\n'
    '🕯 <b>«Лица памяти»</b>\nФотовыставка о Великой Отечественной войне, подвиге и памяти поколений · Фойе, −1 этаж\n\n'
    '🥽 <b>VR-зона «Русская изба»</b>\nТрадиционный русский быт, семейные обычаи и народная культура · Лофт №3, −1 этаж\n\n'
    '🕰 <b>VR-зона «От Ивана IV до современной России»</b>\nПутешествие по ключевым историческим эпохам России · Фойе, 3 этаж\n\n'
    '<b>Задача команды</b>\nВыберите пространство, после которого возник новый вопрос или неожиданная связь.'
)


@router.callback_query(F.data == 'program:spaces')
async def open_spaces(callback: CallbackQuery) -> None:
    await callback.answer()
    await callback.message.answer(
        OPEN_SPACES_TEXT,
        reply_markup=game.inline_buttons([
            ('✍️ Сохранить вопрос', 'v6:spaces'),
            ('🗺 Маршрут', 'tq:route'),
            ('📍 Сейчас', 'tq:current'),
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
        ('🎛 Команды', 'ac:home'), ('🎨 Распределить', 'tq:admin:queue'),
        ('📊 Прогресс', 'tq:admin:teams'), ('💬 Вопросы', 'admin:support'),
        ('📣 Рассылка', 'admin:broadcast'), ('📤 Экспорт', 'admin:export'),
        ('🦋 Финал', 'admin:final'), ('🚨 Аварийно', 'v6:emergency'),
        ('📈 Статистика', 'v6:stats'), ('⚙️ Ещё', 'tq:admin:legacy'),
    ]
    if game.is_superadmin(user_id):
        buttons.insert(2, ('🎭 Ведущие', 'lh:admin:list'))
        buttons.insert(3, ('👤 Доступы', 'access:admins'))
    await target.answer(
        '<b>🛡 ПАНЕЛЬ УПРАВЛЕНИЯ</b>\n\n'
        f'👥 Участников: <b>{total["total"]}</b>\n'
        f'⏳ Ждут команду: <b>{waiting["total"]}</b>\n'
        f'💬 Новых вопросов: <b>{requests["total"]}</b>\n\n'
        f'<b>Команды</b>\n{teams_line}',
        reply_markup=game.inline_buttons(buttons, columns=2),
    )


@router.message(Command('admin'))
@router.message(F.text == '🛡 Управление проектом')
async def compact_admin(message: Message) -> None:
    await send_compact_admin(message, message.from_user.id)


@router.message(Command('mission'))
@router.message(F.text.in_({'◻️ Эффект бабочки', '🦋 Состояние Архива', '🦋 Эффект бабочки'}))
async def final_message(message: Message) -> None:
    await production_v6.final_report(message, message.from_user.id)


@router.callback_query(F.data.in_({'v4:mission', 'progress:final'}))
async def final_callback(callback: CallbackQuery) -> None:
    await callback.answer()
    await production_v6.final_report(callback.message, callback.from_user.id)

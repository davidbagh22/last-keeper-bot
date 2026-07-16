from __future__ import annotations

from collections import Counter

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import Message

import app as game
from game_data import TEAM_COLORS
from ui_text import divider, section, stat

router = Router(name='last_keeper_admin_home')


@router.message(F.text == '🛡 Управление проектом')
@router.message(Command('admin'))
async def admin_home(message: Message) -> None:
    if not await game.is_admin(message.from_user.id):
        await message.answer(
            '🔒 <b>Панель Архивариуса закрыта</b>\n\n'
            'Доступ есть только у назначенных администраторов проекта.'
        )
        return

    total = await game.db.one('SELECT COUNT(*) AS total FROM users')
    waiting = await game.db.one(
        "SELECT COUNT(*) AS total FROM users WHERE team = '' OR status = 'waiting_team'"
    )
    rows = await game.db.all(
        "SELECT team, COUNT(*) AS total FROM users WHERE team <> '' GROUP BY team"
    )
    counts = Counter({row['team']: int(row['total']) for row in rows})
    open_requests = await game.db.one(
        "SELECT COUNT(*) AS total FROM support_requests WHERE status = 'open'"
    )

    lines = [
        '🛡 <b>ПАНЕЛЬ АРХИВАРИУСА</b>',
        '<i>Единый центр управления участниками и игровым маршрутом</i>',
        '',
        divider(),
        section('Сводка', '📌'),
        stat('Зарегистрировано', total['total'], '👥'),
        stat('Ждут команду', waiting['total'], '⏳'),
        stat('Новых обращений', open_requests['total'], '💬'),
        '',
        section('Наполнение команд', '🎨'),
    ]
    lines.extend(
        f'• <b>{team}</b> — {counts[team]}/{game.settings.team_capacity}'
        for team in TEAM_COLORS
    )
    lines.extend([
        '',
        divider(),
        '👇 <b>Выберите действие</b>',
    ])

    buttons = [
        ('🎛 Прохождение команд', 'ac:home'),
        ('🎨 Выдать команду', 'tq:admin:queue'),
        ('📊 Общий прогресс', 'tq:admin:teams'),
        ('💬 Обращения', 'admin:support'),
        ('📣 Рассылка', 'admin:broadcast'),
        ('📤 Экспорт', 'admin:export'),
        ('🦋 Финал', 'admin:final'),
        ('⚙️ Дополнительно', 'tq:admin:legacy'),
    ]
    if game.is_superadmin(message.from_user.id):
        buttons.insert(2, ('👤 Администраторы', 'access:admins'))

    await message.answer(
        '\n'.join(lines),
        reply_markup=game.inline_buttons(buttons, columns=2),
    )

from __future__ import annotations

from collections import Counter

from aiogram import Bot, F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message

import app as game
from game_data import TEAM_COLORS, format_event_date
from quest_common import *
from route_config import ROUTES, TIME_SLOTS

router = Router(name='last_keeper_team_admin')


@router.message(F.text == '🛡 Управление проектом')
@router.message(Command('admin'))
async def admin_panel(message: Message) -> None:
    if not await game.is_admin(message.from_user.id):
        await message.answer('Эта часть Архива закрыта.')
        return
    await send_admin_panel(message)


async def send_admin_panel(target: Message) -> None:
    waiting = await game.db.one("SELECT COUNT(*) AS total FROM users WHERE team = '' OR status = 'waiting_team'")
    total = await game.db.one('SELECT COUNT(*) AS total FROM users')
    rows = await game.db.all("SELECT team, COUNT(*) AS total FROM users WHERE team <> '' GROUP BY team")
    counts = Counter({row['team']: int(row['total']) for row in rows})
    lines = [
        '<b>Управление проектом</b>', '',
        f'Зарегистрировано: {total["total"]}',
        f'Ожидают команду: <b>{waiting["total"]}</b>', '',
        '<b>Наполнение команд</b>',
    ]
    lines.extend(f'• {team}: {counts[team]}/{game.settings.team_capacity}' for team in TEAM_COLORS)
    buttons = [
        ('🎨 Выдать команду', 'tq:admin:queue'),
        ('🔢 Коды живых локаций', 'tq:admin:codes'),
        ('📊 Прогресс команд', 'tq:admin:teams'),
        ('⚙️ Все функции Архивариуса', 'tq:admin:legacy'),
    ]
    if game.is_superadmin(target.from_user.id):
        buttons.insert(1, ('👤 Управление администраторами', 'access:admins'))
    await target.answer('\n'.join(lines), reply_markup=game.inline_buttons(buttons))


@router.callback_query(F.data == 'tq:admin:legacy')
async def legacy_admin_panel(callback: CallbackQuery) -> None:
    if not await game.is_admin(callback.from_user.id):
        return
    await callback.answer()
    await game.show_admin_panel(callback.message)


@router.callback_query(F.data == 'tq:admin:queue')
async def admin_queue(callback: CallbackQuery) -> None:
    if not await game.is_admin(callback.from_user.id):
        return
    await callback.answer()
    rows = await game.db.all(
        "SELECT telegram_id, full_name, event_date FROM users WHERE team = '' OR status = 'waiting_team' ORDER BY created_at LIMIT 40"
    )
    if not rows:
        await callback.message.answer('Все зарегистрированные участники уже распределены.')
        return
    await callback.message.answer(
        '<b>Кому выдать команду?</b>\nКоманду выбирает только Архивариус.',
        reply_markup=game.inline_buttons([
            (f'{format_event_date(row["event_date"])} · {row["full_name"]}', f'tq:admin:user:{row["telegram_id"]}')
            for row in rows
        ]),
    )


@router.callback_query(F.data.startswith('tq:admin:user:'))
async def admin_choose_user(callback: CallbackQuery) -> None:
    if not await game.is_admin(callback.from_user.id):
        return
    target_id = int(callback.data.rsplit(':', 1)[1])
    target = await game.get_user(target_id)
    if not target:
        await callback.answer('Участник не найден.', show_alert=True)
        return
    rows = await game.db.all(
        "SELECT team, COUNT(*) AS total FROM users WHERE event_date = ? AND team <> '' GROUP BY team",
        (target['event_date'],),
    )
    counts = Counter({row['team']: int(row['total']) for row in rows})
    await callback.answer()
    await callback.message.answer(
        f'<b>{game.escape(target["full_name"])}</b>\n'
        f'День: {format_event_date(target["event_date"])}\n\n'
        'Выбери команду. Бот не позволит превысить установленную вместимость.',
        reply_markup=game.inline_buttons([
            (f'{team} · {counts[team]}/{game.settings.team_capacity}', f'tq:admin:assign:{target_id}:{TEAM_COLORS.index(team)}')
            for team in TEAM_COLORS
        ]),
    )


@router.callback_query(F.data.startswith('tq:admin:assign:'))
async def admin_assign(callback: CallbackQuery, bot: Bot) -> None:
    if not await game.is_admin(callback.from_user.id):
        return
    parts = callback.data.split(':')
    if len(parts) != 5 or not parts[3].isdigit() or not parts[4].isdigit():
        return
    target_id = int(parts[3])
    team_index = int(parts[4])
    if team_index >= len(TEAM_COLORS):
        return
    target = await game.get_user(target_id)
    if not target:
        await callback.answer('Участник не найден.', show_alert=True)
        return
    team = TEAM_COLORS[team_index]
    count = await game.db.one(
        'SELECT COUNT(*) AS total FROM users WHERE event_date = ? AND team = ?',
        (target['event_date'], team),
    )
    if int(count['total']) >= game.settings.team_capacity:
        await callback.answer('Команда заполнена. Выбери другой цвет.', show_alert=True)
        return
    await game.db.execute(
        "UPDATE users SET team = ?, status = 'confirmed' WHERE telegram_id = ?",
        (team, target_id),
    )
    await game.db.log(callback.from_user.id, 'assign_team', {'target_id': target_id, 'team': team})
    await callback.answer('Команда выдана', show_alert=True)
    await callback.message.edit_text(
        f'<b>{game.escape(target["full_name"])}</b> назначен в команду <b>{team}</b>.'
    )
    try:
        first = ROUTES[team][0]
        await bot.send_message(
            target_id,
            '<b>Архив определил твой контур.</b>\n\n'
            f'Твоя команда: <b>{team}</b>\n'
            f'Первая точка: <b>{LOCATION_TITLES[first]}</b>\n'
            f'Время: {TIME_SLOTS[0]}\n\n'
            'Для команды уже подготовлены десять уникальных игр. Открой /start.',
            reply_markup=main_menu(False),
        )
    except Exception:
        await callback.message.answer('Команда сохранена, но Telegram не доставил уведомление участнику.')


@router.callback_query(F.data == 'tq:admin:codes')
async def admin_codes(callback: CallbackQuery) -> None:
    if not await game.is_admin(callback.from_user.id):
        return
    await callback.answer()
    rows = await game.db.all('SELECT location_key, code FROM live_location_codes')
    mapping = {row['location_key']: row['code'] for row in rows}
    lines = [
        '<b>Коды живых локаций</b>',
        'Показывайте участникам код только после выполнения реального задания.',
        '',
    ]
    for key in ('culture', 'science', 'history', 'memory', 'open'):
        lines.append(f'• {LOCATION_TITLES[key]}: <code>{mapping.get(key, "----")}</code>')
    lines.append('\nКоды четырёхзначные и не публикуются в пользовательском интерфейсе.')
    await callback.message.answer('\n'.join(lines))


@router.callback_query(F.data == 'tq:admin:teams')
async def admin_team_progress(callback: CallbackQuery) -> None:
    if not await game.is_admin(callback.from_user.id):
        return
    await callback.answer()
    lines = ['<b>Прогресс команд</b>']
    for event_date in game.settings.event_dates:
        lines.append(f'\n<b>{format_event_date(event_date)}</b>')
        for team in TEAM_COLORS:
            users = await game.db.one(
                'SELECT COUNT(*) AS total FROM users WHERE event_date = ? AND team = ?',
                (event_date, team),
            )
            route = await game.db.one(
                'SELECT COUNT(*) AS total FROM team_route_unlocks WHERE event_date = ? AND team = ?',
                (event_date, team),
            )
            decisions = await game.db.one(
                'SELECT COUNT(*) AS total FROM team_choices WHERE event_date = ? AND team = ?',
                (event_date, team),
            )
            lines.append(
                f'• {team}: {users["total"]} чел. · маршрут {route["total"]}/5 · решения {decisions["total"]}/4'
            )
    await callback.message.answer('\n'.join(lines))

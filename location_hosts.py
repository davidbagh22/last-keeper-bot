from __future__ import annotations

from aiogram import Bot, F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message

import app as game
from game_data import TEAM_COLORS, format_event_date
from quest_common import LOCATION_PLACES, LOCATION_TITLES, main_menu
from route_config import ROUTES, TIME_SLOTS
from storage import utcnow

router = Router(name='location_hosts')
LOCATION_KEYS = ('culture', 'science', 'history', 'memory', 'open')

async def init_location_hosts() -> None:
    await game.db.execute('''CREATE TABLE IF NOT EXISTS location_hosts(
        telegram_id INTEGER PRIMARY KEY, location_key TEXT NOT NULL,
        assigned_by INTEGER NOT NULL, assigned_at TEXT NOT NULL)''')
    await game.db.execute('''CREATE TABLE IF NOT EXISTS location_sessions(
        event_date TEXT NOT NULL, team TEXT NOT NULL, location_key TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'waiting', host_id INTEGER,
        started_at TEXT, completed_at TEXT,
        PRIMARY KEY(event_date, team, location_key))''')

async def host_location(user_id: int) -> str | None:
    row = await game.db.one('SELECT location_key FROM location_hosts WHERE telegram_id = ?', (user_id,))
    return str(row['location_key']) if row else None

async def is_location_host(user_id: int) -> bool:
    return bool(await host_location(user_id))

async def location_host_ids() -> set[int]:
    rows = await game.db.all('SELECT telegram_id FROM location_hosts')
    return {int(row['telegram_id']) for row in rows}

async def completed(event_date: str, team: str) -> set[str]:
    rows = await game.db.all('SELECT location_key FROM team_route_unlocks WHERE event_date = ? AND team = ?', (event_date, team))
    return {str(row['location_key']) for row in rows}

def current_key(team: str, done: set[str]) -> str | None:
    return next((key for key in ROUTES[team] if key not in done), None)

async def notify_team(bot: Bot, event_date: str, team: str, text: str) -> tuple[int, int]:
    rows = await game.db.all('SELECT telegram_id FROM users WHERE event_date = ? AND team = ?', (event_date, team))
    sent = failed = 0
    for row in rows:
        try:
            uid = int(row['telegram_id'])
            await bot.send_message(uid, text, reply_markup=main_menu(await game.is_admin(uid), await is_location_host(uid)))
            sent += 1
        except Exception:
            failed += 1
    return sent, failed

@router.message(F.text == '🎭 Панель ведущего')
@router.message(Command('host'))
async def host_panel(message: Message) -> None:
    location = await host_location(message.from_user.id)
    if not location:
        await message.answer('🔒 Панель доступна только назначенным ведущим локаций.')
        return
    await send_host_panel(message, location)

async def send_host_panel(target: Message, location: str) -> None:
    lines = ['🎭 <b>ПАНЕЛЬ ВЕДУЩЕГО</b>', f'<b>{LOCATION_TITLES[location]}</b>', f'📍 {LOCATION_PLACES[location]}', '']
    buttons = []
    for di, event_date in enumerate(game.settings.event_dates):
        lines.append(f'<b>{format_event_date(event_date)}</b>')
        found = False
        for ti, team in enumerate(TEAM_COLORS):
            done = await completed(event_date, team)
            if current_key(team, done) != location:
                continue
            found = True
            step = ROUTES[team].index(location)
            members = await game.db.one('SELECT COUNT(*) AS total FROM users WHERE event_date = ? AND team = ?', (event_date, team))
            session = await game.db.one('SELECT status FROM location_sessions WHERE event_date = ? AND team = ? AND location_key = ?', (event_date, team, location))
            status = '🟢 на локации' if session and session['status'] == 'active' else '🟡 ожидается'
            lines.append(f'• <b>{team}</b> · этап {step + 1}/5 · {TIME_SLOTS[step]} · {members["total"]} чел. · {status}')
            buttons.append((f'{team} · {status.split()[0]}', f'lh:team:{di}:{ti}'))
        if not found:
            lines.append('• Сейчас команд нет')
        lines.append('')
    await target.answer('\n'.join(lines), reply_markup=game.inline_buttons(buttons + [('🔄 Обновить', 'lh:refresh')]))

@router.callback_query(F.data == 'lh:refresh')
async def refresh(callback: CallbackQuery) -> None:
    location = await host_location(callback.from_user.id)
    if location:
        await callback.answer('Обновлено')
        await send_host_panel(callback.message, location)

@router.callback_query(F.data.startswith('lh:team:'))
async def team_card(callback: CallbackQuery) -> None:
    location = await host_location(callback.from_user.id)
    if not location:
        return
    _, _, d, t = callback.data.split(':')
    di, ti = int(d), int(t)
    event_date, team = game.settings.event_dates[di], TEAM_COLORS[ti]
    done = await completed(event_date, team)
    if current_key(team, done) != location:
        await callback.answer('Команда уже перешла дальше.', show_alert=True)
        return
    session = await game.db.one('SELECT status FROM location_sessions WHERE event_date = ? AND team = ? AND location_key = ?', (event_date, team, location))
    active = bool(session and session['status'] == 'active')
    buttons = [] if active else [('▶️ Команда прибыла', f'lh:start:{di}:{ti}')]
    buttons += [('✅ Завершить этап', f'lh:confirm:{di}:{ti}'), ('⏱ Осталось 5 минут', f'lh:five:{di}:{ti}'), ('🆘 Вызвать администратора', f'lh:alert:{di}:{ti}'), ('⬅️ Назад', 'lh:refresh')]
    await callback.answer()
    await callback.message.answer(
        f'🎭 <b>{LOCATION_TITLES[location]}</b>\n\nКоманда: <b>{team}</b>\nДата: {format_event_date(event_date)}\nСтатус: <b>{"на локации" if active else "ожидается"}</b>\n\nВедущий управляет только своей точкой.',
        reply_markup=game.inline_buttons(buttons),
    )

@router.callback_query(F.data.startswith('lh:start:'))
async def start_team(callback: CallbackQuery, bot: Bot) -> None:
    location = await host_location(callback.from_user.id)
    if not location:
        return
    _, _, d, t = callback.data.split(':')
    event_date, team = game.settings.event_dates[int(d)], TEAM_COLORS[int(t)]
    if current_key(team, await completed(event_date, team)) != location:
        await callback.answer('Команда уже не на этой точке.', show_alert=True)
        return
    await game.db.execute('''INSERT INTO location_sessions(event_date, team, location_key, status, host_id, started_at)
        VALUES(?, ?, ?, 'active', ?, ?) ON CONFLICT(event_date, team, location_key) DO UPDATE SET
        status='active', host_id=excluded.host_id, started_at=excluded.started_at''',
        (event_date, team, location, callback.from_user.id, utcnow()))
    sent, failed = await notify_team(bot, event_date, team, f'🎭 <b>Команда «{team}» принята.</b>\n\nСейчас: <b>{LOCATION_TITLES[location]}</b>. Следующая точка откроется после решения ведущего.')
    await game.db.log(callback.from_user.id, 'location_started', {'date': event_date, 'team': team, 'location': location})
    await callback.answer(f'Отмечено. Доставлено: {sent}, ошибок: {failed}', show_alert=True)

@router.callback_query(F.data.startswith('lh:confirm:'))
async def confirm(callback: CallbackQuery) -> None:
    location = await host_location(callback.from_user.id)
    if not location:
        return
    _, _, d, t = callback.data.split(':')
    team = TEAM_COLORS[int(t)]
    await callback.answer()
    await callback.message.answer(
        f'<b>Завершить локацию?</b>\n\nКоманда: <b>{team}</b>\nТочка: <b>{LOCATION_TITLES[location]}</b>\n\nОткроются вторая цифровая игра и следующая точка.',
        reply_markup=game.inline_buttons([('✅ Подтвердить', f'lh:finish:{d}:{t}'), ('Отмена', f'lh:team:{d}:{t}')]),
    )

@router.callback_query(F.data.startswith('lh:finish:'))
async def finish(callback: CallbackQuery, bot: Bot) -> None:
    location = await host_location(callback.from_user.id)
    if not location:
        return
    _, _, d, t = callback.data.split(':')
    event_date, team = game.settings.event_dates[int(d)], TEAM_COLORS[int(t)]
    done = await completed(event_date, team)
    if current_key(team, done) != location:
        await callback.answer('Этап уже закрыт.', show_alert=True)
        return
    step = ROUTES[team].index(location)
    await game.db.execute('INSERT INTO team_route_unlocks(event_date, team, location_key, step_index, unlocked_by, unlocked_at) VALUES(?, ?, ?, ?, ?, ?)', (event_date, team, location, step, callback.from_user.id, utcnow()))
    await game.db.execute('''INSERT INTO location_sessions(event_date, team, location_key, status, host_id, completed_at)
        VALUES(?, ?, ?, 'completed', ?, ?) ON CONFLICT(event_date, team, location_key) DO UPDATE SET
        status='completed', host_id=excluded.host_id, completed_at=excluded.completed_at''',
        (event_date, team, location, callback.from_user.id, utcnow()))
    next_key = current_key(team, await completed(event_date, team))
    next_text = LOCATION_TITLES[next_key] if next_key else 'финал «Эффект бабочки»'
    sent, failed = await notify_team(bot, event_date, team, f'✅ <b>Фрагмент восстановлен.</b>\n\nЗавершено: <b>{LOCATION_TITLES[location]}</b>.\nСледующая точка: <b>{next_text}</b>.\nВторая цифровая игра уже открыта.')
    await game.db.log(callback.from_user.id, 'location_finished', {'date': event_date, 'team': team, 'location': location})
    await callback.answer('Этап завершён', show_alert=True)
    await callback.message.answer(f'Готово. Доставлено: {sent}, ошибок: {failed}.')
    await send_host_panel(callback.message, location)

@router.callback_query(F.data.startswith('lh:five:'))
async def five_minutes(callback: CallbackQuery, bot: Bot) -> None:
    location = await host_location(callback.from_user.id)
    if not location:
        return
    _, _, d, t = callback.data.split(':')
    event_date, team = game.settings.event_dates[int(d)], TEAM_COLORS[int(t)]
    sent, failed = await notify_team(bot, event_date, team, f'⏱ <b>Команда «{team}», осталось 5 минут.</b>\n\nЗавершите обсуждение и подготовьте общий ответ для ведущего.')
    await callback.answer(f'Доставлено: {sent}, ошибок: {failed}', show_alert=True)

@router.callback_query(F.data.startswith('lh:alert:'))
async def alert_admin(callback: CallbackQuery, bot: Bot) -> None:
    location = await host_location(callback.from_user.id)
    if not location:
        return
    _, _, d, t = callback.data.split(':')
    event_date, team = game.settings.event_dates[int(d)], TEAM_COLORS[int(t)]
    delivered = 0
    for admin_id in await game.admin_recipients():
        try:
            await bot.send_message(admin_id, f'🆘 <b>Вызов ведущего</b>\n\nЛокация: {LOCATION_TITLES[location]}\nКоманда: {team}\nДата: {format_event_date(event_date)}')
            delivered += 1
        except Exception:
            pass
    await callback.answer(f'Администраторов уведомлено: {delivered}', show_alert=True)

@router.callback_query(F.data == 'lh:admin:list')
async def hosts_admin(callback: CallbackQuery) -> None:
    if not game.is_superadmin(callback.from_user.id):
        await callback.answer('Только владелец назначает ведущих.', show_alert=True)
        return
    rows = await game.db.all('''SELECT h.telegram_id, h.location_key, COALESCE(u.full_name, h.telegram_id) AS full_name
        FROM location_hosts h LEFT JOIN users u ON u.telegram_id=h.telegram_id ORDER BY h.location_key, full_name''')
    mapping = {key: [] for key in LOCATION_KEYS}
    for row in rows:
        mapping[row['location_key']].append(str(row['full_name']))
    lines = ['🎭 <b>ВЕДУЩИЕ ПЯТИ ЛОКАЦИЙ</b>', ''] + [f'• <b>{LOCATION_TITLES[key]}</b>: {game.escape(", ".join(mapping[key]) or "не назначен")}' for key in LOCATION_KEYS]
    await callback.answer()
    await callback.message.answer('\n'.join(lines), reply_markup=game.inline_buttons([('➕ Назначить', 'lh:admin:users'), ('➖ Отозвать роль', 'lh:admin:remove')]))

@router.callback_query(F.data == 'lh:admin:users')
async def host_users(callback: CallbackQuery) -> None:
    if not game.is_superadmin(callback.from_user.id):
        return
    rows = await game.db.all('''SELECT u.telegram_id, u.full_name FROM users u LEFT JOIN location_hosts h ON h.telegram_id=u.telegram_id WHERE h.telegram_id IS NULL ORDER BY u.full_name LIMIT 80''')
    await callback.answer()
    if not rows:
        await callback.message.answer('Нет пользователей без роли ведущего.')
        return
    await callback.message.answer('<b>Кого назначить ведущим?</b>', reply_markup=game.inline_buttons([(row['full_name'], f'lh:admin:user:{row["telegram_id"]}') for row in rows]))

@router.callback_query(F.data.startswith('lh:admin:user:'))
async def host_location_choose(callback: CallbackQuery) -> None:
    if not game.is_superadmin(callback.from_user.id):
        return
    uid = int(callback.data.rsplit(':', 1)[1])
    user = await game.get_user(uid)
    await callback.answer()
    await callback.message.answer(f'<b>{game.escape(user["full_name"] if user else uid)}</b>\nВыберите локацию:', reply_markup=game.inline_buttons([(LOCATION_TITLES[key], f'lh:admin:set:{uid}:{i}') for i, key in enumerate(LOCATION_KEYS)]))

@router.callback_query(F.data.startswith('lh:admin:set:'))
async def host_set(callback: CallbackQuery, bot: Bot) -> None:
    if not game.is_superadmin(callback.from_user.id):
        return
    _, _, _, uid_raw, idx_raw = callback.data.split(':')
    uid, location = int(uid_raw), LOCATION_KEYS[int(idx_raw)]
    await game.db.execute('''INSERT INTO location_hosts(telegram_id, location_key, assigned_by, assigned_at) VALUES(?, ?, ?, ?)
        ON CONFLICT(telegram_id) DO UPDATE SET location_key=excluded.location_key, assigned_by=excluded.assigned_by, assigned_at=excluded.assigned_at''',
        (uid, location, callback.from_user.id, utcnow()))
    try:
        await bot.send_message(uid, f'🎭 <b>Вы назначены ведущим.</b>\n\nЛокация: <b>{LOCATION_TITLES[location]}</b>.\nОткройте /host.', reply_markup=main_menu(await game.is_admin(uid), True))
    except Exception:
        pass
    await callback.answer('Ведущий назначен', show_alert=True)
    await callback.message.edit_text(f'Ведущий назначен на локацию <b>{LOCATION_TITLES[location]}</b>.')

@router.callback_query(F.data == 'lh:admin:remove')
async def host_remove_list(callback: CallbackQuery) -> None:
    if not game.is_superadmin(callback.from_user.id):
        return
    rows = await game.db.all('''SELECT h.telegram_id, h.location_key, COALESCE(u.full_name, h.telegram_id) AS full_name FROM location_hosts h LEFT JOIN users u ON u.telegram_id=h.telegram_id ORDER BY h.location_key''')
    await callback.answer()
    if not rows:
        await callback.message.answer('Назначенных ведущих нет.')
        return
    await callback.message.answer('<b>Чью роль отозвать?</b>', reply_markup=game.inline_buttons([(f'{row["full_name"]} · {LOCATION_TITLES[row["location_key"]]}', f'lh:admin:drop:{row["telegram_id"]}') for row in rows]))

@router.callback_query(F.data.startswith('lh:admin:drop:'))
async def host_drop(callback: CallbackQuery, bot: Bot) -> None:
    if not game.is_superadmin(callback.from_user.id):
        return
    uid = int(callback.data.rsplit(':', 1)[1])
    await game.db.execute('DELETE FROM location_hosts WHERE telegram_id = ?', (uid,))
    try:
        await bot.send_message(uid, 'Роль ведущего локации отозвана.', reply_markup=main_menu(await game.is_admin(uid), False))
    except Exception:
        pass
    await callback.answer('Роль отозвана', show_alert=True)
    await callback.message.edit_text('Роль ведущего отозвана.')

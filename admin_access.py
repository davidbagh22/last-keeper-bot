from __future__ import annotations

from aiogram import Bot, F, Router
from aiogram.types import CallbackQuery

import app as game
from storage import utcnow

router = Router(name='last_keeper_admin_access')


@router.callback_query(F.data == 'access:admins')
async def admins_panel(callback: CallbackQuery) -> None:
    if not game.is_superadmin(callback.from_user.id):
        await callback.answer('Управление администраторами доступно только владельцу проекта.', show_alert=True)
        return
    await callback.answer()
    superadmins = tuple(game.settings.superadmin_ids)
    placeholders = ','.join('?' for _ in superadmins) or '0'
    rows = await game.db.all(
        f'''SELECT u.telegram_id, u.full_name, u.team,
                   CASE WHEN a.telegram_id IS NULL THEN 0 ELSE 1 END AS is_admin
            FROM users u
            LEFT JOIN admin_users a ON a.telegram_id = u.telegram_id
            WHERE u.telegram_id NOT IN ({placeholders})
            ORDER BY is_admin DESC, u.full_name''',
        superadmins,
    )
    if not rows:
        await callback.message.answer('Пока нет зарегистрированных пользователей, которым можно выдать доступ.')
        return
    buttons = []
    for row in rows[:80]:
        status = '✓ админ' if row['is_admin'] else '＋ выдать доступ'
        team = f' · {row["team"]}' if row['team'] else ''
        buttons.append((f'{status} · {row["full_name"]}{team}', f'access:user:{row["telegram_id"]}'))
    await callback.message.answer(
        '<b>Администраторы проекта</b>\n\n'
        'Выбери зарегистрированного пользователя. Можно выдать или отозвать доступ. '
        'Владелец проекта не отображается в списке и не может быть удалён.',
        reply_markup=game.inline_buttons(buttons),
    )


@router.callback_query(F.data.startswith('access:user:'))
async def admin_user_card(callback: CallbackQuery) -> None:
    if not game.is_superadmin(callback.from_user.id):
        return
    target_id = int(callback.data.rsplit(':', 1)[1])
    user = await game.get_user(target_id)
    if not user:
        await callback.answer('Пользователь не найден.', show_alert=True)
        return
    row = await game.db.one('SELECT 1 FROM admin_users WHERE telegram_id = ?', (target_id,))
    await callback.answer()
    action = (
        ('Отозвать права администратора', f'access:remove:{target_id}')
        if row else
        ('Выдать права администратора', f'access:add:{target_id}')
    )
    await callback.message.answer(
        f'<b>{game.escape(user["full_name"])}</b>\n'
        f'Telegram ID: <code>{target_id}</code>\n'
        f'Команда: {game.escape(user["team"] or "ещё не назначена")}\n'
        f'Статус: {"администратор" if row else "участник"}',
        reply_markup=game.inline_buttons([action, ('Назад к списку', 'access:admins')]),
    )


@router.callback_query(F.data.startswith('access:add:'))
async def add_admin(callback: CallbackQuery, bot: Bot) -> None:
    if not game.is_superadmin(callback.from_user.id):
        return
    target_id = int(callback.data.rsplit(':', 1)[1])
    if target_id in game.settings.superadmin_ids:
        await callback.answer('Этот пользователь уже является владельцем проекта.', show_alert=True)
        return
    user = await game.get_user(target_id)
    if not user:
        await callback.answer('Пользователь не найден.', show_alert=True)
        return
    await game.db.execute(
        '''INSERT INTO admin_users(telegram_id, added_by, added_at)
           VALUES(?, ?, ?)
           ON CONFLICT(telegram_id) DO UPDATE SET added_by = excluded.added_by, added_at = excluded.added_at''',
        (target_id, callback.from_user.id, utcnow()),
    )
    await game.db.log(callback.from_user.id, 'grant_admin', {'target_id': target_id})
    await callback.answer('Администратор добавлен', show_alert=True)
    try:
        await bot.send_message(
            target_id,
            '<b>Тебе открыт доступ Архивариуса.</b>\n\n'
            'Кнопка «🛡 Управление проектом» теперь постоянно отображается в главном меню. '
            'Команда /start также обновит меню.',
            reply_markup=game.main_menu(True),
        )
    except Exception:
        pass
    await callback.message.edit_text(
        f'<b>{game.escape(user["full_name"])}</b> назначен администратором проекта.'
    )


@router.callback_query(F.data.startswith('access:remove:'))
async def remove_admin(callback: CallbackQuery, bot: Bot) -> None:
    if not game.is_superadmin(callback.from_user.id):
        return
    target_id = int(callback.data.rsplit(':', 1)[1])
    if target_id in game.settings.superadmin_ids:
        await callback.answer('Владельца проекта нельзя удалить.', show_alert=True)
        return
    user = await game.get_user(target_id)
    await game.db.execute('DELETE FROM admin_users WHERE telegram_id = ?', (target_id,))
    await game.db.log(callback.from_user.id, 'revoke_admin', {'target_id': target_id})
    await callback.answer('Доступ отозван', show_alert=True)
    try:
        await bot.send_message(
            target_id,
            'Доступ Архивариуса отозван. Игровые данные и регистрация сохранены.',
            reply_markup=game.main_menu(False),
        )
    except Exception:
        pass
    await callback.message.edit_text(
        f'Права администратора для <b>{game.escape(user["full_name"] if user else target_id)}</b> отозваны.'
    )

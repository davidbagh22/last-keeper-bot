from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message

import app as game

router = Router(name='presentation_admin_tools')


async def _reset_user(user_id: int) -> None:
    await game.db.execute(
        "UPDATE presentation_demo_sessions SET first_choice='', second_choice='', stage='', attempts=0, completed_at=NULL WHERE user_id=?",
        (user_id,),
    )


async def _panel(target: Message) -> None:
    mode = await game.db.setting('showcase_mode', 'mixed')
    demo = await game.db.setting('demo_enabled', '1')
    await target.answer(
        '<b>🎬 ПРЕЗЕНТАЦИОННЫЙ РЕЖИМ</b>\n\n'
        f'Режим: <b>{mode}</b>\n'
        f'Демо: <b>{"включено" if demo == "1" else "выключено"}</b>\n\n'
        '<i>Все изменения применяются сразу.</i>',
        reply_markup=game.inline_buttons([
            ('🎤 Только демо', 'show:mode:presentation'),
            ('✨ Демо + регистрация', 'show:mode:mixed'),
            ('🚀 Мероприятие', 'show:mode:event'),
            ('🔒 Закрыть', 'show:mode:closed'),
            ('Вкл./выкл. демо', 'show:toggle-demo'),
            ('↻ Моё демо', 'show:restart-self'),
            ('♻️ Сбросить всем', 'show:restart-all'),
        ], columns=2),
    )


@router.message(Command('showmode'))
async def showmode(message: Message) -> None:
    if await game.is_admin(message.from_user.id):
        await _panel(message)


@router.callback_query(F.data == 'show:admin')
async def showmode_callback(callback: CallbackQuery) -> None:
    if not await game.is_admin(callback.from_user.id):
        return
    await callback.answer()
    await _panel(callback.message)


@router.message(Command('demorestart'))
async def restart_demo_command(message: Message) -> None:
    if not await game.is_admin(message.from_user.id):
        return
    await _reset_user(message.from_user.id)
    await message.answer(
        '<b>Демо перезапущено.</b>\n\nОткройте /start и нажмите «🔓 Открыть Архив».',
        reply_markup=game.inline_buttons([('🔓 Открыть Архив', 'show:demo')]),
    )


@router.callback_query(F.data == 'show:restart-self')
async def restart_self(callback: CallbackQuery) -> None:
    if not await game.is_admin(callback.from_user.id):
        return
    await _reset_user(callback.from_user.id)
    await callback.answer('Демо перезапущено', show_alert=True)
    await callback.message.answer(
        '<b>Чистый запуск готов.</b>',
        reply_markup=game.inline_buttons([('🔓 Открыть Архив', 'show:demo')]),
    )


@router.callback_query(F.data == 'show:restart-all')
async def restart_all(callback: CallbackQuery) -> None:
    if not game.is_superadmin(callback.from_user.id):
        await callback.answer('Только владелец может сбросить демо всем.', show_alert=True)
        return
    await game.db.execute(
        "UPDATE presentation_demo_sessions SET first_choice='', second_choice='', stage='', attempts=0, completed_at=NULL"
    )
    await callback.answer('Демо сброшено всем участникам', show_alert=True)

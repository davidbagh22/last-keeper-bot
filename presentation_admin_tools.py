from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message

import app as game
from demo_visuals import visual

router = Router(name='presentation_admin_tools')


async def _reset_user(user_id: int) -> None:
    await game.db.execute(
        "UPDATE presentation_demo_sessions SET first_choice='', second_choice='', stage='', attempts=0, completed_at=NULL WHERE user_id=?",
        (user_id,),
    )


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


@router.callback_query(F.data == 'show:visual-preview')
async def visual_preview(callback: CallbackQuery) -> None:
    if not await game.is_admin(callback.from_user.id):
        return
    await callback.answer()
    for kind, caption in (
        ('entry', '01 · Вход в Архив'),
        ('scan', '02 · Сканирование'),
        ('riddle', '03 · Живой ключ'),
        ('restored', '04 · Фрагмент восстановлен'),
        ('finale', '05 · Финальная легенда'),
    ):
        await callback.message.answer_photo(visual(kind), caption=f'<b>{caption}</b>')

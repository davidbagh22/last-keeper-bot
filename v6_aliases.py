from __future__ import annotations

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery

import app as game
import partners

router = Router(name='last_keeper_v6_aliases')


@router.callback_query(F.data == 'partners:show')
async def show_partners(callback: CallbackQuery) -> None:
    await callback.answer()
    await partners.send_partners(callback.message)


@router.callback_query(F.data == 'demo:rules')
async def show_rules(callback: CallbackQuery) -> None:
    await callback.answer()
    await callback.message.answer(
        '<b>Как проходит игра</b>\n\n'
        '1. Команда приходит на живую локацию.\n'
        '2. Выполняет общее задание.\n'
        '3. Ведущий подтверждает прохождение.\n'
        '4. Открываются следующая точка и новая цифровая миссия.\n'
        '5. В финале решения команды собираются в «Эффект бабочки».')


@router.callback_query(F.data == 'support:start')
async def start_support(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    await state.set_state(game.SupportFlow.text)
    await callback.message.answer(
        '<b>Вопрос Архивариусу</b>\n\nОпишите проблему одним сообщением. '
        'Укажите команду и локацию, если вопрос связан с маршрутом.')


@router.callback_query(F.data == 'v6:admin')
async def admin_hint(callback: CallbackQuery) -> None:
    if not await game.is_admin(callback.from_user.id):
        await callback.answer('Доступ закрыт.', show_alert=True)
        return
    await callback.answer()
    await callback.message.answer('Откройте основную панель командой /admin.')

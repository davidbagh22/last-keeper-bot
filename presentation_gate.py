from __future__ import annotations

import re

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

import app as game
import presentation_demo

router = Router(name='last_keeper_presentation_gate')


class SlideGate(StatesGroup):
    answer = State()


def normalize_answer(value: str) -> str:
    return re.sub(r'[^а-яёa-z0-9]+', '', value.casefold().replace('ё', 'е'))


VALID_ANSWERS = {'зеленый', 'зелёный'}


async def gate_enabled() -> bool:
    return await game.db.setting('presentation_gate_enabled', '1') == '1'


async def show_first_dilemma(target: Message) -> None:
    await target.answer(
        '<b>ФРАГМЕНТ №1 · КОД СЛОВА</b>\n\n'
        'Архив восстановил строку — но теперь нужно решить, <b>как передать её дальше</b>.\n\n'
        'Перед вами редкий текст русской культуры. Через сто лет его смысл может стать непонятным новому поколению.\n\n'
        '<b>Что вы сохраните в первую очередь?</b>\n\n'
        '<i>Здесь нет неправильного решения. Есть только разные последствия.</i>',
        reply_markup=game.inline_buttons([
            (item.title, f'show:first:{item.code}') for item in presentation_demo.FIRST_CHOICES
        ]),
    )


@router.callback_query(F.data == 'show:first')
async def slide_cipher_start(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    if not await gate_enabled():
        await show_first_dilemma(callback.message)
        return

    await state.set_state(SlideGate.answer)
    await callback.message.edit_text(
        '<b>━━━━━━━━━━━━━━━━━━\n'
        'ФРАГМЕНТ ЗАБЛОКИРОВАН\n'
        '━━━━━━━━━━━━━━━━━━</b>\n\n'
        'Бот видит только часть строки:\n\n'
        '<code>У лукоморья дуб ______</code>\n\n'
        'Недостающее слово находится <b>не в телефоне</b>. Оно спрятано на экране презентации.\n\n'
        'Введите слово сообщением — только тогда Архив откроет следующую ветвь.\n\n'
        '<i>Так в полном проекте живые локации и Telegram-бот образуют единый маршрут: действие в пространстве открывает цифровое продолжение.</i>'
    )


@router.message(SlideGate.answer)
async def slide_cipher_answer(message: Message, state: FSMContext) -> None:
    answer = normalize_answer(message.text or '')
    if answer not in {normalize_answer(item) for item in VALID_ANSWERS}:
        await message.answer(
            '<b>Код не принят.</b>\n\n'
            'Посмотрите на экран презентации внимательнее. Нужен цвет дуба из первой строки пролога к «Руслану и Людмиле».\n\n'
            '<i>Подсказка: введите одно слово без кавычек.</i>'
        )
        return

    await state.clear()
    await message.answer(
        '<b>━━━━━━━━━━━━━━━━━━\n'
        'ЖИВОЙ КОД ПРИНЯТ\n'
        '━━━━━━━━━━━━━━━━━━</b>\n\n'
        'Слово восстановлено: <b>ЗЕЛЁНЫЙ</b>.\n\n'
        'Вы только что связали физическую презентацию и цифровой Архив. В реальном проекте так же работают коды живых локаций: без действия в пространстве следующая часть истории не открывается.\n\n'
        '<b>Но восстановить слово недостаточно.</b> Теперь нужно решить, что с ним делать дальше.',
        reply_markup=game.inline_buttons([('Продолжить реконструкцию', 'gate:continue')]),
    )


@router.callback_query(F.data == 'gate:continue')
async def gate_continue(callback: CallbackQuery) -> None:
    await callback.answer()
    await show_first_dilemma(callback.message)


@router.message(Command('gate'))
async def gate_admin_command(message: Message) -> None:
    if not await game.is_admin(message.from_user.id):
        return
    await send_gate_admin(message)


@router.callback_query(F.data == 'gate:admin')
async def gate_admin_callback(callback: CallbackQuery) -> None:
    if not await game.is_admin(callback.from_user.id):
        return
    await callback.answer()
    await send_gate_admin(callback.message)


async def send_gate_admin(target: Message) -> None:
    enabled = await gate_enabled()
    await target.answer(
        '<b>🧩 КОД С ПРЕЗЕНТАЦИИ</b>\n\n'
        f'Статус: <b>{"включён" if enabled else "выключен"}</b>\n\n'
        'Когда код включён, после запуска демо участник должен найти слово на слайде и ввести его в бот.\n\n'
        'Ключ: <code>ЗЕЛЁНЫЙ</code>',
        reply_markup=game.inline_buttons([
            ('Выключить код' if enabled else 'Включить код', 'gate:toggle'),
            ('🎬 Режим показа', 'show:admin'),
        ]),
    )


@router.callback_query(F.data == 'gate:toggle')
async def gate_toggle(callback: CallbackQuery) -> None:
    if not await game.is_admin(callback.from_user.id):
        return
    enabled = await gate_enabled()
    value = '0' if enabled else '1'
    await game.db.set_setting('presentation_gate_enabled', value)
    await game.db.log(callback.from_user.id, 'toggle_presentation_gate', {'enabled': value})
    await callback.answer('Код выключен' if enabled else 'Код включён', show_alert=True)
    await send_gate_admin(callback.message)

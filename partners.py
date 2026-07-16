from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message

router = Router(name='last_keeper_partners')

PARTNERS = (
    ('КСООРС Армении', 'https://t.me/ksoors_arm'),
    ('Московский Дом соотечественника', 'https://t.me/mosdoms'),
    ('Молодёжное движение соотечественников', 'https://t.me/MDS_molod'),
    ('Дом Москвы в Ереване', 'https://t.me/dommoskvyerevan'),
    ('ОО «ЭРА»', 'https://t.me/era_leaders1'),
)


def partners_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=f'↗ {name}', url=url)]
            for name, url in PARTNERS
        ]
    )


async def send_partners(message: Message) -> None:
    await message.answer(
        '<b>Партнёры проекта «Последний хранитель»</b>\n\n'
        'Проект создаётся не одной командой. За ним стоит сообщество организаций, '
        'которые поддерживают молодых российских соотечественников, культурные инициативы '
        'и живую связь с Россией.\n\n'
        'Нажми на название, чтобы открыть официальный Telegram-канал партнёра.',
        reply_markup=partners_keyboard(),
    )


@router.message(Command('partners'))
@router.message(F.text.in_({'🤝 Партнёры проекта', 'Партнёры проекта'}))
async def partners(message: Message) -> None:
    await send_partners(message)

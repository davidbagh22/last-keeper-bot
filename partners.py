from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message

from ui_text import divider

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
            [InlineKeyboardButton(text=f'↗️ {name}', url=url)]
            for name, url in PARTNERS
        ]
    )


async def send_partners(message: Message) -> None:
    await message.answer(
        '🤝 <b>ПАРТНЁРЫ ПРОЕКТА</b>\n'
        '<i>Организации, которые помогают «Последнему хранителю» стать реальностью</i>\n\n'
        f'{divider()}\n\n'
        '🌍 Поддерживают молодых российских соотечественников\n'
        '🏛 Помогают развивать культурные инициативы\n'
        '🇷🇺 Укрепляют живую связь с Россией\n\n'
        '👇 <b>Откройте официальный Telegram-канал партнёра:</b>',
        reply_markup=partners_keyboard(),
    )


@router.message(Command('partners'))
@router.message(F.text.in_({'🤝 Партнёры проекта', 'Партнёры проекта'}))
async def partners(message: Message) -> None:
    await send_partners(message)

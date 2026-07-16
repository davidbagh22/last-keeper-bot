from __future__ import annotations

import asyncio
import csv
import html
import io
import json
import logging
import os
import secrets
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import aiosqlite
from aiogram import Bot, Dispatcher, F, Router
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    BufferedInputFile,
    CallbackQuery,
    KeyboardButton,
    Message,
    ReplyKeyboardMarkup,
    Update,
)
from aiogram.utils.keyboard import InlineKeyboardBuilder
from fastapi import FastAPI, HTTPException, Request

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
log = logging.getLogger("last_keeper")


class Settings:
    bot_token = os.getenv("BOT_TOKEN", "").strip()
    admin_ids_raw = os.getenv("ADMIN_IDS", "1593868942")
    database_path = os.getenv("DATABASE_PATH", "/tmp/last_keeper.db")
    event_dates_raw = os.getenv("EVENT_DATES", "2026-11-16,2026-11-17")
    team_capacity = int(os.getenv("TEAM_CAPACITY", "30"))
    public_base_url = (
        os.getenv("PUBLIC_BASE_URL", "").strip()
        or os.getenv("RENDER_EXTERNAL_URL", "").strip()
    ).rstrip("/")
    webhook_secret = os.getenv("WEBHOOK_SECRET", "").strip() or secrets.token_urlsafe(24)
    culture_code = os.getenv("LOCATION_CODE_CULTURE", "CULT26").strip()
    science_code = os.getenv("LOCATION_CODE_SCIENCE", "SCI26").strip()
    history_code = os.getenv("LOCATION_CODE_HISTORY", "HIST26").strip()
    memory_code = os.getenv("LOCATION_CODE_MEMORY", "MEM26").strip()

    @property
    def admin_ids(self) -> set[int]:
        return {
            int(value.strip())
            for value in self.admin_ids_raw.split(",")
            if value.strip().isdigit()
        }

    @property
    def event_dates(self) -> list[str]:
        return [
            value.strip()
            for value in self.event_dates_raw.split(",")
            if value.strip()
        ]


settings = Settings()
DB = settings.database_path
router = Router()

TEAM_COLORS = ["Красные", "Белые", "Оранжевые", "Зелёные", "Синие"]

LOCATIONS: dict[str, dict[str, Any]] = {
    "culture": {
        "title": "Код культуры",
        "place": "Библиотека, 3 этаж",
        "code": settings.culture_code,
        "question": "Что должна сохранить команда?",
        "intro": (
            "Архив сохранил древний символ, но утратил объяснение его смысла.\n\n"
            "Можно сохранить привычную форму, которую узнают поколения, "
            "или передать её смысл новым языком."
        ),
        "choices": [
            (
                "culture_form",
                "Сохранить исходную форму",
                {"memory": 2, "truth": 1, "progress": -1},
                "Символ сохранён без изменений. Архив стал точнее, но его язык оказался понятен не каждому.",
            ),
            (
                "culture_new",
                "Передать смысл новым языком",
                {"unity": 2, "progress": 1, "truth": -1},
                "Символ заговорил с новым поколением. Но часть первоначальных деталей растворилась в переводе.",
            ),
        ],
    },
    "science": {
        "title": "Цена открытия",
        "place": "Лофт №1, 2 этаж",
        "code": settings.science_code,
        "question": "Как поступит команда?",
        "intro": (
            "Российское открытие готово изменить жизнь людей. "
            "Дополнительная проверка задержит его применение, "
            "но может предотвратить неизвестные последствия."
        ),
        "choices": [
            (
                "science_now",
                "Открыть доступ сейчас",
                {"progress": 2, "unity": 1, "responsibility": -1},
                "Открытие вышло за стены лаборатории. Мир получил новую возможность раньше, чем успел понять её цену.",
            ),
            (
                "science_check",
                "Остановиться и проверить",
                {"responsibility": 2, "truth": 1, "progress": -1},
                "Открытие осталось под защитой Архива. Риск уменьшился, но часть времени была потеряна.",
            ),
        ],
    },
    "history": {
        "title": "Выбор эпохи",
        "place": "Выставочный зал, 1 этаж",
        "code": settings.history_code,
        "question": "Что выберет команда?",
        "intro": (
            "Найден документ, способный изменить привычное понимание исторического события. "
            "Его публикация восстановит часть истины, но нарушит сложившееся представление о прошлом."
        ),
        "choices": [
            (
                "history_old",
                "Сохранить прежнюю версию",
                {"memory": 2, "unity": 1, "truth": -1},
                "История сохранила знакомый облик. Но одна страница Архива осталась закрытой.",
            ),
            (
                "history_open",
                "Открыть найденное свидетельство",
                {"truth": 2, "responsibility": 1, "unity": -1},
                "Свидетельство возвращено в Архив. История стала полнее, но спокойствие оказалось нарушено.",
            ),
        ],
    },
    "memory": {
        "title": "Голоса памяти",
        "place": "Лофт №2, 2 этаж",
        "code": settings.memory_code,
        "question": "Что должно остаться для будущих поколений?",
        "intro": (
            "В Архиве сохранились два рассказа об одном событии. "
            "Один точен и подтверждён документами. Второй передаёт личную боль, но содержит расхождения."
        ),
        "choices": [
            (
                "memory_fact",
                "Сохранить подтверждённый рассказ",
                {"truth": 2, "memory": 1, "unity": -1},
                "Архив сохранил точность. Но один человеческий голос исчез между строками.",
            ),
            (
                "memory_both",
                "Сохранить оба голоса с пояснением",
                {"responsibility": 2, "unity": 1, "memory": 1},
                "Архив сохранил не только факт, но и переживание. Будущим Хранителям придётся различать документ и память человека.",
            ),
        ],
    },
}

ROUTES = {
    "Красные": ["culture", "science", "history", "memory", "open"],
    "Белые": ["science", "history", "memory", "open", "culture"],
    "Оранжевые": ["history", "memory", "open", "culture", "science"],
    "Зелёные": ["memory", "open", "culture", "science", "history"],
    "Синие": ["open", "culture", "science", "history", "memory"],
}

TIME_SLOTS = [
    "11:00–11:40",
    "11:40–12:20",
    "12:20–13:00",
    "13:00–13:40",
    "13:40–14:15",
]


class Reg(StatesGroup):
    consent = State()
    name = State()
    age = State()
    organization = State()
    date = State()


class CaptainFlow(StatesGroup):
    code = State()
    confirm = State()


class SupportFlow(StatesGroup):
    text = State()


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


async def db_exec(query: str, params: tuple[Any, ...] = ()) -> None:
    Path(DB).parent.mkdir(parents=True, exist_ok=True)
    async with aiosqlite.connect(DB) as db:
        await db.execute(query, params)
        await db.commit()


async def db_one(query: str, params: tuple[Any, ...] = ()):
    async with aiosqlite.connect(DB) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(query, params)
        return await cursor.fetchone()


async def db_all(query: str, params: tuple[Any, ...] = ()):
    async with aiosqlite.connect(DB) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(query, params)
        return await cursor.fetchall()


async def init_db() -> None:
    Path(DB).parent.mkdir(parents=True, exist_ok=True)
    async with aiosqlite.connect(DB) as db:
        await db.execute("PRAGMA journal_mode=WAL")
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS users(
                telegram_id INTEGER PRIMARY KEY,
                username TEXT NOT NULL DEFAULT '',
                full_name TEXT NOT NULL,
                age INTEGER NOT NULL,
                organization TEXT NOT NULL DEFAULT '',
                event_date TEXT NOT NULL,
                team TEXT NOT NULL,
                role TEXT NOT NULL DEFAULT 'participant',
                checked_in INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL
            )
            """
        )
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS team_choices(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_date TEXT NOT NULL,
                team TEXT NOT NULL,
                location_key TEXT NOT NULL,
                choice_code TEXT NOT NULL,
                selected_by INTEGER NOT NULL,
                effects_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                UNIQUE(event_date, team, location_key)
            )
            """
        )
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS support_requests(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                category TEXT NOT NULL,
                message TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'open',
                created_at TEXT NOT NULL
            )
            """
        )
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS settings(
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
            """
        )
        await db.execute(
            "INSERT OR IGNORE INTO settings(key, value) VALUES('final_open', '0')"
        )
        await db.commit()


def inline_buttons(items: list[tuple[str, str]]):
    builder = InlineKeyboardBuilder()
    for text, data in items:
        builder.button(text=text, callback_data=data)
    builder.adjust(1)
    return builder.as_markup()


def main_menu() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(text="Следующая точка"),
                KeyboardButton(text="Мой маршрут"),
            ],
            [
                KeyboardButton(text="Состояние Архива"),
                KeyboardButton(text="Мои фрагменты"),
            ],
            [
                KeyboardButton(text="Позвать Архивариуса"),
                KeyboardButton(text="Правила"),
            ],
        ],
        resize_keyboard=True,
    )


async def get_user(telegram_id: int):
    return await db_one(
        "SELECT * FROM users WHERE telegram_id = ?",
        (telegram_id,),
    )


async def require_user(message: Message):
    user = await get_user(message.from_user.id)
    if not user:
        await message.answer("Сначала отправь /start и заверши регистрацию.")
    return user


async def assign_team(event_date: str) -> str:
    counts = {color: 0 for color in TEAM_COLORS}
    rows = await db_all(
        """
        SELECT team, COUNT(*) AS total
        FROM users
        WHERE event_date = ?
        GROUP BY team
        """,
        (event_date,),
    )
    for row in rows:
        counts[row["team"]] = row["total"]
    available = [
        color
        for color in TEAM_COLORS
        if counts[color] < settings.team_capacity
    ]
    return min(available or TEAM_COLORS, key=lambda color: counts[color])


async def get_team_choices(user) -> list:
    return await db_all(
        """
        SELECT *
        FROM team_choices
        WHERE event_date = ? AND team = ?
        ORDER BY id
        """,
        (user["event_date"], user["team"]),
    )


async def team_parameters(user) -> dict[str, int]:
    result = {
        "memory": 0,
        "truth": 0,
        "unity": 0,
        "progress": 0,
        "responsibility": 0,
    }
    for row in await get_team_choices(user):
        for key, value in json.loads(row["effects_json"]).items():
            result[key] += value
    return result


def final_archetype(parameters: dict[str, int]) -> tuple[str, str]:
    values = list(parameters.values())
    average = sum(values) / len(values)

    if (
        max(values) - min(values) <= 2
        and parameters["responsibility"] >= average
    ):
        return (
            "Общее наследие",
            "Вы не пытались сохранить прошлое неподвижным и не позволили ему раствориться в переменах. Ваш Архив стал живым общим наследием.",
        )
    if parameters["responsibility"] == max(values):
        return (
            "Архив ответственности",
            "Вы не искали простых ответов. Ваш Архив хранит не только события, но и цену решений.",
        )
    if (
        parameters["unity"] >= 3
        and parameters["progress"] >= 2
        and parameters["truth"] < max(parameters["unity"], parameters["progress"])
    ):
        return (
            "Живой архив",
            "Вы сделали память понятной и близкой людям. Архив заговорил живым языком, но часть деталей изменилась при передаче.",
        )
    if (
        parameters["memory"] >= 3
        and parameters["truth"] >= 3
        and parameters["unity"] <= 1
    ):
        return (
            "Закрытый архив",
            "Вы сохранили точность документов и силу свидетельств. Архив уцелел, но стал закрытым.",
        )
    return (
        "Холодный прогресс",
        "Вы открыли Архив будущему. Он стал быстрым и технологичным, но в нём осталось меньше человеческого голоса и осторожности.",
    )


def format_event_date(value: str) -> str:
    try:
        return datetime.fromisoformat(value).strftime("%d.%m.%Y")
    except ValueError:
        return value


@router.message(CommandStart())
async def start(message: Message, state: FSMContext) -> None:
    user = await get_user(message.from_user.id)
    if user:
        await state.clear()
        await message.answer(
            f"Архив узнал тебя, <b>{html.escape(user['full_name'])}</b>.\n"
            f"Команда: <b>{html.escape(user['team'])}</b>.",
            reply_markup=main_menu(),
        )
        return

    await state.set_state(Reg.consent)
    await message.answer(
        "<b>Архив открылся. Но часть его страниц исчезла.</b>\n\n"
        "Сегодня тебе предстоит стать Хранителем и восстановить то, "
        "что ещё можно спасти.\n\n"
        "Чтобы сохранить маршрут, Архиву потребуется имя, возраст и Telegram ID.",
        reply_markup=inline_buttons(
            [
                ("Согласен", "consent:yes"),
                ("Не согласен", "consent:no"),
            ]
        ),
    )


@router.callback_query(Reg.consent, F.data.startswith("consent:"))
async def consent(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    if callback.data.endswith("no"):
        await callback.message.edit_text(
            "Без согласия Архив не сможет сохранить твой маршрут."
        )
        await state.clear()
        return

    await state.set_state(Reg.name)
    await callback.message.edit_text(
        "<b>Как записать тебя в Книгу Хранителей?</b>\n"
        "Укажи имя и фамилию."
    )


@router.message(Reg.name)
async def registration_name(message: Message, state: FSMContext) -> None:
    value = (message.text or "").strip()
    if len(value.split()) < 2 or len(value) > 100:
        await message.answer("Укажи имя и фамилию. Например: Анна Иванова.")
        return
    await state.update_data(full_name=value)
    await state.set_state(Reg.age)
    await message.answer(
        "<b>Сколько тебе лет?</b>\n"
        "Основной маршрут создан для участников от 16 до 26 лет."
    )


@router.message(Reg.age)
async def registration_age(message: Message, state: FSMContext) -> None:
    value = (message.text or "").strip()
    if not value.isdigit() or not 10 <= int(value) <= 99:
        await message.answer("Введи возраст одним числом.")
        return
    await state.update_data(age=int(value))
    await state.set_state(Reg.organization)
    await message.answer(
        "<b>Откуда ты пришёл в Архив?</b>\n"
        "Укажи университет, организацию или напиши «Пропустить»."
    )


@router.message(Reg.organization)
async def registration_organization(message: Message, state: FSMContext) -> None:
    value = (message.text or "").strip()
    organization = "" if value.casefold() == "пропустить" else value[:150]
    await state.update_data(organization=organization)
    await state.set_state(Reg.date)

    buttons = []
    for event_date in settings.event_dates:
        buttons.append((format_event_date(event_date), f"date:{event_date}"))
    await message.answer(
        "<b>Выбери день, когда начнётся твой путь.</b>",
        reply_markup=inline_buttons(buttons),
    )


@router.callback_query(Reg.date, F.data.startswith("date:"))
async def registration_date(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    event_date = callback.data.split(":", 1)[1]
    if event_date not in settings.event_dates:
        await callback.message.answer("Этот день больше недоступен. Отправь /start.")
        await state.clear()
        return

    data = await state.get_data()
    team = await assign_team(event_date)
    role = "admin" if callback.from_user.id in settings.admin_ids else "participant"

    try:
        await db_exec(
            """
            INSERT INTO users(
                telegram_id, username, full_name, age, organization,
                event_date, team, role, created_at
            )
            VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                callback.from_user.id,
                callback.from_user.username or "",
                data["full_name"],
                data["age"],
                data["organization"],
                event_date,
                team,
                role,
                utcnow(),
            ),
        )
    except aiosqlite.IntegrityError:
        pass

    await state.clear()
    await callback.message.edit_text(
        "<b>Запись сохранена.</b>\n"
        f"Хранитель: {html.escape(data['full_name'])}\n"
        f"День: {format_event_date(event_date)}\n"
        f"Команда: <b>{team}</b>"
    )
    await callback.message.answer(
        "Архив определил твой контур. Не меняй команду самостоятельно.",
        reply_markup=main_menu(),
    )


@router.message(F.text == "Мой маршрут")
async def show_route(message: Message) -> None:
    user = await require_user(message)
    if not user:
        return

    lines = [f"<b>Маршрут команды «{html.escape(user['team'])}»</b>"]
    for index, key in enumerate(ROUTES[user["team"]]):
        if key == "open":
            title = "Открытые пространства"
            place = "VR-зона, выставка и фотозона"
        else:
            title = LOCATIONS[key]["title"]
            place = LOCATIONS[key]["place"]
        lines.append(
            f"{index + 1}. {TIME_SLOTS[index]} — <b>{title}</b>\n"
            f"   {place}"
        )
    await message.answer("\n".join(lines))


@router.message(F.text == "Следующая точка")
async def next_point(message: Message) -> None:
    user = await require_user(message)
    if not user:
        return

    choices = await get_team_choices(user)
    done = {row["location_key"] for row in choices}

    for index, key in enumerate(ROUTES[user["team"]]):
        if key == "open":
            continue
        if key not in done:
            location = LOCATIONS[key]
            await message.answer(
                "<b>Архив вызывает вашу команду.</b>\n\n"
                f"Следующая точка: <b>{location['title']}</b>\n"
                f"Место: {location['place']}\n"
                f"Время: {TIME_SLOTS[index]}",
                reply_markup=inline_buttons(
                    [
                        ("Ввести код локации", f"open:{key}"),
                        ("Нужна помощь", "support:location"),
                    ]
                ),
            )
            return

    await message.answer(
        "Основной маршрут завершён. Ожидайте открытия общего финала."
    )


@router.callback_query(F.data.startswith("open:"))
async def open_location(callback: CallbackQuery, state: FSMContext) -> None:
    user = await get_user(callback.from_user.id)
    if not user:
        await callback.answer("Сначала зарегистрируйся через /start.", show_alert=True)
        return
    if user["role"] not in {"captain", "admin"}:
        await callback.answer(
            "Код и решение вводит капитан команды.",
            show_alert=True,
        )
        return

    key = callback.data.split(":", 1)[1]
    if key not in LOCATIONS:
        await callback.answer("Локация не найдена.", show_alert=True)
        return

    await callback.answer()
    await state.update_data(location_key=key)
    await state.set_state(CaptainFlow.code)
    await callback.message.answer(
        "<b>Архив услышал ваш шаг.</b>\n"
        "Введите знак, который передал Хранитель локации."
    )


@router.message(CaptainFlow.code)
async def location_code(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    key = data.get("location_key")
    user = await get_user(message.from_user.id)

    if not user or key not in LOCATIONS:
        await state.clear()
        await message.answer("Сессия устарела. Нажми «Следующая точка» ещё раз.")
        return

    exists = await db_one(
        """
        SELECT 1
        FROM team_choices
        WHERE event_date = ? AND team = ? AND location_key = ?
        """,
        (user["event_date"], user["team"], key),
    )
    if exists:
        await state.clear()
        await message.answer("Эта страница уже восстановлена вашей командой.")
        return

    entered = (message.text or "").strip().upper()
    if entered != str(LOCATIONS[key]["code"]).upper():
        await message.answer(
            "Архив не узнаёт этот знак. Проверь код у Хранителя локации."
        )
        return

    location = LOCATIONS[key]
    builder = InlineKeyboardBuilder()
    for choice_code, button_text, _, _ in location["choices"]:
        builder.button(
            text=button_text,
            callback_data=f"choice:{key}:{choice_code}",
        )
    builder.adjust(1)

    await state.set_state(CaptainFlow.confirm)
    await message.answer(
        f"{location['intro']}\n\n<b>{location['question']}</b>",
        reply_markup=builder.as_markup(),
    )


@router.callback_query(CaptainFlow.confirm, F.data.startswith("choice:"))
async def choose(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    _, key, choice_code = callback.data.split(":", 2)
    if key not in LOCATIONS:
        await state.clear()
        return

    choice = next(
        (item for item in LOCATIONS[key]["choices"] if item[0] == choice_code),
        None,
    )
    if not choice:
        await state.clear()
        return

    await state.update_data(location_key=key, choice_code=choice_code)
    await callback.message.edit_text(
        f"Вы выбрали: <b>{choice[1]}</b>\n\n"
        "Подтвердить решение команды?",
        reply_markup=inline_buttons(
            [
                ("Подтвердить", f"confirm:{key}:{choice_code}"),
                ("Изменить", f"redo:{key}"),
            ]
        ),
    )


@router.callback_query(CaptainFlow.confirm, F.data.startswith("redo:"))
async def redo_choice(callback: CallbackQuery) -> None:
    await callback.answer()
    key = callback.data.split(":", 1)[1]
    if key not in LOCATIONS:
        return

    builder = InlineKeyboardBuilder()
    for choice_code, button_text, _, _ in LOCATIONS[key]["choices"]:
        builder.button(
            text=button_text,
            callback_data=f"choice:{key}:{choice_code}",
        )
    builder.adjust(1)
    await callback.message.edit_text(
        f"<b>{LOCATIONS[key]['question']}</b>",
        reply_markup=builder.as_markup(),
    )


@router.callback_query(CaptainFlow.confirm, F.data.startswith("confirm:"))
async def confirm_choice(
    callback: CallbackQuery,
    state: FSMContext,
    bot: Bot,
) -> None:
    await callback.answer()
    _, key, choice_code = callback.data.split(":", 2)
    user = await get_user(callback.from_user.id)
    if not user or key not in LOCATIONS:
        await state.clear()
        return

    choice = next(
        (item for item in LOCATIONS[key]["choices"] if item[0] == choice_code),
        None,
    )
    if not choice:
        await state.clear()
        return

    try:
        await db_exec(
            """
            INSERT INTO team_choices(
                event_date, team, location_key, choice_code,
                selected_by, effects_json, created_at
            )
            VALUES(?, ?, ?, ?, ?, ?, ?)
            """,
            (
                user["event_date"],
                user["team"],
                key,
                choice_code,
                user["telegram_id"],
                json.dumps(choice[2], ensure_ascii=False),
                utcnow(),
            ),
        )
    except aiosqlite.IntegrityError:
        await state.clear()
        await callback.message.edit_text(
            "Эта страница уже восстановлена вашей командой."
        )
        return

    await state.clear()
    await callback.message.edit_text(choice[3])

    members = await db_all(
        """
        SELECT telegram_id
        FROM users
        WHERE event_date = ? AND team = ? AND telegram_id <> ?
        """,
        (user["event_date"], user["team"], user["telegram_id"]),
    )
    for member in members:
        try:
            await bot.send_message(
                member["telegram_id"],
                f"Команда приняла решение в локации "
                f"«{LOCATIONS[key]['title']}».\n\n{choice[3]}",
            )
        except Exception:
            log.exception("Could not notify team member %s", member["telegram_id"])


@router.message(F.text == "Состояние Архива")
async def archive_state(message: Message) -> None:
    user = await require_user(message)
    if not user:
        return

    parameters = await team_parameters(user)
    labels = {
        "memory": "Память",
        "truth": "Истина",
        "unity": "Связь голосов",
        "progress": "Прогресс",
        "responsibility": "Ответственность",
    }
    phrases = []
    for key, title in labels.items():
        value = parameters[key]
        state = (
            "укрепляется"
            if value >= 3
            else "остаётся хрупкой"
            if value <= 0
            else "обретает форму"
        )
        phrases.append(f"{title}: {state}.")
    await message.answer("<b>Состояние Архива</b>\n" + "\n".join(phrases))


@router.message(F.text == "Мои фрагменты")
async def fragments(message: Message) -> None:
    user = await require_user(message)
    if not user:
        return

    done = {
        row["location_key"]
        for row in await get_team_choices(user)
    }
    names = [
        ("culture", "Символ культуры"),
        ("science", "Печать открытия"),
        ("history", "Фрагмент времени"),
        ("memory", "Голос памяти"),
    ]
    content = "\n".join(
        f"{'✓' if key in done else '○'} {title}"
        for key, title in names
    )
    await message.answer(f"<b>Мешочек памяти</b>\n{content}")


@router.message(F.text == "Правила")
async def rules(message: Message) -> None:
    await message.answer(
        "1. Двигайся только со своей командой.\n"
        "2. Основные задания выполняются офлайн.\n"
        "3. Решение после локации фиксирует капитан.\n"
        "4. Ошибка не означает поражение: она меняет последствия."
    )


@router.message(F.text == "Позвать Архивариуса")
async def support(message: Message) -> None:
    user = await require_user(message)
    if not user:
        return

    await message.answer(
        "Что произошло?",
        reply_markup=inline_buttons(
            [
                ("Не могу найти локацию", "support:location"),
                ("Код не работает", "support:code"),
                ("Отстал от команды", "support:lost"),
                ("Плохо себя чувствую", "support:health"),
                ("Другой вопрос", "support:other"),
            ]
        ),
    )


@router.callback_query(F.data.startswith("support:"))
async def support_category(callback: CallbackQuery, state: FSMContext) -> None:
    user = await get_user(callback.from_user.id)
    if not user:
        await callback.answer("Сначала зарегистрируйся.", show_alert=True)
        return
    await callback.answer()
    await state.update_data(category=callback.data.split(":", 1)[1])
    await state.set_state(SupportFlow.text)
    await callback.message.answer(
        "Коротко опиши ситуацию. Сообщение уйдёт организаторам."
    )


@router.message(SupportFlow.text)
async def support_text(
    message: Message,
    state: FSMContext,
    bot: Bot,
) -> None:
    data = await state.get_data()
    user = await get_user(message.from_user.id)
    if not user:
        await state.clear()
        return

    category = data.get("category", "other")
    body = (message.text or "").strip()[:1000]
    await db_exec(
        """
        INSERT INTO support_requests(
            user_id, category, message, created_at
        )
        VALUES(?, ?, ?, ?)
        """,
        (message.from_user.id, category, body, utcnow()),
    )

    admin_message = (
        "<b>Новое обращение</b>\n"
        f"Участник: {html.escape(user['full_name'])}\n"
        f"Telegram: @{html.escape(user['username'] or 'нет username')}\n"
        f"День: {html.escape(user['event_date'])}\n"
        f"Команда: {html.escape(user['team'])}\n"
        f"Категория: {html.escape(category)}\n"
        f"Сообщение: {html.escape(body)}"
    )
    for admin_id in settings.admin_ids:
        try:
            await bot.send_message(admin_id, admin_message)
        except Exception:
            log.exception("Could not send support request to admin %s", admin_id)

    await state.clear()
    await message.answer(
        "Обращение передано Архивариусу.",
        reply_markup=main_menu(),
    )


@router.message(Command("admin"))
async def admin_panel(message: Message) -> None:
    if message.from_user.id not in settings.admin_ids:
        return

    users = await db_one("SELECT COUNT(*) AS total FROM users")
    requests = await db_one(
        "SELECT COUNT(*) AS total FROM support_requests WHERE status = 'open'"
    )
    teams_done = await db_one(
        """
        SELECT COUNT(*) AS total
        FROM (
            SELECT event_date, team, COUNT(*) AS amount
            FROM team_choices
            GROUP BY event_date, team
            HAVING amount = 4
        )
        """
    )
    await message.answer(
        "<b>Последний хранитель — панель</b>\n"
        f"Зарегистрировано: {users['total']}\n"
        f"Обращений без ответа: {requests['total']}\n"
        f"Команд завершили маршрут: {teams_done['total']}",
        reply_markup=inline_buttons(
            [
                ("Назначить капитана", "admin:captain"),
                ("Открыть финал", "admin:final"),
                ("Экспорт CSV", "admin:export"),
            ]
        ),
    )


@router.callback_query(F.data == "admin:captain")
async def admin_captain_help(callback: CallbackQuery) -> None:
    if callback.from_user.id not in settings.admin_ids:
        await callback.answer("Нет доступа.", show_alert=True)
        return
    await callback.answer()
    await callback.message.answer(
        "Назначение капитана:\n"
        "<code>/captain TELEGRAM_ID</code>\n\n"
        "Например: <code>/captain 123456789</code>"
    )


@router.message(Command("captain"))
async def set_captain(message: Message) -> None:
    if message.from_user.id not in settings.admin_ids:
        return

    parts = (message.text or "").split()
    if len(parts) != 2 or not parts[1].isdigit():
        await message.answer("Формат: /captain TELEGRAM_ID")
        return

    target_id = int(parts[1])
    user = await get_user(target_id)
    if not user:
        await message.answer("Участник с таким Telegram ID не зарегистрирован.")
        return

    await db_exec(
        "UPDATE users SET role = 'captain' WHERE telegram_id = ?",
        (target_id,),
    )
    await message.answer(
        f"Капитан назначен: {html.escape(user['full_name'])}, "
        f"команда {html.escape(user['team'])}."
    )


@router.callback_query(F.data == "admin:final")
async def admin_final(callback: CallbackQuery, bot: Bot) -> None:
    if callback.from_user.id not in settings.admin_ids:
        await callback.answer("Нет доступа.", show_alert=True)
        return

    await db_exec(
        "UPDATE settings SET value = '1' WHERE key = 'final_open'"
    )
    users = await db_all("SELECT * FROM users")
    sent = 0
    for user in users:
        try:
            choices = await get_team_choices(user)
            if len(choices) < 4:
                continue
            title, text = final_archetype(await team_parameters(user))
            await bot.send_message(
                user["telegram_id"],
                "<b>Архив собрал все ваши решения.</b>\n\n"
                f"Ваш итог: <b>{title}</b>\n{text}",
            )
            sent += 1
        except Exception:
            log.exception("Could not send final to %s", user["telegram_id"])

    await callback.answer(
        f"Финал открыт. Сообщений отправлено: {sent}",
        show_alert=True,
    )


@router.callback_query(F.data == "admin:export")
async def admin_export(callback: CallbackQuery) -> None:
    if callback.from_user.id not in settings.admin_ids:
        await callback.answer("Нет доступа.", show_alert=True)
        return

    await callback.answer()
    rows = await db_all(
        "SELECT * FROM users ORDER BY event_date, team, full_name"
    )
    stream = io.StringIO()
    writer = csv.writer(stream)
    fields = [
        "telegram_id",
        "username",
        "full_name",
        "age",
        "organization",
        "event_date",
        "team",
        "role",
        "checked_in",
    ]
    writer.writerow(fields)
    for row in rows:
        writer.writerow([row[field] for field in fields])

    await callback.message.answer_document(
        BufferedInputFile(
            stream.getvalue().encode("utf-8-sig"),
            filename="last_keeper_users.csv",
        )
    )


@router.message(Command("resetme"))
async def reset_me(message: Message, state: FSMContext) -> None:
    user = await get_user(message.from_user.id)
    if not user:
        await message.answer("Регистрация ещё не создана.")
        return
    await db_exec(
        "DELETE FROM users WHERE telegram_id = ?",
        (message.from_user.id,),
    )
    await state.clear()
    await message.answer(
        "Тестовая регистрация удалена. Отправь /start, чтобы пройти её заново."
    )


@router.message(Command("whoami"))
async def who_am_i(message: Message) -> None:
    user = await get_user(message.from_user.id)
    role = user["role"] if user else "не зарегистрирован"
    await message.answer(
        f"Telegram ID: <code>{message.from_user.id}</code>\n"
        f"Роль: {html.escape(role)}"
    )


bot: Bot | None = None
dispatcher: Dispatcher | None = None
bot_username = "unknown"


@asynccontextmanager
async def lifespan(_: FastAPI):
    global bot, dispatcher, bot_username

    if not settings.bot_token:
        raise RuntimeError("BOT_TOKEN is not configured")

    await init_db()
    bot = Bot(
        settings.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dispatcher = Dispatcher(storage=MemoryStorage())
    dispatcher.include_router(router)

    me = await bot.get_me()
    bot_username = me.username or "unknown"
    log.info("Telegram bot authenticated as @%s", bot_username)

    if settings.public_base_url:
        webhook_url = (
            f"{settings.public_base_url}/telegram/webhook/"
            f"{settings.webhook_secret}"
        )
        await bot.set_webhook(
            webhook_url,
            allowed_updates=dispatcher.resolve_used_update_types(),
            drop_pending_updates=False,
        )
        log.info("Webhook configured: %s", webhook_url)
    else:
        log.warning(
            "PUBLIC_BASE_URL/RENDER_EXTERNAL_URL is missing. "
            "Webhook was not configured."
        )

    try:
        yield
    finally:
        if dispatcher:
            await dispatcher.storage.close()
        if bot:
            await bot.session.close()


web = FastAPI(
    title="Last Keeper Telegram Bot",
    version="1.0.0",
    lifespan=lifespan,
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
)


@web.get("/")
@web.get("/health")
async def health() -> dict[str, str]:
    return {
        "status": "ok",
        "bot": bot_username,
        "mode": "webhook" if settings.public_base_url else "not-configured",
    }


@web.post("/telegram/webhook/{secret}")
async def telegram_webhook(secret: str, request: Request) -> dict[str, bool]:
    if secret != settings.webhook_secret:
        raise HTTPException(status_code=403, detail="Invalid webhook secret")
    if not bot or not dispatcher:
        raise HTTPException(status_code=503, detail="Bot is not ready")

    payload = await request.json()
    update = Update.model_validate(payload, context={"bot": bot})
    await dispatcher.feed_update(bot, update)
    return {"ok": True}


async def polling_main() -> None:
    if not settings.bot_token:
        raise RuntimeError("BOT_TOKEN is not configured")

    await init_db()
    local_bot = Bot(
        settings.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    local_dispatcher = Dispatcher(storage=MemoryStorage())
    local_dispatcher.include_router(router)
    await local_bot.delete_webhook(drop_pending_updates=False)

    me = await local_bot.get_me()
    log.info("Polling started for @%s", me.username)
    try:
        await local_dispatcher.start_polling(local_bot)
    finally:
        await local_dispatcher.storage.close()
        await local_bot.session.close()


if __name__ == "__main__":
    asyncio.run(polling_main())

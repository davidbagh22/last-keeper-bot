from __future__ import annotations

import asyncio
import logging
import os
from contextlib import asynccontextmanager, suppress
from typing import Any

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import Update
from fastapi import BackgroundTasks, FastAPI, Header, HTTPException, Request

import app as game

log = logging.getLogger("last_keeper.runtime")


def clean_token() -> str:
    # Удаляем случайные пробелы и переносы строк после вставки токена в Render.
    return "".join(os.getenv("BOT_TOKEN", "").split())


def external_url() -> str:
    return (
        os.getenv("PUBLIC_BASE_URL", "").strip()
        or os.getenv("RENDER_EXTERNAL_URL", "").strip()
    ).rstrip("/")


BOT_TOKEN = clean_token()
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "").strip()
WEBHOOK_PATH = "/telegram/webhook"

bot: Bot | None = None
dispatcher: Dispatcher | None = None
setup_task: asyncio.Task[None] | None = None
runtime: dict[str, Any] = {
    "status": "starting",
    "bot": None,
    "webhook": None,
    "error": None,
}


async def configure_telegram() -> None:
    """Авторизует бота и восстанавливает webhook, повторяя попытки после ошибок."""
    global bot, dispatcher

    if not BOT_TOKEN:
        runtime.update(status="missing-token", error="BOT_TOKEN is empty")
        return

    if not WEBHOOK_SECRET:
        runtime.update(status="missing-secret", error="WEBHOOK_SECRET is empty")
        return

    base_url = external_url()
    if not base_url:
        runtime.update(
            status="missing-url",
            error="RENDER_EXTERNAL_URL/PUBLIC_BASE_URL is empty",
        )
        return

    if bot is None:
        bot = Bot(
            BOT_TOKEN,
            default=DefaultBotProperties(parse_mode=ParseMode.HTML),
        )
    if dispatcher is None:
        dispatcher = Dispatcher(storage=MemoryStorage())
        dispatcher.include_router(game.router)

    webhook_url = f"{base_url}{WEBHOOK_PATH}"

    while True:
        try:
            me = await bot.get_me()
            # Перезаписываем любой старый webhook этого токена.
            await bot.delete_webhook(drop_pending_updates=False)
            await bot.set_webhook(
                webhook_url,
                secret_token=WEBHOOK_SECRET,
                allowed_updates=dispatcher.resolve_used_update_types(),
                drop_pending_updates=False,
            )
            info = await bot.get_webhook_info()
            if info.url != webhook_url:
                raise RuntimeError(
                    f"Telegram returned another webhook URL: {info.url!r}"
                )

            runtime.update(
                status="ok",
                bot=me.username,
                webhook=webhook_url,
                error=None,
            )
            log.info("Bot @%s is ready; webhook=%s", me.username, webhook_url)
            return
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            runtime.update(status="telegram-error", error=f"{type(exc).__name__}: {exc}")
            log.exception("Telegram setup failed; retrying in 20 seconds")
            await asyncio.sleep(20)


@asynccontextmanager
async def lifespan(_: FastAPI):
    global setup_task

    await game.init_db()
    setup_task = asyncio.create_task(configure_telegram())
    try:
        yield
    finally:
        if setup_task:
            setup_task.cancel()
            with suppress(asyncio.CancelledError):
                await setup_task
        if dispatcher:
            await dispatcher.storage.close()
        if bot:
            await bot.session.close()


web = FastAPI(
    title="Last Keeper Telegram Bot",
    version="1.1.0",
    lifespan=lifespan,
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
)


@web.get("/")
@web.get("/health")
async def health() -> dict[str, Any]:
    return runtime


@web.post(WEBHOOK_PATH)
async def telegram_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    secret: str | None = Header(
        default=None,
        alias="X-Telegram-Bot-Api-Secret-Token",
    ),
) -> dict[str, bool]:
    if not WEBHOOK_SECRET or secret != WEBHOOK_SECRET:
        raise HTTPException(status_code=403, detail="Invalid webhook secret")
    if runtime.get("status") != "ok" or not bot or not dispatcher:
        raise HTTPException(status_code=503, detail="Bot is not ready")

    payload = await request.json()
    update = Update.model_validate(payload, context={"bot": bot})
    background_tasks.add_task(dispatcher.feed_update, bot, update)
    return {"ok": True}

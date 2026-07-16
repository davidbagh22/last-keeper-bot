from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager, suppress
from typing import Any

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import BotCommand, BotCommandScopeChat, Update
from fastapi import BackgroundTasks, FastAPI, Header, HTTPException, Request

import admin_tools
import app as game
import expert_ux
from config import load_settings

settings = load_settings()
logging.basicConfig(
    level=getattr(logging, settings.log_level, logging.INFO),
    format='%(asctime)s | %(levelname)s | %(name)s | %(message)s',
)
log = logging.getLogger('last_keeper.runtime')

WEBHOOK_PATH = '/telegram/webhook'
bot: Bot | None = None
dispatcher: Dispatcher | None = None
setup_task: asyncio.Task[None] | None = None
runtime: dict[str, Any] = {'status': 'starting', 'bot': None, 'webhook': None, 'error': None}


async def configure_telegram() -> None:
    global bot, dispatcher
    if not settings.bot_token:
        runtime.update(status='missing-token', error='BOT_TOKEN is empty')
        return
    if not settings.public_base_url:
        runtime.update(status='missing-url', error='RENDER_EXTERNAL_URL/PUBLIC_BASE_URL is empty')
        return

    bot = Bot(settings.bot_token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dispatcher = Dispatcher(storage=MemoryStorage())
    # UX-слой подключается первым: он даёт понятный вход, короткие кнопки
    # и экспертное демо, затем управление получают игровые и админские сценарии.
    dispatcher.include_router(expert_ux.router)
    dispatcher.include_router(admin_tools.router)
    dispatcher.include_router(game.router)
    webhook_url = f'{settings.public_base_url}{WEBHOOK_PATH}'

    while True:
        try:
            me = await bot.get_me()
            await bot.delete_webhook(drop_pending_updates=False)
            await bot.set_webhook(
                webhook_url,
                secret_token=settings.webhook_secret,
                allowed_updates=dispatcher.resolve_used_update_types(),
                drop_pending_updates=False,
            )
            await bot.set_my_commands([
                BotCommand(command='start', description='Открыть Архив'),
                BotCommand(command='demo', description='Демо механики за 60 секунд'),
                BotCommand(command='guide', description='Как проходит игра'),
                BotCommand(command='program', description='Программа проекта'),
                BotCommand(command='progress', description='Мой путь и прогресс'),
                BotCommand(command='help', description='Помощь и правила'),
            ])
            admin_ids = settings.superadmin_ids | await game.database_admin_ids()
            for admin_id in admin_ids:
                with suppress(Exception):
                    await bot.set_my_commands([
                        BotCommand(command='start', description='Открыть Архив'),
                        BotCommand(command='demo', description='Экспертное демо'),
                        BotCommand(command='admin', description='Панель Архивариуса'),
                        BotCommand(command='whoami', description='Мой Telegram ID'),
                        BotCommand(command='cancel', description='Отменить действие'),
                    ], scope=BotCommandScopeChat(chat_id=admin_id))
            info = await bot.get_webhook_info()
            if info.url != webhook_url:
                raise RuntimeError(f'Telegram returned another webhook URL: {info.url!r}')
            runtime.update(status='ok', bot=me.username, webhook=webhook_url, error=None)
            log.info('Bot @%s is ready; webhook=%s', me.username, webhook_url)
            return
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            runtime.update(status='telegram-error', error=f'{type(exc).__name__}: {exc}')
            log.exception('Telegram setup failed; retrying in 20 seconds')
            await asyncio.sleep(20)


@asynccontextmanager
async def lifespan(_: FastAPI):
    global setup_task
    await game.init_application()
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
    title='Last Keeper Telegram Bot',
    version='2.2.0',
    lifespan=lifespan,
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
)


@web.get('/')
@web.get('/health')
async def health() -> dict[str, Any]:
    return runtime


@web.post(WEBHOOK_PATH)
async def telegram_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    secret: str | None = Header(default=None, alias='X-Telegram-Bot-Api-Secret-Token'),
) -> dict[str, bool]:
    if secret != settings.webhook_secret:
        raise HTTPException(status_code=403, detail='Invalid webhook secret')
    if runtime.get('status') != 'ok' or not bot or not dispatcher:
        raise HTTPException(status_code=503, detail='Bot is not ready')
    payload = await request.json()
    update = Update.model_validate(payload, context={'bot': bot})
    background_tasks.add_task(dispatcher.feed_update, bot, update)
    return {'ok': True}

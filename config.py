from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass


def _csv_ints(value: str) -> set[int]:
    return {int(item.strip()) for item in value.split(',') if item.strip().isdigit()}


def clean_token(value: str) -> str:
    return ''.join((value or '').split())


def safe_secret(value: str) -> str:
    raw = (value or 'last-keeper-webhook').encode('utf-8')
    return hashlib.sha256(raw).hexdigest()


@dataclass(frozen=True)
class Settings:
    bot_token: str
    superadmin_ids: set[int]
    database_path: str
    public_base_url: str
    webhook_secret: str
    event_dates: tuple[str, ...]
    team_capacity: int
    location_codes: dict[str, str]
    log_level: str


def load_settings() -> Settings:
    superadmins = _csv_ints(
        os.getenv('SUPERADMIN_IDS', '') or os.getenv('ADMIN_IDS', '1593868942')
    )
    dates = tuple(
        item.strip()
        for item in os.getenv('EVENT_DATES', '2026-11-16,2026-11-17').split(',')
        if item.strip()
    )
    return Settings(
        bot_token=clean_token(os.getenv('BOT_TOKEN', '')),
        superadmin_ids=superadmins,
        database_path=os.getenv('DATABASE_PATH', '/tmp/last_keeper.db'),
        public_base_url=(
            os.getenv('PUBLIC_BASE_URL', '').strip()
            or os.getenv('RENDER_EXTERNAL_URL', '').strip()
        ).rstrip('/'),
        webhook_secret=safe_secret(os.getenv('WEBHOOK_SECRET', '')),
        event_dates=dates,
        team_capacity=max(1, int(os.getenv('TEAM_CAPACITY', '30'))),
        location_codes={
            'culture': os.getenv('LOCATION_CODE_CULTURE', 'CULT26').strip().upper(),
            'science': os.getenv('LOCATION_CODE_SCIENCE', 'SCI26').strip().upper(),
            'history': os.getenv('LOCATION_CODE_HISTORY', 'HIST26').strip().upper(),
            'memory': os.getenv('LOCATION_CODE_MEMORY', 'MEM26').strip().upper(),
        },
        log_level=os.getenv('LOG_LEVEL', 'INFO').upper(),
    )

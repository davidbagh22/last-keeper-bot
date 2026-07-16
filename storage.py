from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import aiosqlite


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


class Database:
    def __init__(self, path: str):
        self.path = path
        self._write_lock = asyncio.Lock()

    async def _connect(self) -> aiosqlite.Connection:
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        db = await aiosqlite.connect(self.path, timeout=30)
        db.row_factory = aiosqlite.Row
        await db.execute('PRAGMA journal_mode=WAL')
        await db.execute('PRAGMA synchronous=NORMAL')
        await db.execute('PRAGMA busy_timeout=30000')
        await db.execute('PRAGMA foreign_keys=ON')
        return db

    async def init(self) -> None:
        statements = [
            '''CREATE TABLE IF NOT EXISTS users(
                telegram_id INTEGER PRIMARY KEY,
                username TEXT NOT NULL DEFAULT '',
                full_name TEXT NOT NULL,
                age INTEGER NOT NULL,
                organization TEXT NOT NULL DEFAULT '',
                event_date TEXT NOT NULL,
                team TEXT NOT NULL,
                role TEXT NOT NULL DEFAULT 'participant',
                status TEXT NOT NULL DEFAULT 'confirmed',
                consent_at TEXT NOT NULL,
                created_at TEXT NOT NULL
            )''',
            '''CREATE TABLE IF NOT EXISTS admin_users(
                telegram_id INTEGER PRIMARY KEY,
                added_by INTEGER NOT NULL,
                added_at TEXT NOT NULL
            )''',
            '''CREATE TABLE IF NOT EXISTS team_choices(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_date TEXT NOT NULL,
                team TEXT NOT NULL,
                location_key TEXT NOT NULL,
                choice_code TEXT NOT NULL,
                selected_by INTEGER NOT NULL,
                effects_json TEXT NOT NULL,
                immediate_text TEXT NOT NULL,
                hidden_text TEXT NOT NULL,
                video_symbol TEXT NOT NULL,
                narrator_hint TEXT NOT NULL,
                created_at TEXT NOT NULL,
                UNIQUE(event_date, team, location_key)
            )''',
            '''CREATE TABLE IF NOT EXISTS personal_progress(
                user_id INTEGER NOT NULL,
                location_key TEXT NOT NULL,
                attempts INTEGER NOT NULL DEFAULT 0,
                passed INTEGER NOT NULL DEFAULT 0,
                artifact TEXT NOT NULL DEFAULT '',
                completed_at TEXT,
                PRIMARY KEY(user_id, location_key)
            )''',
            '''CREATE TABLE IF NOT EXISTS route_marks(
                event_date TEXT NOT NULL,
                team TEXT NOT NULL,
                route_key TEXT NOT NULL,
                marked_by INTEGER NOT NULL,
                marked_at TEXT NOT NULL,
                PRIMARY KEY(event_date, team, route_key)
            )''',
            '''CREATE TABLE IF NOT EXISTS support_requests(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                category TEXT NOT NULL,
                message TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'open',
                answer TEXT NOT NULL DEFAULT '',
                answered_by INTEGER,
                created_at TEXT NOT NULL,
                answered_at TEXT
            )''',
            '''CREATE TABLE IF NOT EXISTS settings(
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )''',
            '''CREATE TABLE IF NOT EXISTS audit_logs(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                actor_id INTEGER NOT NULL,
                action TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                created_at TEXT NOT NULL
            )''',
            'CREATE INDEX IF NOT EXISTS idx_users_day_team ON users(event_date, team)',
            'CREATE INDEX IF NOT EXISTS idx_support_status ON support_requests(status, id)',
            'CREATE INDEX IF NOT EXISTS idx_choices_team ON team_choices(event_date, team)',
        ]
        async with self._write_lock:
            db = await self._connect()
            try:
                for statement in statements:
                    await db.execute(statement)
                await db.execute(
                    "INSERT OR IGNORE INTO settings(key, value) VALUES('game_status', 'open')"
                )
                await db.execute(
                    "INSERT OR IGNORE INTO settings(key, value) VALUES('final_open', '0')"
                )
                await db.commit()
            finally:
                await db.close()

    async def execute(self, query: str, params: Iterable[Any] = ()) -> None:
        async with self._write_lock:
            db = await self._connect()
            try:
                await db.execute(query, tuple(params))
                await db.commit()
            finally:
                await db.close()

    async def execute_returning_id(self, query: str, params: Iterable[Any] = ()) -> int:
        async with self._write_lock:
            db = await self._connect()
            try:
                cursor = await db.execute(query, tuple(params))
                await db.commit()
                return int(cursor.lastrowid)
            finally:
                await db.close()

    async def one(self, query: str, params: Iterable[Any] = ()) -> aiosqlite.Row | None:
        db = await self._connect()
        try:
            cursor = await db.execute(query, tuple(params))
            return await cursor.fetchone()
        finally:
            await db.close()

    async def all(self, query: str, params: Iterable[Any] = ()) -> list[aiosqlite.Row]:
        db = await self._connect()
        try:
            cursor = await db.execute(query, tuple(params))
            return list(await cursor.fetchall())
        finally:
            await db.close()

    async def setting(self, key: str, default: str = '') -> str:
        row = await self.one('SELECT value FROM settings WHERE key = ?', (key,))
        return row['value'] if row else default

    async def set_setting(self, key: str, value: str) -> None:
        await self.execute(
            '''INSERT INTO settings(key, value) VALUES(?, ?)
               ON CONFLICT(key) DO UPDATE SET value = excluded.value''',
            (key, value),
        )

    async def log(self, actor_id: int, action: str, payload: dict[str, Any] | None = None) -> None:
        await self.execute(
            'INSERT INTO audit_logs(actor_id, action, payload_json, created_at) VALUES(?, ?, ?, ?)',
            (actor_id, action, json.dumps(payload or {}, ensure_ascii=False), utcnow()),
        )

"""Работа с базой данных SQLite через aiosqlite."""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncIterator

import aiosqlite


# DDL для создания таблиц
_SCHEMA = """
CREATE TABLE IF NOT EXISTS projects (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT    NOT NULL,
    path        TEXT    NOT NULL,
    created_at  TEXT    NOT NULL DEFAULT (datetime('now')),
    settings_json TEXT  DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS repeater_entries (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id          INTEGER REFERENCES projects(id) ON DELETE CASCADE,
    tab_name            TEXT    NOT NULL DEFAULT 'Tab',
    method              TEXT    NOT NULL,
    url                 TEXT    NOT NULL,
    request_headers     TEXT    DEFAULT '',
    request_body        TEXT    DEFAULT '',
    response_status     INTEGER DEFAULT NULL,
    response_headers    TEXT    DEFAULT '',
    response_body       TEXT    DEFAULT '',
    timestamp           TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS intruder_results (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id          INTEGER REFERENCES projects(id) ON DELETE CASCADE,
    attack_id           TEXT    NOT NULL,
    payload_values      TEXT    DEFAULT '[]',
    request_raw         TEXT    DEFAULT '',
    response_status     INTEGER DEFAULT NULL,
    response_length     INTEGER DEFAULT NULL,
    response_time_ms    INTEGER DEFAULT NULL,
    error               TEXT    DEFAULT NULL,
    timestamp           TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS vulnerabilities (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id      INTEGER REFERENCES projects(id) ON DELETE CASCADE,
    type            TEXT    NOT NULL,
    name            TEXT    NOT NULL DEFAULT '',
    severity        TEXT    NOT NULL DEFAULT 'info',
    host            TEXT    NOT NULL,
    url             TEXT    NOT NULL,
    parameter       TEXT    DEFAULT '',
    payload         TEXT    DEFAULT '',
    evidence        TEXT    DEFAULT '',
    description     TEXT    DEFAULT '',
    cwe             TEXT    DEFAULT '',
    remediation     TEXT    DEFAULT '',
    mitre_attack    TEXT    DEFAULT '',
    request_raw     TEXT    DEFAULT '',
    response_raw    TEXT    DEFAULT '',
    false_positive  INTEGER NOT NULL DEFAULT 0,
    timestamp       TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS site_map (
    id              TEXT    PRIMARY KEY,
    host            TEXT    NOT NULL,
    path            TEXT    NOT NULL,
    methods         TEXT    NOT NULL DEFAULT '[]',
    request_count   INTEGER NOT NULL DEFAULT 0,
    last_seen       TEXT    NOT NULL,
    in_scope        INTEGER NOT NULL DEFAULT 0
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_site_map_host_path ON site_map (host, path);
"""


async def init_db(db_path: str) -> None:
    """Создать таблицы БД, если они не существуют.

    Args:
        db_path: Путь к файлу SQLite.
    """
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    async with aiosqlite.connect(db_path) as db:
        await db.executescript(_SCHEMA)
        await db.commit()
        # Миграция: добавляем новые колонки в vulnerabilities (для старых БД)
        _new_vuln_cols = [
            ("name",         "TEXT NOT NULL DEFAULT ''"),
            ("payload",      "TEXT DEFAULT ''"),
            ("description",  "TEXT DEFAULT ''"),
            ("cwe",          "TEXT DEFAULT ''"),
            ("remediation",  "TEXT DEFAULT ''"),
            ("mitre_attack", "TEXT DEFAULT ''"),
            ("request_raw",  "TEXT DEFAULT ''"),
            ("response_raw", "TEXT DEFAULT ''"),
        ]
        for col_name, col_def in _new_vuln_cols:
            try:
                await db.execute(
                    f"ALTER TABLE vulnerabilities ADD COLUMN {col_name} {col_def}"
                )
            except Exception:
                pass  # Колонка уже существует — ожидаемо
        await db.commit()


@asynccontextmanager
async def get_db(db_path: str) -> AsyncIterator[aiosqlite.Connection]:
    """Контекстный менеджер для получения соединения с БД.

    Args:
        db_path: Путь к файлу SQLite.

    Yields:
        Объект соединения aiosqlite.Connection.
    """
    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        await db.execute("PRAGMA foreign_keys = ON")
        yield db


def init_db_sync(db_path: str) -> None:
    """Синхронная обёртка над init_db для использования в CLI.

    Args:
        db_path: Путь к файлу SQLite.
    """
    asyncio.run(init_db(db_path))

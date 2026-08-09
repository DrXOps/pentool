"""SQLite database access via aiosqlite."""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncIterator

import aiosqlite

# DDL for table creation
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
    request_number      INTEGER NOT NULL DEFAULT 0,
    payload_values      TEXT    DEFAULT '[]',
    request_raw         TEXT    DEFAULT '',
    response_status     INTEGER DEFAULT NULL,
    response_length     INTEGER DEFAULT NULL,
    response_time_ms    INTEGER DEFAULT NULL,
    error               TEXT    DEFAULT NULL,
    timestamp           TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS intruder_state (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    tab_name        TEXT    NOT NULL DEFAULT 'Intruder',
    template        TEXT    NOT NULL DEFAULT '',
    attack_type     TEXT    NOT NULL DEFAULT 'sniper',
    payloads_json   TEXT    NOT NULL DEFAULT '[[]]',
    updated_at      TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS scanner_tabs (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    tab_uid     TEXT    NOT NULL DEFAULT '',
    tab_name    TEXT    NOT NULL DEFAULT 'Scan',
    target_url  TEXT    NOT NULL DEFAULT '',
    updated_at  TEXT    NOT NULL DEFAULT (datetime('now'))
);

-- NOTE: the unique index on scanner_tabs.tab_uid is NOT created here.
-- For a legacy DB (table already exists without the tab_uid column),
-- CREATE TABLE IF NOT EXISTS above is a no-op, so an index on tab_uid
-- run at this point would fail with "no such column: tab_uid" — the
-- ALTER TABLE migration that adds the column hasn't run yet (it runs
-- after this executescript, below). The index is created once, after
-- that migration, near the bottom of init_db().

CREATE TABLE IF NOT EXISTS vulnerabilities (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id      INTEGER REFERENCES projects(id) ON DELETE CASCADE,
    scan_tab_uid    TEXT    DEFAULT '',
    scan_session_id TEXT    DEFAULT '',
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

-- Generic per-project key/value settings (e.g. "proxy.enforce_scope").
-- Lives in the project .db file itself so it travels with the project,
-- unlike pentool's global ~/.config/pentool/config.yaml.
CREATE TABLE IF NOT EXISTS project_settings (
    key     TEXT PRIMARY KEY,
    value   TEXT NOT NULL DEFAULT ''
);
"""


async def init_db(db_path: str) -> None:
    """Create DB tables if they do not exist.

    Args:
        db_path: Path to the SQLite file.
    """
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    async with aiosqlite.connect(db_path) as db:
        await db.executescript(_SCHEMA)
        await db.commit()
        # Migration: add new columns to vulnerabilities (for old DBs)
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
                pass  # Column already exists — expected

        # Migration: add request_number to intruder_results (for old DBs)
        try:
            await db.execute(
                "ALTER TABLE intruder_results ADD COLUMN request_number INTEGER NOT NULL DEFAULT 0"
            )
        except Exception:
            pass  # Column already exists — expected

        # Migration: add response_raw to intruder_results (for detail panel)
        try:
            await db.execute(
                "ALTER TABLE intruder_results ADD COLUMN response_raw TEXT DEFAULT NULL"
            )
        except Exception:
            pass  # Column already exists — expected

        # Migration: add scan_tab_uid/scan_session_id to vulnerabilities (for
        # old DBs) — scopes findings to the scan tab/run that discovered them,
        # instead of every tab showing every finding ever saved to this DB.
        for col_name, col_def in (
            ("scan_tab_uid",    "TEXT DEFAULT ''"),
            ("scan_session_id", "TEXT DEFAULT ''"),
        ):
            try:
                await db.execute(
                    f"ALTER TABLE vulnerabilities ADD COLUMN {col_name} {col_def}"
                )
            except Exception:
                pass  # Column already exists — expected

        # Migration: add tab_uid to scanner_tabs (for old DBs) — stable
        # identity for a tab across app restarts, instead of upserting by
        # tab_name (which resets to "Scan 1", "Scan 2"... every restart and
        # can silently overwrite/merge a different tab's saved row).
        try:
            await db.execute(
                "ALTER TABLE scanner_tabs ADD COLUMN tab_uid TEXT DEFAULT ''"
            )
        except Exception:
            pass  # Column already exists — expected
        try:
            await db.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS idx_scanner_tabs_uid "
                "ON scanner_tabs (tab_uid)"
            )
        except Exception:
            pass

        await db.commit()


@asynccontextmanager
async def get_db(db_path: str) -> AsyncIterator[aiosqlite.Connection]:
    """Context manager for obtaining a DB connection.

    Args:
        db_path: Path to the SQLite file.

    Yields:
        aiosqlite.Connection object.
    """
    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        await db.execute("PRAGMA foreign_keys = ON")
        yield db


def init_db_sync(db_path: str) -> None:
    """Synchronous wrapper over init_db for use in CLI.

    Args:
        db_path: Path to the SQLite file.
    """
    asyncio.run(init_db(db_path))


async def get_project_setting(db_path: str, key: str, default: str | None = None) -> str | None:
    """Read a single per-project key/value setting from `project_settings`.

    Returns `default` if the key is missing or the table/column doesn't
    exist yet (e.g. a brand-new .db before init_db() has run).
    """
    try:
        async with aiosqlite.connect(db_path) as db:
            async with db.execute(
                "SELECT value FROM project_settings WHERE key = ?", (key,)
            ) as cur:
                row = await cur.fetchone()
                return row[0] if row else default
    except Exception:
        return default


async def set_project_setting(db_path: str, key: str, value: str) -> None:
    """Upsert a single per-project key/value setting into `project_settings`."""
    async with aiosqlite.connect(db_path) as db:
        await db.execute(
            "INSERT INTO project_settings (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value),
        )
        await db.commit()

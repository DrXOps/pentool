"""BaseSqliteStorage — shared persistent-connection lifecycle for SQLite storages.

Extracted from HttpStorage as part of the connection-consolidation effort
(see chat: "проблема с соединениями к БД" — вариант C, общий пул соединений).
Both `HttpStorage` (Proxy/History) and `IntruderRepository` (Intruder tab
state/results) inherit from this — each keeps ONE persistent aiosqlite
connection open for as long as the project is active, instead of opening
and closing a fresh connection on every single call (the old `get_db()`
pattern in core/database.py). That old pattern was the direct cause of an
Intruder crash: a fast attack calls `save_result()` per HTTP response —
thousands of times a second — and each call used to open+close its own
SQLite connection to the *same file* HttpStorage already holds open, which
starves out file descriptors / hits SQLite locking under load.

Two usage patterns are supported, matching the two different call styles
already present in the codebase:

- Explicit (HttpStorage-style): caller awaits `init_db(path)` once, then
  uses `self._db` directly. `ensure_open()` is a no-op once connected.
- Lazy (IntruderRepository-style): the object is constructed synchronously
  with `db_path` and methods are called directly with no explicit connect
  step — each public method calls `await self.ensure_open()` first, which
  opens the connection on first use and reuses it afterwards.
"""

from __future__ import annotations

from pathlib import Path

import aiosqlite

from pentool.core.logging import get_logger

logger = get_logger(__name__)


class BaseSqliteStorage:
    """Owns a single persistent aiosqlite connection to one project DB file."""

    def __init__(self, db_path: str | None = None) -> None:
        self._db: aiosqlite.Connection | None = None
        self._db_path: str = db_path or ""

    async def _connect(self, path: str) -> None:
        """Open the connection and apply the standard pragmas.

        Subclasses that need to create/migrate a schema should override
        `init_db()`, call `await super().init_db(path)` (or `_connect`
        directly) first, then run their `executescript`/migrations on
        `self._db`.
        """
        self._db_path = str(Path(path).expanduser())
        Path(self._db_path).parent.mkdir(parents=True, exist_ok=True)
        self._db = await aiosqlite.connect(self._db_path)
        self._db.row_factory = aiosqlite.Row
        await self._db.execute("PRAGMA foreign_keys = ON")
        await self._db.execute("PRAGMA journal_mode = WAL")
        await self._db.execute("PRAGMA busy_timeout = 5000")
        await self._db.commit()

    async def init_db(self, path: str) -> None:
        """Open/create the database. Base implementation just connects —
        subclasses override to add schema creation/migrations."""
        await self._connect(path)

    async def ensure_open(self) -> bool:
        """Lazily open the connection using `self._db_path` if not already
        open. Returns False (no-op) if there is no db_path to connect to —
        matches the historical "safe no-op when db_path is falsy" contract
        of callers like IntruderRepository.
        """
        if self._db is not None:
            return True
        if not self._db_path:
            return False
        await self.init_db(self._db_path)
        return True

    async def close(self) -> None:
        if self._db:
            await self._db.close()
            self._db = None

    async def switch_db(self, path: str) -> None:
        logger.info("%s: switch_db called for %s", type(self).__name__, path)
        await self.close()
        await self.init_db(path)

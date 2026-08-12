"""Unit tests: pentool/storage/base_sqlite_storage.py

Covers BaseSqliteStorage — the shared persistent-connection lifecycle
extracted out of HttpStorage so IntruderRepository (and future storages)
can reuse ONE aiosqlite connection for their whole lifetime instead of
opening/closing a fresh one on every call (the old core.database.get_db()
pattern, which caused a real crash under a fast Intruder attack — see
IntruderRepository's module docstring).
"""

from __future__ import annotations

from pathlib import Path

import aiosqlite
import pytest

from pentool.storage.base_sqlite_storage import BaseSqliteStorage


class TestInitAndConnect:
    @pytest.mark.asyncio
    async def test_init_db_creates_file(self, tmp_path: Path) -> None:
        storage = BaseSqliteStorage()
        db_path = str(tmp_path / "test.db")
        await storage.init_db(db_path)
        assert Path(db_path).exists()
        await storage.close()

    @pytest.mark.asyncio
    async def test_init_db_creates_parent_dirs(self, tmp_path: Path) -> None:
        storage = BaseSqliteStorage()
        db_path = str(tmp_path / "nested" / "dir" / "test.db")
        await storage.init_db(db_path)
        assert Path(db_path).exists()
        await storage.close()

    @pytest.mark.asyncio
    async def test_init_db_sets_db_path(self, tmp_path: Path) -> None:
        storage = BaseSqliteStorage()
        db_path = str(tmp_path / "test.db")
        await storage.init_db(db_path)
        assert storage._db_path == db_path
        await storage.close()

    @pytest.mark.asyncio
    async def test_init_db_opens_connection(self, tmp_path: Path) -> None:
        storage = BaseSqliteStorage()
        db_path = str(tmp_path / "test.db")
        await storage.init_db(db_path)
        assert isinstance(storage._db, aiosqlite.Connection)
        await storage.close()

    @pytest.mark.asyncio
    async def test_pragmas_applied(self, tmp_path: Path) -> None:
        """WAL journal mode and busy_timeout are set on connect."""
        storage = BaseSqliteStorage()
        db_path = str(tmp_path / "test.db")
        await storage.init_db(db_path)
        cur = await storage._db.execute("PRAGMA journal_mode")
        row = await cur.fetchone()
        assert row[0].lower() == "wal"
        cur = await storage._db.execute("PRAGMA busy_timeout")
        row = await cur.fetchone()
        assert row[0] == 5000
        await storage.close()


class TestClose:
    @pytest.mark.asyncio
    async def test_close_clears_connection(self, tmp_path: Path) -> None:
        storage = BaseSqliteStorage()
        await storage.init_db(str(tmp_path / "test.db"))
        await storage.close()
        assert storage._db is None

    @pytest.mark.asyncio
    async def test_close_when_never_opened_is_noop(self) -> None:
        storage = BaseSqliteStorage()
        await storage.close()  # should not raise
        assert storage._db is None


class TestSwitchDb:
    @pytest.mark.asyncio
    async def test_switch_db_closes_old_opens_new(self, tmp_path: Path) -> None:
        storage = BaseSqliteStorage()
        db1 = str(tmp_path / "a.db")
        db2 = str(tmp_path / "b.db")
        await storage.init_db(db1)
        first_conn = storage._db
        await storage.switch_db(db2)
        assert storage._db is not None
        assert storage._db is not first_conn
        assert storage._db_path == db2
        await storage.close()

    @pytest.mark.asyncio
    async def test_switch_db_data_isolated_per_file(self, tmp_path: Path) -> None:
        storage = BaseSqliteStorage()
        db1 = str(tmp_path / "a.db")
        db2 = str(tmp_path / "b.db")
        await storage.init_db(db1)
        await storage._db.execute("CREATE TABLE t (id INTEGER)")
        await storage._db.execute("INSERT INTO t VALUES (1)")
        await storage._db.commit()

        await storage.switch_db(db2)
        cur = await storage._db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='t'"
        )
        assert await cur.fetchone() is None
        await storage.close()


class TestEnsureOpen:
    @pytest.mark.asyncio
    async def test_ensure_open_noop_when_no_db_path(self) -> None:
        storage = BaseSqliteStorage(db_path=None)
        opened = await storage.ensure_open()
        assert opened is False
        assert storage._db is None

    @pytest.mark.asyncio
    async def test_ensure_open_connects_lazily(self, tmp_path: Path) -> None:
        db_path = str(tmp_path / "test.db")
        storage = BaseSqliteStorage(db_path=db_path)
        assert storage._db is None  # not connected yet — constructor is sync
        opened = await storage.ensure_open()
        assert opened is True
        assert storage._db is not None
        await storage.close()

    @pytest.mark.asyncio
    async def test_ensure_open_reuses_existing_connection(self, tmp_path: Path) -> None:
        """The key behavior this class exists for: repeated calls must NOT
        open a fresh connection each time — that per-call open/close was
        the root cause of the Intruder crash under load."""
        db_path = str(tmp_path / "test.db")
        storage = BaseSqliteStorage(db_path=db_path)
        await storage.ensure_open()
        conn_after_first = storage._db
        for _ in range(20):
            opened = await storage.ensure_open()
            assert opened is True
            assert storage._db is conn_after_first
        await storage.close()

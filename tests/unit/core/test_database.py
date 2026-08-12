"""Unit tests: core/database.py

Covers: init_db, get_db, DDL schema, tables.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import pytest_asyncio


class TestInitDb:
    @pytest.mark.asyncio
    async def test_creates_db_file(self, tmp_path: Path) -> None:
        from pentool.core.database import init_db
        db_path = str(tmp_path / "test.db")
        await init_db(db_path)
        assert Path(db_path).exists()

    @pytest.mark.asyncio
    async def test_creates_parent_directories(self, tmp_path: Path) -> None:
        from pentool.core.database import init_db
        db_path = str(tmp_path / "nested" / "dir" / "test.db")
        await init_db(db_path)
        assert Path(db_path).exists()

    @pytest.mark.asyncio
    async def test_creates_projects_table(self, tmp_path: Path) -> None:
        from pentool.core.database import init_db, get_db
        db_path = str(tmp_path / "test.db")
        await init_db(db_path)

        async with get_db(db_path) as db:
            cursor = await db.execute(
                "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
            )
            tables = {row[0] for row in await cursor.fetchall()}

        assert "projects" in tables

    @pytest.mark.asyncio
    async def test_creates_repeater_entries_table(self, tmp_path: Path) -> None:
        from pentool.core.database import init_db, get_db
        db_path = str(tmp_path / "test.db")
        await init_db(db_path)

        async with get_db(db_path) as db:
            cursor = await db.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
            tables = {row[0] for row in await cursor.fetchall()}

        assert "repeater_entries" in tables

    @pytest.mark.asyncio
    async def test_creates_intruder_results_table(self, tmp_path: Path) -> None:
        from pentool.core.database import init_db, get_db
        db_path = str(tmp_path / "test.db")
        await init_db(db_path)

        async with get_db(db_path) as db:
            cursor = await db.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
            tables = {row[0] for row in await cursor.fetchall()}

        assert "intruder_results" in tables

    @pytest.mark.asyncio
    async def test_idempotent_multiple_calls(self, tmp_path: Path) -> None:
        """Repeated call to init_db does not raise errors."""
        from pentool.core.database import init_db
        db_path = str(tmp_path / "test.db")
        await init_db(db_path)
        await init_db(db_path)  # second call — no errors

    @pytest.mark.asyncio
    async def test_tables_initially_empty(self, tmp_path: Path) -> None:
        from pentool.core.database import init_db, get_db
        db_path = str(tmp_path / "test.db")
        await init_db(db_path)

        async with get_db(db_path) as db:
            cursor = await db.execute("SELECT COUNT(*) FROM projects")
            count = (await cursor.fetchone())[0]

        assert count == 0


class TestGetDb:
    @pytest.mark.asyncio
    async def test_context_manager_yields_connection(self, tmp_path: Path) -> None:
        from pentool.core.database import init_db, get_db
        import aiosqlite
        db_path = str(tmp_path / "test.db")
        await init_db(db_path)

        async with get_db(db_path) as db:
            assert isinstance(db, aiosqlite.Connection)

    @pytest.mark.asyncio
    async def test_can_insert_and_select(self, tmp_path: Path) -> None:
        from pentool.core.database import init_db, get_db
        db_path = str(tmp_path / "test.db")
        await init_db(db_path)

        async with get_db(db_path) as db:
            await db.execute(
                "INSERT INTO projects (name, path) VALUES (?, ?)",
                ("TestProject", "/tmp/test"),
            )
            await db.commit()
            cursor = await db.execute("SELECT name FROM projects")
            row = await cursor.fetchone()

        assert row[0] == "TestProject"

    @pytest.mark.asyncio
    async def test_foreign_key_cascade(self, tmp_path: Path) -> None:
        """Deleting a project → cascades to delete repeater_entries."""
        from pentool.core.database import init_db, get_db
        db_path = str(tmp_path / "test.db")
        await init_db(db_path)

        async with get_db(db_path) as db:
            await db.execute("PRAGMA foreign_keys = ON")
            await db.execute(
                "INSERT INTO projects (name, path) VALUES (?, ?)", ("P", "/p")
            )
            cursor = await db.execute("SELECT id FROM projects WHERE name='P'")
            project_id = (await cursor.fetchone())[0]

            await db.execute(
                "INSERT INTO repeater_entries (project_id, method, url, tab_name) VALUES (?, ?, ?, ?)",
                (project_id, "GET", "http://example.com", "Tab 1"),
            )
            await db.execute("DELETE FROM projects WHERE id=?", (project_id,))
            await db.commit()

            cursor = await db.execute(
                "SELECT COUNT(*) FROM repeater_entries WHERE project_id=?", (project_id,)
            )
            count = (await cursor.fetchone())[0]

        assert count == 0


class TestScannerTabsSchema:
    """scanner_tabs.tab_uid — stable identity for a Scanner tab.

    Introduced to replace upserting by tab_name (cosmetic, resets every
    app restart) which could silently merge/overwrite an unrelated tab's
    saved row across restarts.
    """

    @pytest.mark.asyncio
    async def test_scanner_tabs_has_tab_uid_column(self, tmp_path: Path) -> None:
        from pentool.core.database import init_db, get_db
        db_path = str(tmp_path / "test.db")
        await init_db(db_path)

        async with get_db(db_path) as db:
            cursor = await db.execute("PRAGMA table_info(scanner_tabs)")
            cols = {row[1] for row in await cursor.fetchall()}

        assert "tab_uid" in cols

    @pytest.mark.asyncio
    async def test_tab_uid_unique_index_enforced(self, tmp_path: Path) -> None:
        """Inserting two rows with the same tab_uid must fail — upsert-by-uid
        (ScannerAPI.save_tab) relies on this to detect existing vs new rows."""
        from pentool.core.database import init_db, get_db
        import aiosqlite
        db_path = str(tmp_path / "test.db")
        await init_db(db_path)

        async with get_db(db_path) as db:
            await db.execute(
                "INSERT INTO scanner_tabs (tab_uid, tab_name, target_url) "
                "VALUES ('uid-1', 'Scan 1', 'http://a.com')"
            )
            await db.commit()
            with pytest.raises(aiosqlite.IntegrityError):
                await db.execute(
                    "INSERT INTO scanner_tabs (tab_uid, tab_name, target_url) "
                    "VALUES ('uid-1', 'Scan 2', 'http://b.com')"
                )

    @pytest.mark.asyncio
    async def test_migration_adds_tab_uid_to_legacy_table(self, tmp_path: Path) -> None:
        """A pre-migration scanner_tabs table (no tab_uid column) gets the
        column added by init_db()'s ALTER TABLE migration, without losing
        existing rows."""
        from pentool.core.database import init_db, get_db
        import aiosqlite
        db_path = str(tmp_path / "test.db")

        # Simulate an old DB: create scanner_tabs without tab_uid.
        async with aiosqlite.connect(db_path) as db:
            await db.execute(
                """CREATE TABLE scanner_tabs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    tab_name TEXT NOT NULL DEFAULT 'Scan',
                    target_url TEXT NOT NULL DEFAULT '',
                    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
                )"""
            )
            await db.execute(
                "INSERT INTO scanner_tabs (tab_name, target_url) VALUES ('Old Scan', 'http://old.com')"
            )
            await db.commit()

        # init_db() should migrate it in place.
        await init_db(db_path)

        async with get_db(db_path) as db:
            cursor = await db.execute("PRAGMA table_info(scanner_tabs)")
            cols = {row[1] for row in await cursor.fetchall()}
            assert "tab_uid" in cols

            cursor = await db.execute("SELECT tab_name, target_url FROM scanner_tabs")
            row = await cursor.fetchone()
            assert tuple(row) == ("Old Scan", "http://old.com")


class TestProjectSettings:
    """project_settings — generic per-project key/value store.

    Used for "proxy.enforce_scope" (bool as "0"/"1") and, since the
    "Scope host list stops working after reopening an older project" fix,
    also "proxy.scope" (JSON-encoded host list) — both must round-trip
    per-project instead of leaking through the global Config.
    """

    @pytest.mark.asyncio
    async def test_set_then_get_roundtrip(self, tmp_path: Path) -> None:
        from pentool.core.database import init_db, get_project_setting, set_project_setting
        db_path = str(tmp_path / "test.db")
        await init_db(db_path)

        await set_project_setting(db_path, "proxy.enforce_scope", "1")
        value = await get_project_setting(db_path, "proxy.enforce_scope", "0")

        assert value == "1"

    @pytest.mark.asyncio
    async def test_get_missing_key_returns_default(self, tmp_path: Path) -> None:
        from pentool.core.database import init_db, get_project_setting
        db_path = str(tmp_path / "test.db")
        await init_db(db_path)

        value = await get_project_setting(db_path, "proxy.scope", None)

        assert value is None

    @pytest.mark.asyncio
    async def test_upsert_overwrites_existing_value(self, tmp_path: Path) -> None:
        from pentool.core.database import init_db, get_project_setting, set_project_setting
        db_path = str(tmp_path / "test.db")
        await init_db(db_path)

        await set_project_setting(db_path, "proxy.enforce_scope", "1")
        await set_project_setting(db_path, "proxy.enforce_scope", "0")
        value = await get_project_setting(db_path, "proxy.enforce_scope", None)

        assert value == "0"

    @pytest.mark.asyncio
    async def test_scope_json_roundtrip(self, tmp_path: Path) -> None:
        """proxy.scope stores a JSON-encoded host list — the exact mechanism
        ProxyScreen._save_scope_setting/_load_scope_setting use so the Scope
        host list is restored per-project instead of from the global Config
        (which used to go stale after switching projects)."""
        import json
        from pentool.core.database import init_db, get_project_setting, set_project_setting
        db_path = str(tmp_path / "test.db")
        await init_db(db_path)

        hosts = ["example.com", "*.internal.test"]
        await set_project_setting(db_path, "proxy.scope", json.dumps(hosts))
        raw = await get_project_setting(db_path, "proxy.scope", None)

        assert raw is not None
        assert json.loads(raw) == hosts

    @pytest.mark.asyncio
    async def test_settings_isolated_per_db_file(self, tmp_path: Path) -> None:
        """Two different project .db files must not share project_settings
        rows — each project's Scope/enforce_scope is independent."""
        from pentool.core.database import init_db, get_project_setting, set_project_setting
        db_a = str(tmp_path / "a.db")
        db_b = str(tmp_path / "b.db")
        await init_db(db_a)
        await init_db(db_b)

        await set_project_setting(db_a, "proxy.enforce_scope", "1")

        value_a = await get_project_setting(db_a, "proxy.enforce_scope", "0")
        value_b = await get_project_setting(db_b, "proxy.enforce_scope", "0")

        assert value_a == "1"
        assert value_b == "0"


class TestVulnerabilitiesScopingSchema:
    """vulnerabilities.scan_tab_uid / scan_session_id — scope findings to
    the Scanner tab/run that discovered them, instead of every tab showing
    every finding ever saved to the project DB."""

    @pytest.mark.asyncio
    async def test_vulnerabilities_has_scoping_columns(self, tmp_path: Path) -> None:
        from pentool.core.database import init_db, get_db
        db_path = str(tmp_path / "test.db")
        await init_db(db_path)

        async with get_db(db_path) as db:
            cursor = await db.execute("PRAGMA table_info(vulnerabilities)")
            cols = {row[1] for row in await cursor.fetchall()}

        assert "scan_tab_uid" in cols
        assert "scan_session_id" in cols

    @pytest.mark.asyncio
    async def test_migration_adds_scoping_columns_to_legacy_table(self, tmp_path: Path) -> None:
        """A pre-migration vulnerabilities table (no scan_tab_uid/
        scan_session_id) gets both columns added without losing rows."""
        from pentool.core.database import init_db, get_db
        import aiosqlite
        db_path = str(tmp_path / "test.db")

        async with aiosqlite.connect(db_path) as db:
            await db.execute(
                """CREATE TABLE vulnerabilities (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    type TEXT NOT NULL,
                    severity TEXT NOT NULL DEFAULT 'info',
                    host TEXT NOT NULL,
                    url TEXT NOT NULL
                )"""
            )
            await db.execute(
                "INSERT INTO vulnerabilities (type, severity, host, url) "
                "VALUES ('xss', 'high', 'old.com', 'http://old.com/x')"
            )
            await db.commit()

        await init_db(db_path)

        async with get_db(db_path) as db:
            cursor = await db.execute("PRAGMA table_info(vulnerabilities)")
            cols = {row[1] for row in await cursor.fetchall()}
            assert "scan_tab_uid" in cols
            assert "scan_session_id" in cols

            cursor = await db.execute("SELECT type, url FROM vulnerabilities")
            row = await cursor.fetchone()
            assert tuple(row) == ("xss", "http://old.com/x")

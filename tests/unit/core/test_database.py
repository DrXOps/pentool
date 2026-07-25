"""Unit-тесты: core/database.py

Покрывает: init_db, get_db, DDL-схема, таблицы.
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
        """Повторный вызов init_db не бросает ошибок."""
        from pentool.core.database import init_db
        db_path = str(tmp_path / "test.db")
        await init_db(db_path)
        await init_db(db_path)  # второй вызов — нет ошибок

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
        """Удаление проекта → каскадное удаление repeater_entries."""
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

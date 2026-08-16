"""Unit tests for pentool/api/intruder_storage.py.

Regression coverage for the extraction done in
MYPLANS/ARCHITECTURE_REFACTOR_PLAN_2026-08-09.md section 2.6 —
IntruderStorage now owns the SQL that used to live directly on
IntruderAPI (save_state/load_state/save_result/get_results_from_db).
IntruderAPI keeps identical public method names delegating to this class.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest
import pytest_asyncio

from pentool.modules.intruder import IntruderResult


@pytest_asyncio.fixture
async def db_path(tmp_path: Path) -> str:
    from pentool.core.db_schema import init_db
    path = str(tmp_path / "test.db")
    await init_db(path)
    return path


@pytest_asyncio.fixture
async def repo(db_path):
    from pentool.api.intruder_storage import IntruderStorage
    r = IntruderStorage(db_path=db_path)
    yield r
    # IntruderStorage now holds a persistent aiosqlite connection (see
    # BaseSqliteStorage) instead of the old open/close-per-call get_db()
    # pattern — must be closed explicitly or its background thread leaks
    # past the test (PytestUnhandledThreadExceptionWarning on teardown).
    await r.close()


def _make_result(attack_id: str = "atk-1", request_number: int = 1) -> IntruderResult:
    return IntruderResult(
        id="r1",
        attack_id=attack_id,
        request_number=request_number,
        payload_values=["admin", "1234"],
        request_raw="GET / HTTP/1.1\r\n\r\n",
        response_raw="HTTP/1.1 200 OK\r\n\r\nok",
        response_status=200,
        response_length=2,
        response_time_ms=15,
        error=None,
        timestamp=datetime.now(timezone.utc),
    )


class TestNoDbPath:
    """All methods must be safe no-ops when db_path is falsy — matches the
    original IntruderAPI behavior (many callers construct IntruderAPI()
    with no project open yet)."""

    @pytest.mark.asyncio
    async def test_save_state_noop(self):
        from pentool.api.intruder_storage import IntruderStorage
        repo = IntruderStorage(db_path=None)
        await repo.save_state("tab", "template", "sniper", [["a"]])  # should not raise

    @pytest.mark.asyncio
    async def test_load_state_returns_none(self):
        from pentool.api.intruder_storage import IntruderStorage
        repo = IntruderStorage(db_path=None)
        assert await repo.load_state("tab") is None

    @pytest.mark.asyncio
    async def test_save_result_noop(self):
        from pentool.api.intruder_storage import IntruderStorage
        repo = IntruderStorage(db_path=None)
        await repo.save_result(_make_result())  # should not raise

    @pytest.mark.asyncio
    async def test_get_results_returns_empty(self):
        from pentool.api.intruder_storage import IntruderStorage
        repo = IntruderStorage(db_path=None)
        assert await repo.get_results() == []


class TestStatePersistence:
    @pytest.mark.asyncio
    async def test_save_and_load_state(self, repo):
        await repo.save_state("Tab 1", "GET /?id=§1§", "sniper", [["1", "2"]])
        state = await repo.load_state("Tab 1")
        assert state is not None
        assert state["template"] == "GET /?id=§1§"
        assert state["attack_type"] == "sniper"
        assert state["payloads"] == [["1", "2"]]

    @pytest.mark.asyncio
    async def test_load_state_unknown_tab_returns_none(self, repo):
        assert await repo.load_state("nonexistent") is None

    @pytest.mark.asyncio
    async def test_save_state_overwrites_previous(self, repo):
        await repo.save_state("Tab 1", "old", "sniper", [["a"]])
        await repo.save_state("Tab 1", "new", "cluster_bomb", [["b"]])
        state = await repo.load_state("Tab 1")
        assert state["template"] == "new"
        assert state["attack_type"] == "cluster_bomb"


class TestResultPersistence:
    @pytest.mark.asyncio
    async def test_save_and_get_results(self, repo):
        result = _make_result()
        await repo.save_result(result)
        results = await repo.get_results()
        assert len(results) == 1
        assert results[0].attack_id == "atk-1"
        assert results[0].payload_values == ["admin", "1234"]
        assert results[0].response_status == 200

    @pytest.mark.asyncio
    async def test_get_results_filters_by_attack_id(self, repo):
        await repo.save_result(_make_result(attack_id="atk-1", request_number=1))
        await repo.save_result(_make_result(attack_id="atk-2", request_number=1))
        results = await repo.get_results(attack_id="atk-1")
        assert len(results) == 1
        assert results[0].attack_id == "atk-1"

    @pytest.mark.asyncio
    async def test_get_results_respects_limit(self, repo):
        for i in range(5):
            await repo.save_result(_make_result(request_number=i))
        results = await repo.get_results(limit=2)
        assert len(results) == 2

    @pytest.mark.asyncio
    async def test_get_results_ordered_by_request_number_within_attack(self, repo):
        await repo.save_result(_make_result(attack_id="atk-1", request_number=3))
        await repo.save_result(_make_result(attack_id="atk-1", request_number=1))
        await repo.save_result(_make_result(attack_id="atk-1", request_number=2))
        results = await repo.get_results(attack_id="atk-1")
        assert [r.request_number for r in results] == [1, 2, 3]


class TestPersistentConnection:
    """Regression coverage for the connection-consolidation fix.

    IntruderStorage used to open a brand-new aiosqlite connection (via
    core.db_schema.get_db()) on every single call — save_result() is called
    once per HTTP response during an attack, so a fast attack opened/closed
    thousands of connections a second to the same file HttpStorage already
    holds open, which crashed under load. IntruderStorage now inherits
    BaseSqliteStorage: one connection, opened lazily on first use via
    ensure_open(), reused for the object's lifetime.
    """

    @pytest.mark.asyncio
    async def test_repeated_calls_reuse_same_connection(self, repo):
        await repo.save_result(_make_result(request_number=1))
        conn_after_first = repo._db
        assert conn_after_first is not None

        for i in range(2, 22):
            await repo.save_result(_make_result(request_number=i))
            assert repo._db is conn_after_first

        results = await repo.get_results(limit=100)
        assert len(results) == 21
        assert repo._db is conn_after_first

    @pytest.mark.asyncio
    async def test_switch_db_moves_to_new_file(self, tmp_path: Path):
        from pentool.api.intruder_storage import IntruderStorage
        from pentool.core.db_schema import init_db

        db1 = str(tmp_path / "a.db")
        db2 = str(tmp_path / "b.db")
        await init_db(db1)
        await init_db(db2)

        repo = IntruderStorage(db_path=db1)
        try:
            await repo.save_result(_make_result(attack_id="atk-a"))
            assert len(await repo.get_results()) == 1

            await repo.switch_db(db2)
            assert repo._db_path == db2
            # New file is empty — old attack's result did not follow the switch
            assert await repo.get_results() == []

            await repo.save_result(_make_result(attack_id="atk-b"))
            results = await repo.get_results()
            assert len(results) == 1
            assert results[0].attack_id == "atk-b"
        finally:
            await repo.close()

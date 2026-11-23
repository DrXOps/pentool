"""Tests for IntruderStorage.get_results/count_results with FilterSpec.

Verifies that the SQL WHERE clause is built correctly for intruder_results fields:
  - response_status (int)
  - response_length (int)
  - error (str | None)
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone

import aiosqlite
import pytest

from pentool.api.intruder_storage import IntruderStorage
from pentool.collections.filter_predicate import FilterOp, FilterPredicate, FilterSpec
from pentool.modules.intruder import IntruderResult

_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS intruder_results (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id          INTEGER,
    attack_id           TEXT    NOT NULL,
    request_number      INTEGER NOT NULL DEFAULT 0,
    payload_values      TEXT    DEFAULT '[]',
    request_raw         TEXT    DEFAULT '',
    response_status     INTEGER DEFAULT NULL,
    response_length     INTEGER DEFAULT NULL,
    response_time_ms    INTEGER DEFAULT NULL,
    response_raw        TEXT    DEFAULT '',
    error               TEXT    DEFAULT NULL,
    timestamp           TEXT    NOT NULL DEFAULT (datetime('now')),
    tab_uid             TEXT    DEFAULT ''
);
"""


def _run(coro):
    """Helper: run async in fixture."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


async def _init_schema(db_path: str) -> None:
    async with aiosqlite.connect(db_path) as db:
        await db.execute(_SCHEMA_SQL)
        await db.commit()


@pytest.fixture
def storage(tmp_path):
    """Creates an IntruderStorage with a temporary DB (schema + data)."""
    db_path = str(tmp_path / "test_intruder.db")
    s = IntruderStorage(db_path=db_path)
    _run(s.init_db(db_path))
    _run(_init_schema(db_path))

    # Add test results
    results = [
        IntruderResult(
            id="1",
            attack_id="a1",
            request_number=1,
            payload_values=["admin"],
            request_raw="",
            response_raw="",
            response_status=200,
            response_length=100,
            response_time_ms=10,
            error="",
            timestamp=datetime.now(timezone.utc),
        ),
        IntruderResult(
            id="2",
            attack_id="a1",
            request_number=2,
            payload_values=["test"],
            request_raw="",
            response_raw="",
            response_status=404,
            response_length=50,
            response_time_ms=5,
            error="Not Found",
            timestamp=datetime.now(timezone.utc),
        ),
        IntruderResult(
            id="3",
            attack_id="a1",
            request_number=3,
            payload_values=["root"],
            request_raw="",
            response_raw="",
            response_status=200,
            response_length=200,
            response_time_ms=15,
            error="",
            timestamp=datetime.now(timezone.utc),
        ),
        IntruderResult(
            id="4",
            attack_id="a2",
            request_number=1,
            payload_values=["sql"],
            request_raw="",
            response_raw="",
            response_status=500,
            response_length=300,
            response_time_ms=20,
            error="Server Error",
            timestamp=datetime.now(timezone.utc),
        ),
    ]

    for r in results:
        _run(s.save_result(r))

    yield s

    _run(s.close())


@pytest.mark.asyncio
async def test_get_results_no_filter(storage):
    """No filter — all results."""
    results = await storage.get_results(limit=100)
    assert len(results) == 4


@pytest.mark.asyncio
async def test_get_results_status_eq(storage):
    """status=200 — 2 results."""
    spec = FilterSpec(
        predicates=[
            FilterPredicate("response_status", FilterOp.EQ, 200),
        ]
    )
    results = await storage.get_results(limit=100, filters=spec)
    assert len(results) == 2
    for r in results:
        assert r.response_status == 200


@pytest.mark.asyncio
async def test_get_results_status_between(storage):
    """status BETWEEN 200 AND 300 — 2 results."""
    spec = FilterSpec(
        predicates=[
            FilterPredicate("response_status", FilterOp.BETWEEN, (200, 300)),
        ]
    )
    results = await storage.get_results(limit=100, filters=spec)
    assert len(results) == 2
    for r in results:
        assert 200 <= r.response_status <= 300


@pytest.mark.asyncio
async def test_get_results_length_gt(storage):
    """length > 100 — 2 results."""
    spec = FilterSpec(
        predicates=[
            FilterPredicate("response_length", FilterOp.GT, 100),
        ]
    )
    results = await storage.get_results(limit=100, filters=spec)
    assert len(results) == 2
    for r in results:
        assert r.response_length > 100


@pytest.mark.asyncio
async def test_get_results_length_lt(storage):
    """length < 100 — 1 result."""
    spec = FilterSpec(
        predicates=[
            FilterPredicate("response_length", FilterOp.LT, 100),
        ]
    )
    results = await storage.get_results(limit=100, filters=spec)
    assert len(results) == 1
    assert results[0].response_length < 100


@pytest.mark.asyncio
async def test_get_results_combined_status_and_length(storage):
    """status=200 AND length > 150 — 1 result."""
    spec = FilterSpec(
        predicates=[
            FilterPredicate("response_status", FilterOp.EQ, 200),
            FilterPredicate("response_length", FilterOp.GT, 150),
        ]
    )
    results = await storage.get_results(limit=100, filters=spec)
    assert len(results) == 1
    assert results[0].response_status == 200
    assert results[0].response_length > 150


@pytest.mark.asyncio
async def test_get_results_attack_id_and_filter(storage):
    """attack_id + filter — combined WHERE."""
    spec = FilterSpec(
        predicates=[
            FilterPredicate("response_status", FilterOp.EQ, 200),
        ]
    )
    results = await storage.get_results(attack_id="a1", limit=100, filters=spec)
    # a1 has status=200 for id 1 and 3, but the filter keeps only 200
    assert len(results) == 2
    for r in results:
        assert r.attack_id == "a1"
        assert r.response_status == 200


@pytest.mark.asyncio
async def test_count_results_no_filter(storage):
    total = await storage.count_results()
    assert total == 4


@pytest.mark.asyncio
async def test_count_results_with_filter(storage):
    spec = FilterSpec(
        predicates=[
            FilterPredicate("response_status", FilterOp.EQ, 404),
        ]
    )
    total = await storage.count_results(filters=spec)
    assert total == 1


@pytest.mark.asyncio
async def test_count_results_attack_id_and_filter(storage):
    spec = FilterSpec(
        predicates=[
            FilterPredicate("response_length", FilterOp.GT, 100),
        ]
    )
    total = await storage.count_results(attack_id="a1", filters=spec)
    # a1: length > 100 = id3 (200) — 1 result
    assert total == 1


@pytest.mark.asyncio
async def test_get_results_empty_filter(storage):
    """Empty FilterSpec — all results (equivalent to None)."""
    spec = FilterSpec()
    results = await storage.get_results(limit=100, filters=spec)
    assert len(results) == 4


@pytest.mark.asyncio
async def test_get_results_no_match(storage):
    """The filter yields no results."""
    spec = FilterSpec(
        predicates=[
            FilterPredicate("response_status", FilterOp.EQ, 999),
        ]
    )
    results = await storage.get_results(limit=100, filters=spec)
    assert len(results) == 0

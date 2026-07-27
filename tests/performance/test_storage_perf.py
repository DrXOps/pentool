"""Performance: HttpStorage insert/query throughput."""
from __future__ import annotations

import asyncio
import time

import pytest
import pytest_asyncio

from pentool.storage.http_storage import HttpStorage
from pentool.utils.parser import ParsedRequest, ParsedResponse


@pytest_asyncio.fixture
async def storage(tmp_path):
    s = HttpStorage()
    await s.init_db(str(tmp_path / "perf_test.db"))
    yield s
    await s.close()


def _make_pair(i: int):
    req = ParsedRequest(
        method="GET",
        url=f"http://host{i}.example.com/path?q={i}",
        headers={"Host": f"host{i}.example.com"},
    )
    resp = ParsedResponse(
        status=200,
        reason="OK",
        headers={"Content-Type": "text/html"},
        body=f"body-{i}",
    )
    return req, resp


@pytest.mark.performance
@pytest.mark.slow
async def test_insert_100_requests(storage):
    start = time.monotonic()
    for i in range(100):
        req, resp = _make_pair(i)
        await storage.add_request(req, resp)
    elapsed = time.monotonic() - start
    assert elapsed < 5.0, f"100 inserts took {elapsed:.2f}s (limit 5.0s)"


@pytest.mark.performance
@pytest.mark.slow
async def test_insert_500_requests(storage):
    start = time.monotonic()
    for i in range(500):
        req, resp = _make_pair(i)
        await storage.add_request(req, resp)
    elapsed = time.monotonic() - start
    assert elapsed < 15.0, f"500 inserts took {elapsed:.2f}s (limit 15.0s)"


@pytest.mark.performance
@pytest.mark.slow
async def test_query_after_1000_inserts(storage):
    # Insert 1000 records in batches of 100
    for batch_start in range(0, 1000, 100):
        await asyncio.gather(
            *(storage.add_request(*_make_pair(i)) for i in range(batch_start, batch_start + 100))
        )

    start = time.monotonic()
    rows = await storage.get_metadata_batch(limit=500)
    elapsed = time.monotonic() - start
    assert len(rows) == 500
    assert elapsed < 1.0, f"get_metadata_batch took {elapsed:.3f}s (limit 1.0s)"


@pytest.mark.performance
@pytest.mark.slow
async def test_clear_all_perf(storage):
    for i in range(200):
        req, resp = _make_pair(i)
        await storage.add_request(req, resp)

    start = time.monotonic()
    await storage.clear_all()
    elapsed = time.monotonic() - start
    assert elapsed < 3.0, f"clear_all took {elapsed:.3f}s (limit 3.0s)"

    cnt = await storage.count()
    assert cnt == 0


@pytest.mark.performance
@pytest.mark.slow
async def test_count_perf(storage):
    for i in range(100):
        req, resp = _make_pair(i)
        await storage.add_request(req, resp)

    start = time.monotonic()
    for _ in range(100):
        await storage.count()
    elapsed = time.monotonic() - start
    assert elapsed < 2.0, f"count() x100 took {elapsed:.3f}s (limit 2.0s)"


@pytest.mark.performance
@pytest.mark.slow
async def test_search_perf(storage):
    for i in range(100):
        req, resp = _make_pair(i)
        await storage.add_request(req, resp)

    start = time.monotonic()
    for _ in range(10):
        await storage.search("example")
    elapsed = time.monotonic() - start
    assert elapsed < 2.0, f"search() x10 took {elapsed:.3f}s (limit 2.0s)"


@pytest.mark.performance
@pytest.mark.slow
async def test_concurrent_inserts(storage):
    pairs = [_make_pair(i) for i in range(20)]
    # Should not raise any exceptions
    results = await asyncio.gather(
        *(storage.add_request(req, resp) for req, resp in pairs),
        return_exceptions=True,
    )
    for r in results:
        assert not isinstance(r, Exception), f"Concurrent insert raised: {r}"

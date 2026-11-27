"""ProxyService: the storage path that every captured request goes through (T-014).

Coverage was thin exactly where the cost of a bug is highest: a request that is captured but not
stored disappears from history with no trace (that class of bug was reported twice). These tests
drive the real service against a temporary SQLite file.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest

from pentool.services.proxy_service import ProxyService
from pentool.utils.intercepted_request import InterceptedRequest
from pentool.utils.parser import ParsedResponse


def _request(url: str = "http://example.test/", *, response: bool = True, req_id: str = "r1") -> InterceptedRequest:
    return InterceptedRequest(
        id=req_id,
        method="GET",
        url=url,
        headers={"Host": "example.test"},
        body="",
        timestamp=datetime.now(),
        state="forwarded",
        response=ParsedResponse(status=200, reason="OK", headers={}, body="<html>ok</html>") if response else None,
        is_https=url.startswith("https://"),
    )


@pytest.fixture
async def service(tmp_path: Path) -> ProxyService:
    instance = ProxyService(proxy_api=None, db_path=str(tmp_path / "history.db"))
    await instance.init_storage()
    return instance


@pytest.mark.asyncio
async def test_captured_request_reaches_history(service: ProxyService) -> None:
    row_id = await service.store_request(_request())
    assert row_id is not None

    rows = await service.get_history(offset=0, limit=10)
    assert [row["url"] for row in rows] == ["http://example.test/"]
    assert rows[0]["status_code"] == 200


@pytest.mark.asyncio
async def test_request_without_response_is_still_stored(service: ProxyService) -> None:
    await service.store_request(_request("http://example.test/pending", response=False))

    rows = await service.get_history(offset=0, limit=10)
    assert len(rows) == 1, "запрос без ответа тоже должен попадать в историю"


@pytest.mark.asyncio
async def test_host_with_port_is_kept_as_typed(service: ProxyService) -> None:
    await service.store_request(_request("https://example.test:8443/x"))

    rows = await service.get_history(offset=0, limit=10)
    assert rows[0]["url"] == "https://example.test:8443/x"


@pytest.mark.asyncio
async def test_count_history_matches_stored_rows(service: ProxyService) -> None:
    for index in range(3):
        await service.store_request(_request(f"http://example.test/{index}", req_id=f"r{index}"))

    assert await service.count_history() == 3


@pytest.mark.asyncio
async def test_delete_and_clear_remove_rows(service: ProxyService) -> None:
    first = await service.store_request(_request("http://example.test/a", req_id="a"))
    await service.store_request(_request("http://example.test/b", req_id="b"))

    await service.delete_request(int(first or 1))
    assert await service.count_history() == 1

    await service.clear_history()
    assert await service.count_history() == 0


@pytest.mark.asyncio
async def test_comment_is_stored_and_read_back(service: ProxyService) -> None:
    row_id = await service.store_request(_request())
    assert row_id is not None

    await service.update_comment(row_id, "fetch started")
    entry = await service.get_full_entry(row_id)
    assert entry is not None and entry.get("comment") == "fetch started"


@pytest.mark.asyncio
async def test_requests_arriving_before_storage_are_flushed(tmp_path: Path) -> None:
    """A capture that lands before the DB is open must not be lost."""
    instance = ProxyService(proxy_api=None, db_path=str(tmp_path / "late.db"))
    queued = _request("http://example.test/late")
    assert await instance.store_request(queued) is None  # queued, not stored yet

    await instance.init_storage()

    assert await instance.count_history() == 1, "запрос из очереди не доехал до истории"

"""Integration tests: ProxyService — orchestrates storage + ProxyAPI."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest
import pytest_asyncio

from pentool.api.proxy_api import ProxyAPI
from pentool.services.proxy_service import ProxyService

# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest_asyncio.fixture
async def proxy_service(tmp_path):
    mock_api = MagicMock(spec=ProxyAPI)
    mock_api.get_proxy.return_value = None
    service = ProxyService(
        proxy_api=mock_api,
        db_path=str(tmp_path / "proxy.db"),
    )
    await service.init_storage()
    yield service
    await service._storage.close()


@pytest.fixture
def intercepted_req():
    from pentool.modules.proxy import InterceptedRequest

    return InterceptedRequest(
        id="test-001",
        method="GET",
        url="http://example.com/api",
        headers={"Host": "example.com"},
        body="",
        timestamp=datetime.now(timezone.utc),
    )


# ── Tests ─────────────────────────────────────────────────────────────────────


@pytest.mark.integration
class TestProxyService:
    async def test_init_storage_ready(self, proxy_service: ProxyService) -> None:
        """is_storage_ready() == True after init."""
        assert proxy_service.is_storage_ready() is True

    async def test_store_request_returns_id(self, proxy_service: ProxyService, intercepted_req) -> None:
        """store_request(req) → int."""
        row_id = await proxy_service.store_request(intercepted_req)
        assert isinstance(row_id, int)
        assert row_id >= 1

    async def test_get_history_returns_list(self, proxy_service: ProxyService) -> None:
        """get_history() → list."""
        result = await proxy_service.get_history()
        assert isinstance(result, list)

    async def test_get_history_after_store(self, proxy_service: ProxyService, intercepted_req) -> None:
        """store + get_history → len >= 1."""
        await proxy_service.store_request(intercepted_req)
        history = await proxy_service.get_history()
        assert len(history) >= 1

    async def test_delete_request(self, proxy_service: ProxyService, intercepted_req) -> None:
        """store → delete(row_id) → row is no longer found."""
        row_id = await proxy_service.store_request(intercepted_req)
        await proxy_service.delete_request(row_id)
        entry = await proxy_service.get_full_entry(row_id)
        assert entry is None

    async def test_clear_history(self, proxy_service: ProxyService, intercepted_req) -> None:
        """store 3 req → clear_history() → get_history() is empty."""
        from pentool.modules.proxy import InterceptedRequest

        for i in range(3):
            req = InterceptedRequest(
                id=f"req-{i}",
                method="GET",
                url=f"http://example.com/path{i}",
                headers={"Host": "example.com"},
                body="",
                timestamp=datetime.now(timezone.utc),
            )
            await proxy_service.store_request(req)

        await proxy_service.clear_history()
        history = await proxy_service.get_history()
        assert len(history) == 0

    async def test_get_request_by_id(self, proxy_service: ProxyService, intercepted_req) -> None:
        """store → get_request_by_id(row_id) → dict."""
        row_id = await proxy_service.store_request(intercepted_req)
        result = await proxy_service.get_request_by_id(row_id)
        assert isinstance(result, dict)

    async def test_get_full_entry(self, proxy_service: ProxyService, intercepted_req) -> None:
        """store → get_full_entry(row_id) → dict."""
        row_id = await proxy_service.store_request(intercepted_req)
        result = await proxy_service.get_full_entry(row_id)
        assert isinstance(result, dict)

    async def test_switch_db(self, proxy_service: ProxyService, tmp_path) -> None:
        """switch_db new path → is_storage_ready() True."""
        new_db = str(tmp_path / "new_proxy.db")
        await proxy_service.switch_db(new_db)
        assert proxy_service.is_storage_ready() is True

    async def test_pre_storage_queue(self, tmp_path) -> None:
        """Request before init_storage → in pre_storage_queue; after init → count == 1."""
        from pentool.modules.proxy import InterceptedRequest

        mock_api = MagicMock(spec=ProxyAPI)
        mock_api.get_proxy.return_value = None
        service = ProxyService(
            proxy_api=mock_api,
            db_path=str(tmp_path / "queue_test.db"),
        )

        # storage is not initialized yet
        req = InterceptedRequest(
            id="pre-001",
            method="GET",
            url="http://example.com/pre",
            headers={"Host": "example.com"},
            body="",
            timestamp=datetime.now(timezone.utc),
        )
        result = await service.store_request(req)
        assert result is None
        assert len(service._pre_storage_queue) == 1

        # now initialize — the queue must be flushed into the DB
        await service.init_storage()
        count = await service._storage.count()
        assert count == 1

        await service._storage.close()

    async def test_is_storage_ready_before_init(self, tmp_path) -> None:
        """Before init_storage → is_storage_ready() == False."""
        mock_api = MagicMock(spec=ProxyAPI)
        service = ProxyService(
            proxy_api=mock_api,
            db_path=str(tmp_path / "not_init.db"),
        )
        assert service.is_storage_ready() is False

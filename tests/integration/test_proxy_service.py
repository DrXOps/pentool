"""Integration tests: ProxyService — orchestrates storage + ProxyAPI."""
from __future__ import annotations

import pytest
import pytest_asyncio
from datetime import datetime, timezone
from unittest.mock import MagicMock

from pentool.services.proxy_service import ProxyService
from pentool.api.proxy_api import ProxyAPI


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
        """is_storage_ready() == True после init."""
        assert proxy_service.is_storage_ready() is True

    async def test_store_request_returns_id(
        self, proxy_service: ProxyService, intercepted_req
    ) -> None:
        """store_request(req) → int."""
        row_id = await proxy_service.store_request(intercepted_req)
        assert isinstance(row_id, int)
        assert row_id >= 1

    async def test_get_history_returns_list(self, proxy_service: ProxyService) -> None:
        """get_history() → list."""
        result = await proxy_service.get_history()
        assert isinstance(result, list)

    async def test_get_history_after_store(
        self, proxy_service: ProxyService, intercepted_req
    ) -> None:
        """store + get_history → len >= 1."""
        await proxy_service.store_request(intercepted_req)
        history = await proxy_service.get_history()
        assert len(history) >= 1

    async def test_delete_request(
        self, proxy_service: ProxyService, intercepted_req
    ) -> None:
        """store → delete(row_id) → row больше не находится."""
        row_id = await proxy_service.store_request(intercepted_req)
        await proxy_service.delete_request(row_id)
        entry = await proxy_service.get_full_entry(row_id)
        assert entry is None

    async def test_clear_history(
        self, proxy_service: ProxyService, intercepted_req
    ) -> None:
        """store 3 req → clear_history() → get_history() пуст."""
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

    async def test_get_request_by_id(
        self, proxy_service: ProxyService, intercepted_req
    ) -> None:
        """store → get_request_by_id(row_id) → dict."""
        row_id = await proxy_service.store_request(intercepted_req)
        result = await proxy_service.get_request_by_id(row_id)
        assert isinstance(result, dict)

    async def test_get_full_entry(
        self, proxy_service: ProxyService, intercepted_req
    ) -> None:
        """store → get_full_entry(row_id) → dict."""
        row_id = await proxy_service.store_request(intercepted_req)
        result = await proxy_service.get_full_entry(row_id)
        assert isinstance(result, dict)

    async def test_switch_db(
        self, proxy_service: ProxyService, tmp_path
    ) -> None:
        """switch_db новый путь → is_storage_ready() True."""
        new_db = str(tmp_path / "new_proxy.db")
        await proxy_service.switch_db(new_db)
        assert proxy_service.is_storage_ready() is True

    async def test_pre_storage_queue(self, tmp_path) -> None:
        """Запрос до init_storage → в pre_storage_queue; после init → count == 1."""
        from pentool.modules.proxy import InterceptedRequest

        mock_api = MagicMock(spec=ProxyAPI)
        mock_api.get_proxy.return_value = None
        service = ProxyService(
            proxy_api=mock_api,
            db_path=str(tmp_path / "queue_test.db"),
        )

        # storage ещё не инициализирована
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

        # теперь инициализируем — очередь должна быть сброшена в БД
        await service.init_storage()
        count = await service._storage.count()
        assert count == 1

        await service._storage.close()

    async def test_is_storage_ready_before_init(self, tmp_path) -> None:
        """До init_storage → is_storage_ready() == False."""
        mock_api = MagicMock(spec=ProxyAPI)
        service = ProxyService(
            proxy_api=mock_api,
            db_path=str(tmp_path / "not_init.db"),
        )
        assert service.is_storage_ready() is False

"""Unit-тесты для pentool/services/proxy_service.py."""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch


@pytest.fixture
def proxy_api():
    api = MagicMock()
    api.get_proxy = MagicMock(return_value=None)
    return api


@pytest.fixture
def event_bus():
    return MagicMock()


@pytest.fixture
def service(proxy_api, event_bus, tmp_path):
    from pentool.services.proxy_service import ProxyService
    svc = ProxyService(
        proxy_api=proxy_api,
        db_path=str(tmp_path / "test.db"),
        event_bus=event_bus,
    )
    return svc


class TestProxyServiceInit:
    def test_storage_not_ready_initially(self, service):
        assert service.is_storage_ready() is False

    def test_pre_storage_queue_empty(self, service):
        assert service._pre_storage_queue == []


class TestProxyServiceInitStorage:
    @pytest.mark.asyncio
    async def test_init_storage_sets_ready(self, service):
        service._storage.init_db = AsyncMock()
        await service.init_storage()
        assert service.is_storage_ready() is True

    @pytest.mark.asyncio
    async def test_init_storage_flushes_queue(self, service):
        service._storage.init_db = AsyncMock()
        req = MagicMock()
        req.to_parsed_request = MagicMock(return_value=MagicMock())
        req.response = None
        req.is_websocket = False
        req.id = "test-id"
        service._pre_storage_queue.append(req)
        service._storage.add_request = AsyncMock(return_value=1)
        await service.init_storage()
        assert service._pre_storage_queue == []

    @pytest.mark.asyncio
    async def test_init_storage_handles_error(self, service):
        service._storage.init_db = AsyncMock(side_effect=Exception("DB error"))
        await service.init_storage()
        assert service.is_storage_ready() is False


class TestProxyServiceStoreRequest:
    @pytest.mark.asyncio
    async def test_store_queues_when_not_ready(self, service):
        req = MagicMock()
        result = await service.store_request(req)
        assert result is None
        assert req in service._pre_storage_queue

    @pytest.mark.asyncio
    async def test_store_saves_when_ready(self, service):
        service._storage_ready = True
        service._storage.add_request = AsyncMock(return_value=42)
        req = MagicMock()
        req.to_parsed_request = MagicMock(return_value=MagicMock())
        req.response = None
        req.is_websocket = False
        req.id = "test-id"
        result = await service.store_request(req)
        assert result == 42

    @pytest.mark.asyncio
    async def test_store_handles_exception(self, service):
        service._storage_ready = True
        service._storage.add_request = AsyncMock(side_effect=Exception("fail"))
        req = MagicMock()
        req.to_parsed_request = MagicMock(return_value=MagicMock())
        req.response = None
        req.is_websocket = False
        req.id = "test-id"
        result = await service.store_request(req)
        assert result is None


class TestProxyServiceGetHistory:
    @pytest.mark.asyncio
    async def test_returns_empty_when_not_ready(self, service):
        result = await service.get_history()
        assert result == []

    @pytest.mark.asyncio
    async def test_returns_rows_when_ready(self, service):
        service._storage_ready = True
        service._storage.get_metadata_batch = AsyncMock(return_value=[{"id": 1}])
        result = await service.get_history()
        assert result == [{"id": 1}]

    @pytest.mark.asyncio
    async def test_scope_only_filter(self, service, proxy_api):
        service._storage_ready = True
        proxy = MagicMock()
        proxy.scope = ["example.com"]
        proxy_api.get_proxy.return_value = proxy
        service._storage.get_metadata_batch = AsyncMock(return_value=[])
        await service.get_history(filters={"scope_only": True})
        call_kwargs = service._storage.get_metadata_batch.call_args[1]
        assert call_kwargs["filters"]["hosts"] == ["example.com"]

    @pytest.mark.asyncio
    async def test_handles_exception(self, service):
        service._storage_ready = True
        service._storage.get_metadata_batch = AsyncMock(side_effect=Exception("fail"))
        result = await service.get_history()
        assert result == []


class TestProxyServiceGetRequestById:
    @pytest.mark.asyncio
    async def test_returns_none_when_not_ready(self, service):
        result = await service.get_request_by_id(1)
        assert result is None

    @pytest.mark.asyncio
    async def test_returns_data_when_ready(self, service):
        service._storage_ready = True
        service._storage.get_request_by_id = AsyncMock(return_value={"id": 1})
        result = await service.get_request_by_id(1)
        assert result == {"id": 1}

    @pytest.mark.asyncio
    async def test_handles_exception(self, service):
        service._storage_ready = True
        service._storage.get_request_by_id = AsyncMock(side_effect=Exception("fail"))
        result = await service.get_request_by_id(1)
        assert result is None


class TestProxyServiceDeleteRequest:
    @pytest.mark.asyncio
    async def test_noop_when_not_ready(self, service):
        service._storage.delete = AsyncMock()
        await service.delete_request(1)
        service._storage.delete.assert_not_called()

    @pytest.mark.asyncio
    async def test_deletes_when_ready(self, service):
        service._storage_ready = True
        service._storage.delete = AsyncMock()
        await service.delete_request(1)
        service._storage.delete.assert_called_once_with(1)


class TestProxyServiceClearHistory:
    @pytest.mark.asyncio
    async def test_noop_when_not_ready(self, service):
        service._storage.clear_all = AsyncMock()
        await service.clear_history()
        service._storage.clear_all.assert_not_called()

    @pytest.mark.asyncio
    async def test_clears_when_ready(self, service):
        service._storage_ready = True
        service._storage.clear_all = AsyncMock()
        await service.clear_history()
        service._storage.clear_all.assert_called_once()


class TestProxyServiceSwitchDb:
    @pytest.mark.asyncio
    async def test_switch_db(self, service):
        service._storage.switch_db = AsyncMock()
        await service.switch_db("/new/path.db")
        service._storage.switch_db.assert_called_once_with("/new/path.db")
        assert service._db_path == "/new/path.db"

    @pytest.mark.asyncio
    async def test_switch_db_handles_error(self, service):
        service._storage.switch_db = AsyncMock(side_effect=Exception("fail"))
        await service.switch_db("/new/path.db")
        # Should not raise


class TestProxyServiceUpdateResponse:
    @pytest.mark.asyncio
    async def test_noop_when_not_ready(self, service):
        service._storage.update_response = AsyncMock()
        await service.update_response(1, MagicMock())
        service._storage.update_response.assert_not_called()

    @pytest.mark.asyncio
    async def test_updates_when_ready(self, service):
        service._storage_ready = True
        service._storage.update_response = AsyncMock()
        resp = MagicMock()
        await service.update_response(1, resp)
        service._storage.update_response.assert_called_once_with(1, resp)

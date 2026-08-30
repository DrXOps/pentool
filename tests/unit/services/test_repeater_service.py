"""Unit tests for pentool/services/repeater_service.py."""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch


@pytest.fixture
def repeater_api():
    api = MagicMock()
    api.send = AsyncMock()
    return api


@pytest.fixture
def service(repeater_api):
    from pentool.services.repeater_service import RepeaterService
    return RepeaterService(repeater_api=repeater_api)


@pytest.fixture
def service_no_api():
    from pentool.services.repeater_service import RepeaterService
    return RepeaterService(repeater_api=None)


class TestRepeaterServiceSendRequest:
    @pytest.mark.asyncio
    async def test_send_via_api(self, service, repeater_api):
        from pentool.utils.parser import ParsedResponse
        resp = ParsedResponse(status=200, headers={}, body="OK")
        repeater_api.send.return_value = resp

        raw = "GET / HTTP/1.1\r\nHost: example.com\r\n\r\n"
        result, elapsed, error = await service.send_request(raw)
        assert result is resp
        assert error is None
        assert elapsed >= 0

    @pytest.mark.asyncio
    async def test_send_exception_returns_error(self, service, repeater_api):
        repeater_api.send.side_effect = ValueError("bad request")
        raw = "GET / HTTP/1.1\r\nHost: example.com\r\n\r\n"
        result, elapsed, error = await service.send_request(raw)
        assert error is not None

    @pytest.mark.asyncio
    async def test_send_exception(self, service, repeater_api):
        repeater_api.send.side_effect = Exception("Connection refused")
        raw = "GET / HTTP/1.1\r\nHost: example.com\r\n\r\n"
        result, elapsed, error = await service.send_request(raw)
        assert result is None
        assert "Connection refused" in error

    @pytest.mark.asyncio
    async def test_send_without_api_spins_up_own_api(self, service_no_api):
        from pentool.utils.parser import ParsedResponse
        resp = ParsedResponse(status=200, headers={}, body="OK")

        # 4.3: when no RepeaterAPI was injected, the service creates its own
        # (single route through the API layer) rather than a raw HTTPClient.
        from pentool.api.repeater_api import RepeaterAPI

        with patch("pentool.services.repeater_service.RepeaterAPI") as mock_api_cls:
            mock_api = AsyncMock()
            mock_api.send = AsyncMock(return_value=resp)
            mock_api_cls.return_value = mock_api

            raw = "GET / HTTP/1.1\r\nHost: example.com\r\n\r\n"
            result, elapsed, error = await service_no_api.send_request(raw)
            # sent through the (self-created) API, without history (save=False)
            mock_api.send.assert_awaited_once()
            kwargs = mock_api.send.call_args.kwargs
            assert kwargs.get("save") is False
            assert result is resp

    @pytest.mark.asyncio
    async def test_elapsed_ms_returned(self, service, repeater_api):
        from pentool.utils.parser import ParsedResponse
        resp = ParsedResponse(status=200, headers={}, body="OK")
        repeater_api.send.return_value = resp

        raw = "GET / HTTP/1.1\r\nHost: example.com\r\n\r\n"
        _, elapsed, _ = await service.send_request(raw)
        assert isinstance(elapsed, int)
        assert elapsed >= 0


class TestRepeaterServiceClose:
    @pytest.mark.asyncio
    async def test_close_no_client(self, service):
        await service.close()  # Should not raise

    @pytest.mark.asyncio
    async def test_close_no_standalone_client(self, service_no_api):
        # 4.3: no standalone HTTP client anymore — close is a safe no-op.
        await service_no_api.close()  # Should not raise

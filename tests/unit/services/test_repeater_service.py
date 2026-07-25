"""Unit-тесты для pentool/services/repeater_service.py."""

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
    async def test_send_without_api_uses_http_client(self, service_no_api):
        from pentool.utils.parser import ParsedResponse
        resp = ParsedResponse(status=200, headers={}, body="OK")

        with patch("pentool.services.repeater_service.HTTPClient") as mock_cls:
            mock_client = AsyncMock()
            mock_client.send = AsyncMock(return_value=resp)
            mock_cls.return_value = mock_client

            raw = "GET / HTTP/1.1\r\nHost: example.com\r\n\r\n"
            result, elapsed, error = await service_no_api.send_request(raw)
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
    async def test_close_with_client(self, service_no_api):
        mock_client = AsyncMock()
        mock_client.close = AsyncMock()
        service_no_api._http_client = mock_client
        await service_no_api.close()
        mock_client.close.assert_called_once()
        assert service_no_api._http_client is None

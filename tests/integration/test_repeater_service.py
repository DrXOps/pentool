"""Integration tests: RepeaterService — HTTP sending with mocked aiohttp."""
from __future__ import annotations

import pytest
import pytest_asyncio
from aioresponses import aioresponses

from pentool.services.repeater_service import RepeaterService
from pentool.utils.parser import ParsedResponse


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def service():
    return RepeaterService()


# ── Tests ─────────────────────────────────────────────────────────────────────

@pytest.mark.integration
class TestRepeaterService:

    async def test_send_request_success(self, service: RepeaterService) -> None:
        """Мокнуть GET → status=200; send_request → (ParsedResponse, elapsed_ms >= 0, None)."""
        raw = "GET http://example.com/api HTTP/1.1\r\nHost: example.com\r\n\r\n"
        with aioresponses() as m:
            m.get("http://example.com/api", status=200, body=b"OK")
            resp, elapsed, err = await service.send_request(raw)

        assert isinstance(resp, ParsedResponse)
        assert resp.status == 200
        assert elapsed >= 0
        assert err is None

        await service.close()

    async def test_send_request_invalid_raw(self, service: RepeaterService) -> None:
        """send_request("not a request") → (None, 0, str) — parse error."""
        resp, elapsed, err = await service.send_request("not a request")
        assert resp is None
        assert elapsed == 0
        assert isinstance(err, str)

        await service.close()

    async def test_send_request_post(self, service: RepeaterService) -> None:
        """Мокнуть POST → status=201; отправить POST запрос → resp.status == 201."""
        raw = (
            "POST http://example.com/api HTTP/1.1\r\n"
            "Host: example.com\r\n"
            "Content-Type: application/json\r\n"
            "\r\n"
            '{"key": "value"}'
        )
        with aioresponses() as m:
            m.post("http://example.com/api", status=201, body=b"Created")
            resp, elapsed, err = await service.send_request(raw)

        assert resp is not None
        assert resp.status == 201
        assert err is None

        await service.close()

    async def test_elapsed_ms_non_negative(self, service: RepeaterService) -> None:
        """elapsed_ms >= 0 всегда."""
        raw = "GET http://example.com/timing HTTP/1.1\r\nHost: example.com\r\n\r\n"
        with aioresponses() as m:
            m.get("http://example.com/timing", status=200, body=b"ok")
            _, elapsed, _ = await service.send_request(raw)

        assert elapsed >= 0

        await service.close()

    async def test_close_no_error(self, service: RepeaterService) -> None:
        """service.close() не бросает исключение."""
        # Инициализируем клиент одним запросом
        raw = "GET http://example.com/close HTTP/1.1\r\nHost: example.com\r\n\r\n"
        with aioresponses() as m:
            m.get("http://example.com/close", status=200, body=b"bye")
            await service.send_request(raw)

        # close не должен бросать
        await service.close()

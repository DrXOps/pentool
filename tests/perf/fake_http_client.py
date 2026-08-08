"""Fake HTTPClient — мгновенные "консервированные" ответы, без сети.

Используется в Level-A leak-тестах: изолирует именно *планирование*
задач (`asyncio.gather` эагерный fan-out в ScanEngine/IntruderAttack) от
реальных сетевых/I-O эффектов. Если память всё равно взрывается здесь —
причина структурная (в самом коде движка), а не в сетевой буферизации.
"""

from __future__ import annotations

import asyncio

from pentool.utils.parser import ParsedRequest, ParsedResponse

_BODY = (
    "<html><head><title>Fake</title></head><body>"
    "<p>Server: nginx/1.18.0</p><p>ok</p>"
    "</body></html>"
)


class FakeHTTPClient:
    """Drop-in замена pentool.utils.http_client.HTTPClient для тестов.

    Каждый send()/get()/post() возвращается мгновенно (один
    asyncio.sleep(0) — чтобы остаться "хорошей" корутиной, реально
    отдающей управление циклу событий) с фиксированным 200 OK — без
    aiohttp, без сокетов, без per-request TCP/TLS. Считает вызовы.
    """

    def __init__(self, body: str = _BODY, status: int = 200, delay: float = 0.0) -> None:
        self._body = body
        self._status = status
        self._delay = delay
        self.calls = 0

    async def send(self, request: ParsedRequest) -> ParsedResponse:
        self.calls += 1
        if self._delay:
            await asyncio.sleep(self._delay)
        else:
            await asyncio.sleep(0)
        return ParsedResponse(
            status=self._status,
            reason="OK",
            headers={
                "Content-Type": "text/html",
                "X-Powered-By": "PHP/7.4.3",
                "Server": "nginx/1.18.0",
            },
            body=self._body,
        )

    async def get(self, url: str, headers: dict | None = None) -> ParsedResponse:
        return await self.send(ParsedRequest(method="GET", url=url, headers=headers or {}, body=""))

    async def post(self, url: str, body: str = "", headers: dict | None = None) -> ParsedResponse:
        return await self.send(ParsedRequest(method="POST", url=url, headers=headers or {}, body=body))

    async def close(self) -> None:
        pass

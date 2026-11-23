"""Fake HTTPClient — instant "canned" responses, no network.

Used in the Level-A leak tests: it isolates precisely the *scheduling* of
tasks (`asyncio.gather` eager fan-out in ScanEngine/IntruderAttack) from
real network/I-O effects. If memory still blows up here, the cause is
structural (in the engine code itself), not network buffering.
"""

from __future__ import annotations

import asyncio

from pentool.utils.parser import ParsedRequest, ParsedResponse

_BODY = "<html><head><title>Fake</title></head><body><p>Server: nginx/1.18.0</p><p>ok</p></body></html>"


class FakeHTTPClient:
    """Drop-in replacement for pentool.utils.http_client.HTTPClient in tests.

    Every send()/get()/post() returns instantly (a single
    asyncio.sleep(0) — so it stays a "well-behaved" coroutine that actually
    yields control to the event loop) with a fixed 200 OK — no aiohttp,
    no sockets, no per-request TCP/TLS. It counts the calls.
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

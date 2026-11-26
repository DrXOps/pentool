"""Captured traffic is stored even when the Proxy screen is not open (owner's item 9).

The screen used to be the only writer: with the Dashboard open (`--smart` start) nothing reached
HTTP History. These tests pin the contract — the app stores the completed exchange itself when the
screen is absent, and the screen path stays untouched when it is present.
"""

from __future__ import annotations

from datetime import datetime
from threading import Lock
from types import SimpleNamespace

import pytest

from pentool.tui.app import PentoolApp
from pentool.utils.intercepted_request import InterceptedRequest


class _Service:
    def __init__(self) -> None:
        self.stored: list = []

    async def store_request(self, req):
        self.stored.append(req)
        return 1


def _request(req_id: str) -> InterceptedRequest:
    return InterceptedRequest(
        id=req_id,
        method="GET",
        url="http://example.test/",
        headers={"Host": "example.test"},
        body="",
        timestamp=datetime.now(),
        state="forwarded",
    )


def _app_with(service, screen=None, pending=None) -> PentoolApp:
    pending = pending if pending is not None else []
    app = PentoolApp()  # real object: the handler is a Textual message method
    app._skip_project_guard = True
    app._proxy = SimpleNamespace(is_running=True, intercept_enabled=False)
    app._proxy_service = service
    app._get_proxy_screen = lambda: screen
    app._workers = pending
    app.run_worker = lambda coro, **kwargs: pending.append(coro)
    app._pending_done_ids = set()
    app._pending_done_lock = Lock()
    return app


@pytest.mark.asyncio
async def test_completed_request_is_stored_without_the_proxy_screen() -> None:
    service = _Service()
    pending: list = []
    app = _app_with(service, screen=None, pending=pending)
    req = _request("r1")

    app.on_proxy_request_done(SimpleNamespace(req=req))
    for coro in pending:
        await coro

    assert service.stored == [req], "запрос не записан без открытого экрана Proxy — история пуста"


@pytest.mark.asyncio
async def test_screen_path_is_used_when_the_screen_exists() -> None:
    service = _Service()
    calls: list = []

    class _Screen:
        def update_request_row(self, req):
            calls.append(req)

    app = _app_with(service, screen=_Screen())
    req = _request("r2")

    app.on_proxy_request_done(SimpleNamespace(req=req))

    assert calls == [req], "экран должен обновляться как раньше"
    assert service.stored == [], "двойной записи нет: экран сам пишет строку"

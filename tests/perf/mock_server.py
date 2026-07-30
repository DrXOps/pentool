"""Локальный мок-сервер для perf-тестов (без внешней сети)."""
from __future__ import annotations

import asyncio
from aiohttp import web


async def handle(request: web.Request) -> web.Response:
    # Небольшая полезная нагрузка + echo query, чтобы чекеры сканера имели что анализировать
    body = (
        "<html><head><title>Mock Target</title></head><body>"
        f"<p>method={request.method}</p><p>path={request.path_qs}</p>"
        "<p>Server: nginx/1.18.0</p>"
        "</body></html>"
    )
    return web.Response(text=body, status=200, headers={"X-Powered-By": "PHP/7.4.3"})


def make_app() -> web.Application:
    app = web.Application()
    app.router.add_route("*", "/{tail:.*}", handle)
    return app


class MockServer:
    """Контекстный менеджер: поднимает aiohttp сервер на свободном порту."""

    def __init__(self, port: int = 8765):
        self.port = port
        self._runner: web.AppRunner | None = None

    async def __aenter__(self) -> "MockServer":
        app = make_app()
        self._runner = web.AppRunner(app)
        await self._runner.setup()
        site = web.TCPSite(self._runner, "127.0.0.1", self.port)
        await site.start()
        return self

    async def __aexit__(self, *exc) -> None:
        if self._runner:
            await self._runner.cleanup()

    @property
    def base_url(self) -> str:
        return f"http://127.0.0.1:{self.port}"

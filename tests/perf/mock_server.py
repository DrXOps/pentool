"""Local mock server for perf tests (no external network)."""

from __future__ import annotations

from aiohttp import web


async def handle(request: web.Request) -> web.Response:
    # A small useful payload + echoed query, so scanner checks have something to analyze
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
    """Context manager: starts an aiohttp server on a free port."""

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

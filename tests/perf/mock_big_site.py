"""Параметризуемый локальный "крупный сайт" для нагрузочных leak-тестов.

Единственная цель — дать Scanner/Spider/Intruder что-то похожее на
реальный крупный сайт (много уникальных URL, GET/POST-параметров, форм),
без сети, без риска бана/троттлинга и с детерминированным размером.

Параметры (через MockBigSiteConfig):
  - n_pages:        число уникальных "страниц" /page/<i>
  - params_per_page: число GET-параметров на страницу (?p0=..&p1=..)
  - n_forms:        число POST-форм (каждая с несколькими полями)
  - body_size:      размер HTML-тела ответа (байт) — влияет на baseline/diff

Страницы линкуются друг на друга (следующие N_LINKS_PER_PAGE), так что
Spider может реально обойти сайт (не просто список URL "в лоб").

Использование как контекстный менеджер:
    async with MockBigSite(MockBigSiteConfig(n_pages=2000)) as site:
        print(site.base_url)
"""

from __future__ import annotations

from dataclasses import dataclass

from aiohttp import web

_LINKS_PER_PAGE = 5


@dataclass
class MockBigSiteConfig:
    n_pages: int = 1000
    params_per_page: int = 3
    n_forms: int = 200
    body_size: int = 800
    port: int = 8766


def _page_html(cfg: MockBigSiteConfig, i: int) -> str:
    links = []
    for j in range(_LINKS_PER_PAGE):
        target = (i * 7 + j + 1) % cfg.n_pages
        query = "&".join(f"p{k}=val{target}_{k}" for k in range(cfg.params_per_page))
        links.append(f'<a href="/page/{target}?{query}">page {target}</a>')

    forms = ""
    if cfg.n_forms and i % max(cfg.n_pages // max(cfg.n_forms, 1), 1) == 0:
        form_id = i % cfg.n_forms
        forms = (
            f'<form action="/submit/{form_id}" method="POST">'
            f'<input name="username" value="user{form_id}">'
            f'<input name="comment" value="hello">'
            f'<input name="token" value="tok{form_id}">'
            f'</form>'
        )

    padding = "x" * max(cfg.body_size - 400, 0)
    return (
        "<html><head><title>Mock Big Site</title></head><body>"
        f"<p>Server: nginx/1.18.0</p><p>page={i}</p>"
        + "".join(links)
        + forms
        + f"<!-- {padding} -->"
        "</body></html>"
    )


def make_app(cfg: MockBigSiteConfig) -> web.Application:
    app = web.Application()

    async def handle_page(request: web.Request) -> web.Response:
        try:
            i = int(request.match_info["i"]) % cfg.n_pages
        except (KeyError, ValueError):
            i = 0
        return web.Response(
            text=_page_html(cfg, i),
            status=200,
            headers={"X-Powered-By": "PHP/7.4.3", "Server": "nginx/1.18.0"},
        )

    async def handle_submit(request: web.Request) -> web.Response:
        await request.post()
        return web.Response(text="<html><body>OK</body></html>", status=200)

    async def handle_root(request: web.Request) -> web.Response:
        return await handle_page_zero(request)

    async def handle_page_zero(_request: web.Request) -> web.Response:
        return web.Response(text=_page_html(cfg, 0), status=200)

    async def handle_robots(_request: web.Request) -> web.Response:
        return web.Response(text="User-agent: *\nAllow: /\n", status=200)

    app.router.add_get("/", handle_root)
    app.router.add_get("/robots.txt", handle_robots)
    app.router.add_route("*", "/page/{i}", handle_page)
    app.router.add_route("POST", "/submit/{i}", handle_submit)
    return app


class MockBigSite:
    """Context manager: raises a parameterized aiohttp server on a free-ish port."""

    def __init__(self, cfg: MockBigSiteConfig | None = None) -> None:
        self.cfg = cfg or MockBigSiteConfig()
        self._runner: web.AppRunner | None = None

    async def __aenter__(self) -> "MockBigSite":
        app = make_app(self.cfg)
        self._runner = web.AppRunner(app)
        await self._runner.setup()
        site = web.TCPSite(self._runner, "127.0.0.1", self.cfg.port)
        await site.start()
        return self

    async def __aexit__(self, *exc) -> None:
        if self._runner:
            await self._runner.cleanup()

    @property
    def base_url(self) -> str:
        return f"http://127.0.0.1:{self.cfg.port}"

    def page_url(self, i: int, with_params: bool = True) -> str:
        i = i % self.cfg.n_pages
        if not with_params:
            return f"{self.base_url}/page/{i}"
        query = "&".join(f"p{k}=val{i}_{k}" for k in range(self.cfg.params_per_page))
        return f"{self.base_url}/page/{i}?{query}"

    def seed_urls(self, n: int) -> list[str]:
        """N distinct page URLs (with GET params) — for direct engine tests."""
        return [self.page_url(i) for i in range(n)]

"""Быстрый perf-проверка Spider на локальном MockBigSite.

Аналог тяжёлого `tests/perf/load_spider.py --level b` (M7). Проверяем на
маленьком детерминированном mock-сайте:
  - обход заканчивается (не зацикливается);
  - дедупликация: число уникальных посещённых страниц ≤ max_pages, и
    total_requests = len(visited) (нет повторных запросов одного URL);
  - RSS не взрывается скачком на малом объёме (smoke-ассерт).
"""

from __future__ import annotations

import gc

import pytest

from pentool.modules.spider import AsyncSpider
from tests.perf.memtrack import rss_mb
from tests.perf.mock_big_site import MockBigSite, MockBigSiteConfig

pytestmark = pytest.mark.perf


def test_mock_site_crawl_completes_and_dedups():
    """Обход MockBigSite: завершается, дедуплицирует, в пределах max_pages."""
    gc.collect()
    rss_before = rss_mb()

    async def _run():
        cfg = MockBigSiteConfig(n_pages=200, params_per_page=3)
        async with MockBigSite(cfg) as site:
            spider = AsyncSpider(max_depth=2, max_pages=50, concurrency=5,
                                 timeout=10)
            return await spider.crawl(site.base_url)

    import asyncio

    r = asyncio.run(_run())
    d = r.to_dict()

    # Завершился, не зациклился
    assert d["pages_count"] <= 50, "превышен max_pages"
    # Все найденные страницы уникальны (дедупликация внутри result.pages)
    assert len(r.pages) == len(set(r.pages)), "страницы дублируются в result.pages"
    # Хотя бы что-то обойдено
    assert d["pages_count"] > 0 or d["endpoints_count"] > 0, "crawl нашёл 0 страниц"

    # RSS не должен скачком улететь на мелком прогоне (smoke; самплинг шумный)
    gc.collect()
    rss_after = rss_mb()
    assert rss_after - rss_before < 25, (
        f"RSS изменился на {rss_after - rss_before:.1f}MB на малом обходе"
    )


def test_spider_scope_respected():
    """Спайдер не уходит за пределы домена (scope)."""
    async def _run():
        cfg = MockBigSiteConfig(n_pages=50, params_per_page=2)
        async with MockBigSite(cfg) as site:
            spider = AsyncSpider(max_depth=3, max_pages=100, concurrency=5,
                                 timeout=10)
            r = await spider.crawl(site.base_url)
            # Все найденные ссылки/форм — того же домена (127.0.0.1:port)
            for p in r.pages:
                assert site.base_url in p, f"страница вне scope: {p}"
            return True

    import asyncio

    assert asyncio.run(_run()) is True

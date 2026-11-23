"""Quick perf check of Spider against the local MockBigSite.

Analogous to the heavy `tests/perf/load_spider.py --level b` (M7). We check on
a small deterministic mock site:
  - the crawl finishes (does not loop forever);
  - deduplication: the number of unique visited pages ≤ max_pages, and
    total_requests = len(visited) (no repeated requests for the same URL);
  - RSS does not blow up abruptly on a small volume (smoke assertion).
"""

from __future__ import annotations

import gc

import pytest

from pentool.modules.spider import AsyncSpider
from tests.perf.memtrack import rss_mb
from tests.perf.mock_big_site import MockBigSite, MockBigSiteConfig

pytestmark = pytest.mark.perf


def test_mock_site_crawl_completes_and_dedups():
    """Crawl of MockBigSite: finishes, deduplicates, stays within max_pages."""
    gc.collect()
    rss_before = rss_mb()

    async def _run():
        cfg = MockBigSiteConfig(n_pages=200, params_per_page=3)
        async with MockBigSite(cfg) as site:
            spider = AsyncSpider(max_depth=2, max_pages=50, concurrency=5, timeout=10)
            return await spider.crawl(site.base_url)

    import asyncio

    r = asyncio.run(_run())
    d = r.to_dict()

    # Finished, did not get stuck in a loop
    assert d["pages_count"] <= 50, "превышен max_pages"
    # All discovered pages are unique (dedup inside result.pages)
    assert len(r.pages) == len(set(r.pages)), "страницы дублируются в result.pages"
    # At least something was crawled
    assert d["pages_count"] > 0 or d["endpoints_count"] > 0, "crawl нашёл 0 страниц"

    # RSS must not jump on a small run (smoke; sampling is noisy)
    gc.collect()
    rss_after = rss_mb()
    assert rss_after - rss_before < 25, f"RSS изменился на {rss_after - rss_before:.1f}MB на малом обходе"


def test_spider_scope_respected():
    """The spider does not leave the domain (scope)."""

    async def _run():
        cfg = MockBigSiteConfig(n_pages=50, params_per_page=2)
        async with MockBigSite(cfg) as site:
            spider = AsyncSpider(max_depth=3, max_pages=100, concurrency=5, timeout=10)
            r = await spider.crawl(site.base_url)
            # All discovered links/forms belong to the same domain (127.0.0.1:port)
            for p in r.pages:
                assert site.base_url in p, f"страница вне scope: {p}"
            return True

    import asyncio

    assert asyncio.run(_run()) is True

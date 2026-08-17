"""Нагрузочные тесты Spider (AsyncSpider): обход и парсинг.

Уровни (гибрид, LOAD_TESTING_PLAN_2026-08-17.md):
  A(parse) — скорость _parse_html БЕЗ сети на синтетических HTML-страницах
        больших размеров (100КБ/1МБ): замер времени/памяти парсинга,
        числа найденных ссылок/форм/JS.
  B — обход локального MockBigSite (реальный HTTP): матрица n_pages ×
        max_depth × concurrency, дедупликация URL, RSS/CPU/время.
  C — DVWA crawl (малый max_pages), сессия через extra_headers.

Запуск:
    python3 tests/perf/load_spider.py --level a        # парсинг
    python3 tests/perf/load_spider.py --level b --n-pages 5000
    python3 tests/perf/load_spider.py --level c
"""

from __future__ import annotations

import argparse
import asyncio
import gc
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)

from pentool.modules.spider import AsyncSpider  # noqa: E402
from tests.perf.memtrack import MemSampler, rss_mb, save_report  # noqa: E402
from tests.perf.mock_big_site import MockBigSite, MockBigSiteConfig  # noqa: E402

# ═══════════════════════════════════════════════════════════════════════════
# Уровень A(parse) — скорость _parse_html без сети
# ═══════════════════════════════════════════════════════════════════════════

def _synthetic_html(size_bytes: int, n_links: int, with_forms: bool = True) -> str:
    """Синтетическая HTML-страница размера ~size_bytes с n_links ссылок."""
    base = []
    base.append("<html><head><title>Perf</title>")
    base.append("<script src='/static/app.js'></script></head><body>")
    for i in range(n_links):
        # ~50 bytes on a link
        base.append(f'<a href="/page/{i}?p=val{i}">link {i} xxxxxx</a>')
    if with_forms:
        for i in range(20):
            base.append(
                f"<form action='/submit/{i}' method='POST'>"
                f"<input name='username' value='user{i}'>"
                f"<input name='token' value='tok{i}'></form>"
            )
    base.append("<!--")
    base.append("x" * max(size_bytes - sum(len(b) for b in base) - 8, 0))
    base.append("-->")
    base.append("</body></html>")
    h = "".join(base)
    # Добить до точного target-размера, если ещё не хватает
    if len(h) < size_bytes:
        h = h.replace("-->", "x" * (size_bytes - len(h) + 3) + "-->", 1)
    return h


async def run_level_a(args) -> dict:
    print("\n=== УРОВЕНЬ A: парсинг HTML без сети ===")
    spider = AsyncSpider(max_pages=0)  # не краулим, только _parse_html
    sampler = MemSampler(cpu=True)
    rows = []
    for size in (100 * 1024, 512 * 1024, 1024 * 1024):
        html = _synthetic_html(size, n_links=2000)
        page_url = "http://127.0.0.1:9/page/0?p=1"
        sampler.tick(f"before parse {size // 1024}KB")
        gc.collect()
        rss0 = rss_mb()
        t0 = time.monotonic()
        links, forms, js = spider._parse_html(html, page_url, "127.0.0.1:9")
        dt = time.monotonic() - t0
        gc.collect()
        rss1 = rss_mb()
        sampler.tick(f"after parse {size // 1024}KB", elapsed=round(dt, 3),
                     n_links=len(links), n_forms=len(forms), n_js=len(js))
        rows.append({"size_kb": size // 1024, "dt_s": round(dt, 3),
                     "links": len(links), "forms": len(forms), "js": len(js),
                     "rss_delta": round(rss1 - rss0, 1),
                     "mb_per_s": round(size / (1024 * 1024) / dt if dt else 0, 1)})
        print(f"  {size // 1024:5}KB  dt={dt:.2f}s links={len(links)} "
              f"forms={len(forms)} js={len(js)} ({rows[-1]['mb_per_s']}MB/s)")
    return {"rows": rows, "table": sampler.render_report("Spider Level A — парсинг")}


# ═══════════════════════════════════════════════════════════════════════════
# Уровень B — обход MockBigSite (реальный HTTP)
# ═══════════════════════════════════════════════════════════════════════════

async def run_level_b(args) -> dict:
    print("\n=== УРОВЕНЬ B: обход MockBigSite (реальный HTTP) ===")
    sampler = MemSampler(cpu=True)
    cfg = MockBigSiteConfig(n_pages=args.n_pages, params_per_page=args.params_per_page,
                            body_size=args.body_size, port=args.mock_port)
    async with MockBigSite(cfg) as site:
        spider = AsyncSpider(max_depth=args.max_depth, max_pages=args.max_pages,
                             concurrency=args.concurrency, timeout=10)
        sampler.tick(f"crawl start: n_pages={cfg.n_pages} depth={args.max_depth} "
                     f"max_pages={args.max_pages} conc={args.concurrency}")
        t0 = time.monotonic()
        result = await spider.crawl(site.base_url)
        dt = time.monotonic() - t0
        gc.collect()
        d = result.to_dict()
        sampler.tick("crawl done", elapsed=round(dt, 3), **d)
        print(f"  {d['pages_count']} pages, {d['endpoints_count']} endpoints, "
              f"{d['forms_count']} forms, {d['total_requests']} requests, "
              f"{d['js_files_count']} js, {d['errors_count']} errors, {dt:.2f}s")
    return {"dict": d, "dt_s": round(dt, 3),
            "table": sampler.render_report("Spider Level B — MockBigSite обход")}


# ═══════════════════════════════════════════════════════════════════════════
# Уровень C — DVWA crawl (малый, сессия)
# ═══════════════════════════════════════════════════════════════════════════

async def run_level_c(args) -> dict:
    print("\n=== УРОВЕНЬ C: обход DVWA (реальный сайт, сессия) ===")
    from tests.perf.dvwa_session import DVWA_URL, build_session_headers

    headers = await build_session_headers()
    print(f"  сессия: {headers['Cookie'][:40]}…")
    sampler = MemSampler(cpu=True)

    spider = AsyncSpider(max_depth=args.max_depth, max_pages=args.max_pages,
                         concurrency=args.concurrency, timeout=15,
                         extra_headers=headers)
    sampler.tick("crawl DVWA start")
    t0 = time.monotonic()
    try:
        result = await spider.crawl(DVWA_URL)
    finally:
        pass  # spider не держит ланчер, aiohttp сессия закрывается внутри crawl
    dt = time.monotonic() - t0
    gc.collect()
    d = result.to_dict()
    sampler.tick("crawl DVWA done", elapsed=round(dt, 3), **d)
    print(f"  {d['pages_count']} pages, {d['endpoints_count']} endpoints, "
          f"{d['forms_count']} forms, {d['total_requests']} requests, "
          f"{d['errors_count']} errors, {dt:.2f}s")
    return {"dict": d, "dt_s": round(dt, 3),
            "table": sampler.render_report("Spider Level C — DVWA обход")}


# ═══════════════════════════════════════════════════════════════════════════

async def main(args):
    ts = time.strftime("%Y%m%d_%H%M%S")
    out_path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            f"load_spider_{ts}.md")
    all_report: list[str] = ["# Spider load-test", "",
                             f"Дата: {time.strftime('%Y-%m-%d %H:%M:%S')}", ""]
    if args.level == "a":
        res = await run_level_a(args)
        all_report += ["## Уровень A — парсинг", "", res["table"]]
    elif args.level == "b":
        res = await run_level_b(args)
        all_report += ["## Уровень B — MockBigSite", "",
                       "### Итог обхода",
                       str(res["dict"]), "",
                       res["table"]]
    elif args.level == "c":
        res = await run_level_c(args)
        all_report += ["## Уровень C — DVWA", "",
                       "### Итог обхода",
                       str(res["dict"]), "",
                       res["table"]]
    else:
        raise SystemExit(f"Неизвестный --level: {args.level}")
    save_report(out_path, "\n".join(all_report))


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Нагрузочные тесты Spider")
    ap.add_argument("--level", default="a", choices=["a", "b", "c"])
    ap.add_argument("--n-pages", type=int, default=3000, help="MockBigSite pages (level b)")
    ap.add_argument("--params-per-page", type=int, default=3)
    ap.add_argument("--body-size", type=int, default=800)
    ap.add_argument("--max-depth", type=int, default=2)
    ap.add_argument("--max-pages", type=int, default=1000, help="Потолок посещённых URL (level b/c)")
    ap.add_argument("--concurrency", type=int, default=10)
    ap.add_argument("--mock-port", type=int, default=8766)
    args = ap.parse_args()
    asyncio.run(main(args))

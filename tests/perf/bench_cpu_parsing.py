"""Benchmark: where the spider/scanner CPU goes and whether to bypass the GIL.

Goal (see the 2026-08-17 discussion): decide what will help — (a) swapping
BeautifulSoup for lxml and (b) multiprocessing to bypass the GIL — based on
facts, not on guesses.

From the profile of spider._parse_html (see load_spider / discussion) the two
dominant CPU jobs of the spider:
  1. HTML parsing (BeautifulSoup html.parser)   ~31%
  2. Per-link URL handling: urlparse/urljoin/urlsplit + _normalize_url  ~55%
Both are Python code under the GIL. We measure:

  Section A — parsing: bs4 vs lxml (if lxml is available) on real HTML.
  Section B — GIL/multiprocessing: two CPU jobs (a parsing-like one and a
      urlparse-like one) are executed as:
        sync     — in the current process (GIL-bound, as today)
        threads  — in a ThreadPoolExecutor (GIL is NOT bypassed, but shows the cost)
        procs    — in a ProcessPoolExecutor (bypasses the GIL)
      We look at the procs-vs-threads speedup of each job and at the IPC transfer time.

Run:
    python3 tests/perf/bench_cpu_parsing.py          # synthetic (any environment)
    python3 -m pip ... # the lxml comparison needs lxml: system python had it

Decision input: if the urllib calls dominate (as in the profile), then the LARGE
gain from multiprocessing will come only from them, while the parsing part will
gain from lxml without any multiprocessing. The decision follows from the ratio
of the two.
"""

from __future__ import annotations

import concurrent.futures as cf
import os
import time
from urllib.parse import urljoin, urlparse

# ═══════════ Section A — parsing: bs4 vs lxml (when available) ══════════════


def _big_html(n_links: int = 3000) -> str:
    h = "<html><head><title>t</title></head><body>"
    h += "".join(f'<a href="/page/{i}?p=v{i}">l{i}</a>' for i in range(n_links))
    h += '<form action="/s"><input name="a" value="1"></form></body></html>'
    return h


def _try_import():
    have = {"bs4": False, "lxml": False}
    try:
        from bs4 import BeautifulSoup  # noqa: F401

        have["bs4"] = True
    except ImportError:
        pass
    try:
        import lxml.html  # noqa: F401

        have["lxml"] = True
    except ImportError:
        pass
    return have


def _bench_parsing(html: str, have):
    print("── Раздел A: парсинг HTML (3000 ссылок, x20) ─────────────────────")
    results = {}
    if have["bs4"]:
        from bs4 import BeautifulSoup

        t = time.monotonic()
        for _ in range(20):
            soup = BeautifulSoup(html, "html.parser")
            _ = [a.get("href", "") for a in soup.find_all("a", href=True)]
        wall = time.monotonic() - t
        results["bs4_htmlparser"] = wall
        print(f"  BeautifulSoup html.parser : {wall:6.2f}s  ({wall / 20 * 1000:4.0f}ms/стр)")
    if have["lxml"]:
        import lxml.html as lh

        t = time.monotonic()
        for _ in range(20):
            doc = lh.fromstring(html)
            _ = doc.xpath("//a[@href]/@href")
        wall = time.monotonic() - t
        results["lxml"] = wall
        print(f"  lxml xpath               : {wall:6.2f}s  ({wall / 20 * 1000:4.0f}ms/стр)")
        if "bs4_htmlparser" in results:
            print(f"  ускорение lxml/bs4       : {results['bs4_htmlparser'] / wall:6.1f}x")
    return results


# ═══════════ Section B — GIL vs multiprocessing on two kinds of CPU jobs ════


def _urlparse_work(n: int) -> int:
    """urlparse-like CPU job: a lot of urllib parsing (like _add_link)."""
    cnt = 0
    base = "http://127.0.0.1:9/index.php"
    for i in range(n):
        for j in range(10):
            u = f"/page/{i}?p=v{j}&q=val{j}"
            parsed = urlparse(urljoin(base, u))
            cnt += len(parsed.path) + len(parsed.query)
    return cnt


def _strsplit_work(n: int) -> int:
    """Parsing-like CPU job: regex+strings over a large HTML (like bs4)."""
    import re

    html = _big_html(3000)
    pat = re.compile(r'href="([^"]+)"')
    cnt = 0
    for _ in range(n):
        cnt += len(pat.findall(html))
    return cnt


def _run_tasks(name: str, work, args, n_parallel: int):
    print(f"\n── Раздел B: {name} (CPU-задача) ─────────────────────────────────")
    rows = {}

    # sync — one call in the current process (GIL-bound, as today)
    total = args[0]
    t0 = time.monotonic()
    work(total)
    dt_sync = time.monotonic() - t0
    rows["sync"] = dt_sync
    print(f"  sync    : {dt_sync * 1000:7.0f}ms  (вся работа в одном процессе, амбар)")

    # Split the same work into n_parallel chunks ↓ the total volume stays the same
    # as in sync. That way threads/procs show the honest speedup from parallelising
    # ONE task (not 8 independent copies).
    per = max(1, total // n_parallel)
    split = [per] * n_parallel
    # Even it out so the sum is ≈ total (the last chunk takes the remainder)
    split[-1] += total - per * n_parallel

    # threads — ThreadPoolExecutor (GIL is NOT bypassed, shows the GIL cost)
    t0 = time.monotonic()
    with cf.ThreadPoolExecutor(max_workers=n_parallel) as ex:
        list(ex.map(work, split))
    dt_thr = time.monotonic() - t0
    rows["threads"] = dt_thr
    print(f"  threads : {dt_thr * 1000:7.0f}ms  ({n_parallel} потоков, GIL блокирует)")

    # procs — ProcessPoolExecutor (bypasses the GIL, pays the IPC argument transfer)
    t0 = time.monotonic()
    with cf.ProcessPoolExecutor(max_workers=n_parallel) as ex:
        list(ex.map(work, split))
    dt_proc = time.monotonic() - t0
    rows["procs"] = dt_proc
    print(f"  procs   : {dt_proc * 1000:7.0f}ms  ({n_parallel} процессов, GIL обойдён)")
    print(f"  ускорение procs/sync: {dt_sync / dt_proc:5.2f}x   threads/sync: {dt_sync / dt_thr:5.2f}x")
    return rows


def main() -> None:
    print("=== bench: CPU спайдера/сканера — GIL vs multiprocessing ===")
    have = _try_import()
    print(f"  парсеры: bs4={have['bs4']} lxml={have['lxml']}")

    html = _big_html(3000)
    _bench_parsing(html, have)

    print("\n── Раздел B: мультипроцессинг (GIL vs прoцессы) ────────────────")
    print("  работа 1 — urllib-строки (urljoin/urlparse, как _add_link):")
    print("  работа 2 — регекс по HTML (как bs4-feed):")
    n_par = os.cpu_count() or 4
    n_par = min(n_par, 8)
    print(f"  (n_parallel={n_par})")
    _run_tasks("urllib-строки (_add_link)", _urlparse_work, (8_000,), n_par)
    _run_tasks("regex по HTML (парсинг)", _strsplit_work, (6,), n_par)


if __name__ == "__main__":
    main()

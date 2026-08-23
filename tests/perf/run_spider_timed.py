"""Одноразовый замер краулера на http://dvwa.local:7474/login.php (2026-08-17).

Авторизуется в DVWA (build_session_headers) для осмысленной сессии, затем
краулит yказанный URL через AsyncSpider и печатает время/итоги.
Не часть тестов — временная команда по запросу.
"""

from __future__ import annotations

import asyncio
import gc
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)

from pentool.modules.spider import AsyncSpider  # noqa: E402
from tests.perf.dvwa_session import build_session_headers  # noqa: E402

import sys as _sys
TARGET = _sys.argv[1] if len(_sys.argv) > 1 else "http://dvwa.local:7474/login.php"


async def main() -> None:
    headers = await build_session_headers()
    print(f"сессия: {headers.get('Cookie', '')[:40]}…")

    spider = AsyncSpider(max_depth=2, max_pages=200, concurrency=8,
                         timeout=15, extra_headers=headers)

    t0 = time.monotonic()
    try:
        result = await spider.crawl(TARGET)
    finally:
        pass
    dt = time.monotonic() - t0
    gc.collect()

    d = result.to_dict()
    print(f"\nTARGET: {TARGET}")
    print(f"ВРЕМЯ КРАУЛИНГА: {dt:.2f} с")
    print(f"  pages     : {d['pages_count']}")
    print(f"  endpoints : {d['endpoints_count']}")
    print(f"  forms     : {d['forms_count']}")
    print(f"  js files  : {d['js_files_count']}")
    print(f"  requests  : {d['total_requests']}")
    print(f"  errors    : {d['errors_count']}")
    if d.get('errors'):
        for e in list(d['errors'])[:5]:
            print(f"    err: {e}")
    rate = d['total_requests'] / dt if dt else 0
    print(f"  ~{rate:.1f} req/s")


if __name__ == "__main__":
    asyncio.run(main())

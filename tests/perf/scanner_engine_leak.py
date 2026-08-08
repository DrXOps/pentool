"""Level A — ScanEngine leak test БЕЗ сети (FakeHTTPClient).

Гипотеза H1 (см. MYPLANS/MEMORY_LEAK_INVESTIGATION_PLAN_2026-08-08.md):
`ScanEngine.run_active_on_requests()` строит `tasks_list` = ВСЕ комбинации
(seed_request × injection_point × check) и передаёт целиком в
`asyncio.gather(*[_run_one(...) for ...])`. Семафор (Threads в UI)
ограничивает только сколько задач одновременно шлют реальный HTTP, но НЕ
ограничивает, сколько `asyncio.Task` одновременно существует в памяти.

Этот тест изолирует именно эту часть — без реальной сети (FakeHTTPClient
отвечает мгновенно), без Spider, без TUI — чтобы отделить структурную
причину роста памяти от сетевых/I-O эффектов.

Замеряется:
  - RSS до/после каждого сценария
  - "потолок" одновременно живых asyncio.Task (peek каждые 50мс, пока
    идёт gather()) — прямая проверка H1
  - как этот потолок реагирует на Threads (concurrency) — если H1 верна,
    потолок почти не зависит от concurrency (растёт с
    n_requests × n_checks × points_per_request)
  - tracemalloc top-N для самого крупного сценария

Запуск:
    python3 tests/perf/scanner_engine_leak.py
    python3 tests/perf/scanner_engine_leak.py --max-requests 20000
"""

from __future__ import annotations

import argparse
import asyncio
import gc
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from tests.perf.fake_http_client import FakeHTTPClient  # noqa: E402
from tests.perf.memtrack import MemSampler, TraceSnaps, rss_mb, save_report  # noqa: E402

from pentool.modules.scanner.checks import (  # noqa: E402
    BrokenAuthCheck,
    CORSCheck,
    DOMXSSCheck,
    GraphQLCheck,
    HeaderInjectionCheck,
    InfoLeakCheck,
    JWTNoneCheck,
    LFICheck,
    MissingSecurityHeadersCheck,
    NoSQLInjectionCheck,
    OAuthCheck,
    OpenRedirectCheck,
    PathTraversalCheck,
    PrototypePollutionCheck,
    RCECheck,
    SensitiveDataCheck,
    SQLiCheck,
    SSRFCheck,
    SSTICheck,
    XSSCheck,
    XXECheck,
)
from pentool.modules.scanner.checks.header_injection import HostHeaderInjectionCheck  # noqa: E402
from pentool.modules.scanner.engine import ScanEngine  # noqa: E402
from pentool.utils.parser import ParsedRequest  # noqa: E402

# All 22 checks that don't require an active PRO feature flag beyond the
# base "scanner_pro" trial (SQLiUnionCheck needs "scanner_sqli_union" and
# is unavailable in this dev license — excluded, matches real runtime).
ALL_CHECKS_FACTORY = [
    MissingSecurityHeadersCheck, InfoLeakCheck, SQLiCheck, XSSCheck, SSTICheck,
    LFICheck, PathTraversalCheck, HeaderInjectionCheck, HostHeaderInjectionCheck,
    RCECheck, OpenRedirectCheck, SSRFCheck, XXECheck, CORSCheck, BrokenAuthCheck,
    JWTNoneCheck, NoSQLInjectionCheck, GraphQLCheck, PrototypePollutionCheck,
    DOMXSSCheck, OAuthCheck, SensitiveDataCheck,
]


def build_seed_requests(n: int, params_per_req: int = 3) -> list[ParsedRequest]:
    """N distinct GET requests with query params + cookie — gives each
    request several injection points (GET params + cookie + fixed header
    set), similar to what a real crawled site would produce."""
    reqs = []
    for i in range(n):
        query = "&".join(f"p{k}=val{i}_{k}" for k in range(params_per_req))
        reqs.append(ParsedRequest(
            method="GET",
            url=f"http://127.0.0.1:9/page/{i}?{query}",
            headers={
                "Cookie": f"session=abc{i}; theme=dark",
                "User-Agent": "pentool-leak-test",
            },
            body="",
        ))
    return reqs


async def run_one_scenario(
    n_requests: int,
    n_checks: int,
    concurrency: int,
    params_per_req: int = 3,
) -> dict:
    checks = [c() for c in ALL_CHECKS_FACTORY[:n_checks]]
    fake_client = FakeHTTPClient()
    engine = ScanEngine(db_path=":memory:", concurrency=concurrency, http_client=fake_client)
    engine.register_checks(checks)

    seed_requests = build_seed_requests(n_requests, params_per_req)

    gc.collect()
    rss_before = rss_mb()
    t0 = time.monotonic()

    peak_tasks = 0
    stop_flag = {"stop": False}

    async def _peek() -> None:
        nonlocal peak_tasks
        while not stop_flag["stop"]:
            n = len(asyncio.all_tasks())
            if n > peak_tasks:
                peak_tasks = n
            await asyncio.sleep(0.05)

    peeker = asyncio.create_task(_peek())
    try:
        findings = await engine.run_active_on_requests(seed_requests=seed_requests)
    finally:
        stop_flag["stop"] = True
        await peeker

    elapsed = time.monotonic() - t0
    gc.collect()
    rss_after = rss_mb()

    return {
        "n_requests": n_requests,
        "n_checks": n_checks,
        "concurrency": concurrency,
        "peak_tasks": peak_tasks,
        "elapsed_s": round(elapsed, 2),
        "rss_before_mb": round(rss_before, 1),
        "rss_after_mb": round(rss_after, 1),
        "delta_mb": round(rss_after - rss_before, 1),
        "findings": len(findings),
        "http_calls": fake_client.calls,
    }


async def main(max_requests: int) -> None:
    print("=== Level A: ScanEngine без сети (FakeHTTPClient) ===\n")

    n_checks_full = len(ALL_CHECKS_FACTORY)

    # ── Матрица 1: рост n_requests при фиксированном concurrency ──────────
    print("--- Матрица 1: n_requests растёт, concurrency=10, checks=все ---")
    scale_points = [p for p in (50, 200, 1000, 5000, max_requests) if p <= max_requests]
    scale_points = sorted(set(scale_points))
    results_scale = []
    for n in scale_points:
        r = await run_one_scenario(n, n_checks_full, concurrency=10)
        results_scale.append(r)
        print(r)

    # ── Матрица 2: H1 — Threads (concurrency) не спасает от роста задач ───
    print("\n--- Матрица 2: concurrency растёт при фиксированном n_requests ---")
    fixed_n = min(1000, max_requests)
    conc_points = [5, 10, 25, 50, 100]
    results_conc = []
    for c in conc_points:
        r = await run_one_scenario(fixed_n, n_checks_full, concurrency=c)
        results_conc.append(r)
        print(r)

    # ── tracemalloc top-N для самого крупного сценария ─────────────────────
    print("\n--- tracemalloc top-15 для самого крупного сценария ---")
    tracer = TraceSnaps()
    tracer.snap("before")
    biggest_n = scale_points[-1]
    await run_one_scenario(biggest_n, n_checks_full, concurrency=10)
    tracer.snap("after")
    top = tracer.diff("before", "after")
    for line in top:
        print(line)
    tracer.stop()

    # ── Вывод и вердикт по H1 ───────────────────────────────────────────────
    print("\n=== Вердикт H1 ===")
    tasks_vs_n = [(r["n_requests"], r["peak_tasks"]) for r in results_scale]
    print(f"peak_tasks по мере роста n_requests: {tasks_vs_n}")
    conc_vs_tasks = [(r["concurrency"], r["peak_tasks"]) for r in results_conc]
    print(f"peak_tasks по мере роста concurrency (n_requests={fixed_n}): {conc_vs_tasks}")
    task_spread = max(t for _, t in conc_vs_tasks) - min(t for _, t in conc_vs_tasks)
    print(
        f"Разброс peak_tasks при разных concurrency: {task_spread} "
        f"(если мал по сравнению с абсолютным peak_tasks — Threads НЕ "
        f"ограничивает рост числа живых задач => H1 подтверждена)"
    )

    ts = time.strftime("%Y%m%d_%H%M%S")
    out_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), f"scanner_engine_leak_{ts}.md")
    lines = [
        "# ScanEngine leak test (Level A — без сети)",
        "",
        f"Дата: {time.strftime('%Y-%m-%d %H:%M:%S')}",
        "",
        "## Матрица 1 — рост n_requests (concurrency=10, все чеки)",
        "",
        "| n_requests | peak_tasks | rss_before | rss_after | delta_mb | http_calls | findings |",
        "|---|---|---|---|---|---|---|",
    ]
    for r in results_scale:
        lines.append(
            f"| {r['n_requests']} | {r['peak_tasks']} | {r['rss_before_mb']} | "
            f"{r['rss_after_mb']} | {r['delta_mb']} | {r['http_calls']} | {r['findings']} |"
        )
    lines += [
        "",
        f"## Матрица 2 — рост concurrency (n_requests={fixed_n}, все чеки)",
        "",
        "| concurrency | peak_tasks | rss_before | rss_after | delta_mb | http_calls |",
        "|---|---|---|---|---|---|",
    ]
    for r in results_conc:
        lines.append(
            f"| {r['concurrency']} | {r['peak_tasks']} | {r['rss_before_mb']} | "
            f"{r['rss_after_mb']} | {r['delta_mb']} | {r['http_calls']} |"
        )
    lines += [
        "",
        "## tracemalloc top-15 (before -> after, самый крупный сценарий)",
        "```",
        *top,
        "```",
        "",
        f"## Вердикт H1",
        "",
        f"Разброс peak_tasks при разных concurrency (5..100), n_requests={fixed_n}: "
        f"{task_spread}",
        "",
        conc_vs_tasks.__repr__(),
    ]
    save_report(out_path, "\n".join(lines))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--max-requests", type=int, default=5000,
                         help="Максимум seed-запросов для самого крупного сценария "
                              "(осторожно: peak_tasks ~ max_requests × injection_points × 22 чека)")
    args = parser.parse_args()
    asyncio.run(main(args.max_requests))

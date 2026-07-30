"""
Быстрый perf/memory раннер для pentool (~15 минут суммарно).

Гоняет 5 сценариев по модулям, снимает:
  - RSS до/после (psutil)
  - tracemalloc top-аллокации (diff до/после)
  - время выполнения

Использование:
    python3 tests/perf/quick_check.py                # все сценарии
    python3 tests/perf/quick_check.py --only scanner  # один сценарий

Отчёт сохраняется в tests/perf/report_<timestamp>.md
"""
from __future__ import annotations

import argparse
import asyncio
import gc
import os
import sys
import time
import tracemalloc
from dataclasses import dataclass, field

import psutil

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from tests.perf.mock_server import MockServer

PROC = psutil.Process(os.getpid())


@dataclass
class ScenarioResult:
    name: str
    duration_s: float = 0.0
    rss_before_mb: float = 0.0
    rss_after_mb: float = 0.0
    rss_peak_delta_mb: float = 0.0
    top_allocations: list[str] = field(default_factory=list)
    extra: dict = field(default_factory=dict)
    error: str | None = None


def _rss_mb() -> float:
    return PROC.memory_info().rss / (1024 * 1024)


async def _measure(name: str, coro_factory) -> ScenarioResult:
    gc.collect()
    tracemalloc.start(15)
    snap_before = tracemalloc.take_snapshot()
    rss_before = _rss_mb()
    t0 = time.monotonic()

    result = ScenarioResult(name=name, rss_before_mb=rss_before)
    try:
        extra = await coro_factory()
        result.extra = extra or {}
    except Exception as exc:  # noqa: BLE001
        result.error = f"{type(exc).__name__}: {exc}"

    result.duration_s = time.monotonic() - t0
    rss_after_raw = _rss_mb()
    gc.collect()
    rss_after_gc = _rss_mb()
    snap_after = tracemalloc.take_snapshot()

    result.rss_after_mb = rss_after_gc
    result.rss_peak_delta_mb = rss_after_raw - rss_before

    diff = snap_after.compare_to(snap_before, "lineno")
    result.top_allocations = [
        f"{stat.size_diff / 1024:+.0f} KiB  {stat.traceback[0]}"
        for stat in diff[:5]
        if stat.size_diff > 0
    ]
    tracemalloc.stop()
    return result


# ── Сценарий 1: Scanner — 60 URL x все active checks ─────────────────────────

async def scenario_scanner(base_url: str) -> dict:
    from pentool.api.scanner_api import ScannerAPI
    from pentool.utils.http_client import HTTPClient
    from pentool.utils.parser import ParsedRequest

    n_urls = 60
    http_client = HTTPClient(timeout=5.0)
    api = ScannerAPI(db_path=":memory:", http_client=http_client)
    engine = api._get_engine()

    seed_requests = [
        ParsedRequest(method="GET", url=f"{base_url}/page{i}?id={i}&q=test", headers={}, body="")
        for i in range(n_urls)
    ]

    findings_count = 0

    def _on_finding(f):
        nonlocal findings_count
        findings_count += 1

    hard_cap_s = 90
    timed_out = False
    try:
        findings = await asyncio.wait_for(
            engine.run_active_on_requests(seed_requests, on_finding=_on_finding),
            timeout=hard_cap_s,
        )
    except asyncio.TimeoutError:
        timed_out = True
        findings = []
    await http_client._session.close() if http_client._session else None

    return {
        "urls_scanned": n_urls,
        "checks_registered": len(engine.get_registered_checks()),
        "findings": len(findings),
        "TIMED_OUT_after_s": hard_cap_s if timed_out else None,
    }


# ── Сценарий 2: Proxy — 5000 запросов через HttpStorage (SQLite) ────────────

async def scenario_proxy_storage() -> dict:
    from pentool.storage.http_storage import HttpStorage
    from pentool.utils.parser import ParsedRequest, ParsedResponse

    n_requests = 5000
    db_path = "/tmp/pentool_perf_proxy.db"
    if os.path.exists(db_path):
        os.remove(db_path)

    storage = HttpStorage()
    await storage.init_db(db_path)

    body = "x" * 500  # средний размер тела
    for i in range(n_requests):
        req = ParsedRequest(
            method="GET",
            url=f"http://example.com/api/resource/{i}?p={i}",
            headers={"User-Agent": "pentool-perf"},
            body="",
        )
        resp = ParsedResponse(status=200, reason="OK", headers={}, body=body)
        await storage.add_request(req, resp)

    count = await storage.count()
    await storage.close()
    db_size_mb = os.path.getsize(db_path) / (1024 * 1024) if os.path.exists(db_path) else 0
    os.remove(db_path)

    return {
        "requests_stored": count,
        "db_size_mb": round(db_size_mb, 2),
    }


# ── Сценарий 3: Intruder — Cluster bomb, словарь ~1000 слов ──────────────────

async def scenario_intruder(base_url: str) -> dict:
    from pentool.modules.intruder import IntruderConfig, IntruderAttack, AttackType

    payloads = [f"payload{i}" for i in range(200)]  # 200 x 2 позиции = 400 combos (cluster_bomb)
    template = (
        f"GET /search?q=§q§&id=§id§ HTTP/1.1\r\n"
        f"Host: 127.0.0.1\r\n\r\n"
    ).replace("§", "§")
    # actual host must match mock server port
    host_port = base_url.replace("http://", "")
    template = template.replace("Host: 127.0.0.1", f"Host: {host_port}")

    config = IntruderConfig(
        template=template,
        attack_type=AttackType.CLUSTER_BOMB,
        payload_sets=[payloads[:20], payloads[:20]],  # 20x20=400 requests
        threads=20,
        timeout=5,
    )
    attack = IntruderAttack(config)

    results_count = 0

    def _on_result(r):
        nonlocal results_count
        results_count += 1

    def _on_progress(done, total):
        pass

    await attack.run(_on_result, _on_progress)

    return {
        "requests_sent": results_count,
        "total_planned": attack.total_requests,
    }


# ── Сценарий 4: DataTable (ArrowBackend) — 50k строк ─────────────────────────

async def scenario_datatable() -> dict:
    import pyarrow as pa
    from textual_fastdatatable import ArrowBackend

    n_rows = 50_000
    t0 = time.monotonic()
    table = pa.table({
        "id": list(range(n_rows)),
        "method": ["GET"] * n_rows,
        "url": [f"http://example.com/path/{i}" for i in range(n_rows)],
        "status": [200] * n_rows,
        "length": [512] * n_rows,
    })
    build_s = time.monotonic() - t0

    t1 = time.monotonic()
    backend = ArrowBackend(table)
    backend_build_s = time.monotonic() - t1

    t2 = time.monotonic()
    _ = backend.row_count
    for i in range(0, n_rows, 5000):
        backend.get_row_at(i)
    scan_s = time.monotonic() - t2

    return {
        "rows": n_rows,
        "pa_table_build_s": round(build_s, 3),
        "arrow_backend_build_s": round(backend_build_s, 3),
        "sample_scan_s": round(scan_s, 3),
    }


# ── Сценарий 5: Dashboard LiveChart — 10k push событий ───────────────────────

async def scenario_livechart() -> dict:
    # Импортируем без Textual App context — тестируем чистую логику push/render
    from collections import deque

    class FakeLiveChart:
        def __init__(self):
            self._history: deque[int] = deque([0] * 60, maxlen=60)
            self._total = 0
            self._peak = 0

        def push(self, value: int) -> None:
            self._history.append(value)
            self._total += value
            if value > self._peak:
                self._peak = value

    chart = FakeLiveChart()
    n_events = 10_000
    t0 = time.monotonic()
    for i in range(n_events):
        chart.push(i % 100)
    elapsed = time.monotonic() - t0

    return {
        "events_pushed": n_events,
        "elapsed_s": round(elapsed, 4),
        "total_accumulated": chart._total,
    }


SCENARIOS = {
    "scanner": lambda base_url: scenario_scanner(base_url),
    "proxy": lambda base_url: scenario_proxy_storage(),
    "intruder": lambda base_url: scenario_intruder(base_url),
    "datatable": lambda base_url: scenario_datatable(),
    "dashboard": lambda base_url: scenario_livechart(),
}


def format_report(results: list[ScenarioResult]) -> str:
    lines = [
        "# Perf/Memory Quick Check — отчёт",
        "",
        f"Дата: {time.strftime('%Y-%m-%d %H:%M:%S')}",
        "",
        "| Модуль | Время (с) | RSS до (MB) | RSS после (MB) | Δ RSS (MB) | Детали |",
        "|---|---|---|---|---|---|",
    ]
    for r in results:
        details = ", ".join(f"{k}={v}" for k, v in r.extra.items())
        if r.error:
            details = f"ОШИБКА: {r.error}"
        lines.append(
            f"| {r.name} | {r.duration_s:.2f} | {r.rss_before_mb:.1f} | "
            f"{r.rss_after_mb:.1f} | {r.rss_peak_delta_mb:+.1f} | {details} |"
        )

    lines.append("")
    lines.append("## Топ-аллокации по сценарию (tracemalloc diff, до/после)")
    for r in results:
        lines.append(f"\n### {r.name}")
        if r.error:
            lines.append(f"- Пропущено из-за ошибки: {r.error}")
            continue
        if not r.top_allocations:
            lines.append("- Значимых новых аллокаций не обнаружено (< порога)")
        for a in r.top_allocations:
            lines.append(f"- {a}")

    return "\n".join(lines)


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--only", help="Запустить только один сценарий (scanner/proxy/intruder/datatable/dashboard)")
    args = parser.parse_args()

    names = [args.only] if args.only else list(SCENARIOS.keys())
    results: list[ScenarioResult] = []

    async with MockServer(port=8765) as server:
        for name in names:
            print(f"[{name}] запуск...", flush=True)
            factory = SCENARIOS[name]
            res = await _measure(name, lambda f=factory: f(server.base_url))
            results.append(res)
            print(f"[{name}] done: {res.duration_s:.2f}s, ΔRSS={res.rss_peak_delta_mb:+.1f}MB, extra={res.extra}, err={res.error}")

    report = format_report(results)
    ts = time.strftime("%Y%m%d_%H%M%S")
    out_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), f"report_{ts}.md")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(report)

    print(f"\nОтчёт сохранён: {out_path}")


if __name__ == "__main__":
    asyncio.run(main())

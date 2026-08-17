"""Нагрузочные тесты Scanner (PRO): активное сканирование.

Уровни (гибрид, LOAD_TESTING_PLAN_2026-08-17.md):
  A — без сети (FakeHTTPClient): структурный рост задач/памяти/ЦПУ без I/O.
        * рост n_requests при фикс. checks+concurrency;
        * матрица concurrency (5/10/25/50/100) при фикс. n_requests;
        * пик живых asyncio.Tasks vs concurrency (bounded pool).
  B — локальный MockBigSite (реальный HTTP): детерминированный крупный сайт,
        с реальными baseline-cache и fingerprint вызовами поверх payload-потока.
  C — DVWA (-level c, малый объём): реальный стек PHP/MySQL, сессия из
        dvwa_session, гигиеничный запуск (по 1 запросу на payload-класс).

Запуск:
    python3 tests/perf/load_scanner.py --level a
    python3 tests/perf/load_scanner.py --level b --concurrency 10 --max-requests 2000
    python3 tests/perf/load_scanner.py --level c
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

from pentool.utils.http_client import HTTPClient  # noqa: E402
from pentool.utils.parser import ParsedRequest  # noqa: E402
from tests.perf.fake_http_client import FakeHTTPClient  # noqa: E402
from tests.perf.memtrack import MemSampler, rss_mb, save_report  # noqa: E402
from tests.perf.mock_big_site import MockBigSite, MockBigSiteConfig  # noqa: E402

# Совпадает с production runtime: SQLiUnionCheck требует отдельного флага
# (scanner_sqli_union) — в dev-лицензии недоступен, исключаем.
ALL_CHECKS_FACTORY = [
    MissingSecurityHeadersCheck, InfoLeakCheck, SQLiCheck, XSSCheck, SSTICheck,
    LFICheck, PathTraversalCheck, HeaderInjectionCheck, HostHeaderInjectionCheck,
    RCECheck, OpenRedirectCheck, SSRFCheck, XXECheck, CORSCheck, BrokenAuthCheck,
    JWTNoneCheck, NoSQLInjectionCheck, GraphQLCheck, PrototypePollutionCheck,
    DOMXSSCheck, OAuthCheck, SensitiveDataCheck,
]

# Активные чеки (едут в run_active_on_requests) — passive-чеки работают на
# уже полученном ответе и не создают активного payload-потока/HTTP-запросов,
# поэтому для замеров планировщика/сети берём только их.
ACTIVE_CHECK_FACTORIES = [
    f for f in ALL_CHECKS_FACTORY
    if not f().passive
]
NUM_CORES = os.cpu_count() or 1


def build_seed_requests(n: int, params_per_req: int = 3) -> list[ParsedRequest]:
    """N distinct GET-запросов с query-параметрами + cookie (Level A)."""
    reqs = []
    for i in range(n):
        query = "&".join(f"p{k}=val{i}_{k}" for k in range(params_per_req))
        reqs.append(ParsedRequest(
            method="GET",
            url=f"http://127.0.0.1:9/page/{i}?{query}",
            headers={
                "Cookie": f"session=abc{i}; theme=dark",
                "User-Agent": "pentool-loadtest-scanner/1.0",
            },
            body="",
        ))
    return reqs


def url_to_parse_request(url: str, cookie: str = "") -> ParsedRequest:
    h = {"User-Agent": "pentool-loadtest-scanner/1.0"}
    if cookie:
        h["Cookie"] = cookie
    return ParsedRequest(method="GET", url=url, headers=h, body="")


# ═══════════════════════════════════════════════════════════════════════════
# Уровень A — без сети (FakeHTTPClient): структурный замер
# ═══════════════════════════════════════════════════════════════════════════

async def run_one_a(n_requests: int, n_checks: int, concurrency: int,
                    params_per_req: int = 3) -> dict:
    checks = [c() for c in ACTIVE_CHECK_FACTORIES[:n_checks]]
    fake = FakeHTTPClient()
    engine = ScanEngine(db_path=":memory:", concurrency=concurrency,
                        http_client=fake)
    engine.register_checks(checks)
    seeds = build_seed_requests(n_requests, params_per_req)

    gc.collect()
    rss_before = rss_mb()
    t0 = time.monotonic()

    peak_tasks = 0
    stop = {"go": True}

    async def _peek():
        nonlocal peak_tasks
        while stop["go"]:
            n = len(asyncio.all_tasks())
            if n > peak_tasks:
                peak_tasks = n
            await asyncio.sleep(0.02)

    peeker = asyncio.create_task(_peek())
    try:
        findings = await engine.run_active_on_requests(seed_requests=seeds)
    finally:
        stop["go"] = False
        await peeker

    elapsed = time.monotonic() - t0
    gc.collect()
    rss_after = rss_mb()
    return {"n_requests": n_requests, "n_checks": n_checks, "concurrency": concurrency,
            "peak_tasks": peak_tasks, "elapsed_s": round(elapsed, 2),
            "rss_before_mb": round(rss_before, 1), "rss_after_mb": round(rss_after, 1),
            "delta_mb": round(rss_after - rss_before, 1),
            "findings": len(findings), "http_calls": fake.calls}


async def run_level_a(args) -> dict:
    print("\n=== УРОВЕНЬ A: сканер без сети (FakeHTTPClient) ===\n")
    rows = []
    n_checks = min(args.n_checks, len(ACTIVE_CHECK_FACTORIES))
    scale = sorted(set(x for x in (50, 200, 1000, 5000, args.max_requests) if x <= args.max_requests))
    print(f"--- Matrix 1: рост n_requests (concurrency={args.concurrency}, {n_checks} чеков) ---")
    for n in scale:
        r = await run_one_a(n, n_checks, args.concurrency)
        rows.append(("scale", r))
        print(f"  n={n:<6} peak_tasks={r['peak_tasks']:<6} delta={r['delta_mb']:+5}MB "
              f"http_calls={r['http_calls']:<8} {r['elapsed_s']}s")

    print("--- Matrix 2: рост concurrency (n_requests=500, все чеки) ---")
    for c in (5, 10, 25, 50, 100):
        if c > args.concurrency * 4 and args.concurrency < 100:
            continue
        r = await run_one_a(min(500, args.max_requests), n_checks, c)
        rows.append(("conc", r))
        print(f"  conc={c:<4} peak_tasks={r['peak_tasks']:<6} delta={r['delta_mb']:+5}MB "
              f"http_calls={r['http_calls']:<8} {r['elapsed_s']}s")
    return {"rows": rows, "n_checks": n_checks}


# ═══════════════════════════════════════════════════════════════════════════
# Уровень B — локальный MockBigSite (реальный HTTP)
# ═══════════════════════════════════════════════════════════════════════════

async def run_level_b(args) -> dict:
    print("\n=== УРОВЕНЬ B: сканер на локальном MockBigSite (реальный HTTP) ===\n")
    checks = [c() for c in ACTIVE_CHECK_FACTORIES[: min(args.n_checks, len(ACTIVE_CHECK_FACTORIES))]]
    sampler = MemSampler(cpu=True)
    rows = []

    cfg = MockBigSiteConfig(n_pages=args.n_pages, params_per_page=args.params_per_page,
                            body_size=args.body_size, port=args.mock_port)
    async with MockBigSite(cfg) as site:
        seeds = [url_to_parse_request(u) for u in site.seed_urls(args.max_requests)]
        client = HTTPClient(verify_ssl=False)
        engine = ScanEngine(db_path=":memory:", concurrency=args.concurrency,
                            http_client=client)
        engine.register_checks(checks)

        calls = {"sent": 0}
        def _on_sent(*_a):
            calls["sent"] += 1

        sampler.tick(f"scan start: {len(seeds)} seed, conc={args.concurrency}, {len(checks)} checks")
        t0 = time.monotonic()
        try:
            findings = await engine.run_active_on_requests(
                seed_requests=seeds, on_request_sent=_on_sent)
        finally:
            await client.close()
        dt = time.monotonic() - t0
        gc.collect()
        sampler.tick("scan done", elapsed=round(dt, 3),
                     findings=len(findings), http_sent=calls["sent"])
        r = {"n_seed": len(seeds), "concurrency": args.concurrency,
             "elapsed_s": round(dt, 3), "findings": len(findings),
             "http_sent": calls["sent"], "n_checks": len(checks)}
        rows.append(r)
        print(f"  seed={len(seeds)} conc={args.concurrency} checks={len(checks)} "
              f"http_sent={calls['sent']} findings={len(findings)} {dt:.2f}s")
    out = {"rows": rows, "table": sampler.render_report("Scanner Level B — MockBigSite")}
    return out


# ═══════════════════════════════════════════════════════════════════════════
# Уровень C — DVWA (малый объём, сессия)
# ═══════════════════════════════════════════════════════════════════════════

def _sqlite_size(path: str | None) -> int | None:
    """Размер БД SQLite на диске (байт), или None если файла нет/в памяти."""
    if not path or path == ":memory:":
        return None
    try:
        return os.path.getsize(path)
    except OSError:
        return None


def _count_vuln_rows(db_path: str) -> int:
    """Число строк в таблице vulnerabilities БД (0 если нет БД/таблицы)."""
    if not db_path or db_path == ":memory:":
        return 0
    try:
        import sqlite3
        con = sqlite3.connect(db_path)
        try:
            return con.execute("SELECT COUNT(*) FROM vulnerabilities").fetchone()[0]
        finally:
            con.close()
    except sqlite3.Error:
        return 0


async def _background_profile(sampler: MemSampler, stop: dict, interval: float = 0.15):
    """Фоновый трекер: пишет CPU/RSS-точки в sampler, пока stop['go'] == True."""
    while stop["go"]:
        sampler.tick("profile _bg", heavy_gc_scan=False)
        await asyncio.sleep(interval)


async def run_level_c(args) -> dict:
    print("\n=== УРОВЕНЬ C: сканер на DVWA (реальный сайт, сессия) ===\n")
    from tests.perf.dvwa_session import DVWA_URL, build_session_headers

    headers = await build_session_headers()
    print(f"  сессия: {headers['Cookie'][:40]}…")

    # ── Дисковая БД вместо :memory: — чтобы измерить РАЗМЕР БД после скана
    #    (вопрос «сколько места растёт БД»). Файл во временной _data-папке.
    _data_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_data")
    os.makedirs(_data_dir, exist_ok=True)
    db_path = os.path.join(_data_dir, f"scan_c_{int(time.time())}.db")

    sampler = MemSampler(cpu=True)
    # Набор DVWA-страниц: главная + учебные уязвимые точки. Используем ТОЛЬКО
    # GET-точки чтения (не мутируем формы входа/создания). XSS_r — чтобы были
    # реальные findings (DVWA — учебная под XSS), SQLi и загрузка (upload —
    # отдельная GET-цепочка, печатает форму, не мутируем).
    seed_urls = [
        DVWA_URL + "/index.php",
        DVWA_URL + "/vulnerabilities/xss_r/?name=test",
        DVWA_URL + "/vulnerabilities/sqli/?id=1&Submit=Submit",
        DVWA_URL + "/vulnerabilities/brute/?username=admin&password=test&Login=Login",
    ]
    seeds = [url_to_parse_request(u, headers["Cookie"]) for u in seed_urls]

    client = HTTPClient(verify_ssl=False, extra_headers=headers)
    engine = ScanEngine(db_path=db_path, concurrency=args.concurrency,
                        http_client=client)
    # Лёгкие активные чеки: CORS (global), OpenRedirect (62), XSS (577) — XSS
    # даёт findings на xss_r; SQLi/exec — слишком много payload/побочных.
    engine.register_checks([
        c() for c in (CORSCheck, OpenRedirectCheck, XSSCheck)
        if not c().passive
    ])

    calls = {"sent": 0}
    def _on_sent(*_a):
        calls["sent"] += 1

    # ── Фоновый профиль CPU/RSS по времени (не просто start/done) ───────
    bg_stop = {"go": True}
    bg_task = asyncio.create_task(_background_profile(sampler, bg_stop))

    sampler.tick("scan DVWA start")
    t0 = time.monotonic()
    db_size_after_scan = (_sqlite_size(db_path) or 0)
    try:
        findings = await engine.run_active_on_requests(seed_requests=seeds,
                                                       on_request_sent=_on_sent)
        # run_active_on_requests возвращает findings в память, но НЕ пишет их
        # в БД — это делает внешний API-слой (ScannerAPI.start_active_scan).
        # Явно сохраняем, чтобы замерить РЕАЛЬНЫЙ рост БД от findings.
        try:
            await engine.save_findings(findings)
        except Exception as exc:
            print(f"  [!] save_findings: {exc}")
    finally:
        await client.close()
    db_size_after_scan = (_sqlite_size(db_path) or 0) - db_size_after_scan
    dt = time.monotonic() - t0
    bg_stop["go"] = False
    await bg_task
    gc.collect()

    db_size_after = _sqlite_size(db_path) or 0
    db_growth_from_scan = max(0, db_size_after_scan)
    vuln_rows = _count_vuln_rows(db_path)
    sampler.tick("scan DVWA done", elapsed=round(dt, 3),
                 findings=len(findings), http_sent=calls["sent"],
                 db_growth_kb=round(db_growth_from_scan / 1024, 1),
                 vuln_rows=vuln_rows)
    print(f"  seed={len(seeds)} http_sent={calls['sent']} findings={len(findings)} "
          f"БД+{db_growth_from_scan/1024:.1f}KB vuln_rows={vuln_rows} {dt:.2f}s")

    # Уборка временной БД
    try:
        os.remove(db_path)
    except OSError:
        pass

    # Спарклайн профиля — вынесем в out (смотреть по t_s)
    cpu_spark = sampler.cpu_series()
    return {"n_seed": len(seeds), "http_sent": calls["sent"], "findings": len(findings),
            "elapsed_s": round(dt, 3),
            "db_size_kb": round(db_size_after / 1024, 1),
            "db_growth_kb": round(db_growth_from_scan / 1024, 1),
            "vuln_rows": vuln_rows,
            "cpu_sparkline": _spark_str(cpu_spark),
            "rss_sparkline": _spark_str(sampler.rss_series()),
            "table": sampler.render_report("Scanner Level C — DVWA (профиль)")}


def _spark_str(vals: list[float]) -> str:
    """Текстовый sparkline (зависит от memtrack.sparkline, лёгкая обёртка)."""
    from tests.perf.memtrack import sparkline
    return sparkline(vals) if vals else ""


# ═══════════════════════════════════════════════════════════════════════════

async def main(args):
    ts = time.strftime("%Y%m%d_%H%M%S")
    out_path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            f"load_scanner_{ts}.md")
    all_report: list[str] = ["# Scanner load-test", "",
                             f"Дата: {time.strftime('%Y-%m-%d %H:%M:%S')}", ""]

    if args.level == "a":
        res = await run_level_a(args)
        lines = ["## Уровень A — без сети (FakeHTTPClient)", ""]
        lines += ["| n_requests | conc | peak_tasks | rss_before | rss_after | delta | http_calls | findings |",
                  "|---|---|---|---|---|---|---|---|"]
        for kind, r in res["rows"]:
            if kind == "scale":
                lines.append(f"| {r['n_requests']} | {r['concurrency']} | {r['peak_tasks']} "
                             f"| {r['rss_before_mb']} | {r['rss_after_mb']} | {r['delta_mb']} "
                             f"| {r['http_calls']} | {r['findings']} |")
        all_report += lines
        lines2 = ["", "| concurrency | peak_tasks | delta | http_calls |", "|---|---|---|---|"]
        for kind, r in res["rows"]:
            if kind == "conc":
                lines2.append(f"| {r['concurrency']} | {r['peak_tasks']} "
                              f"| {r['delta_mb']} | {r['http_calls']} |")
        all_report += lines2
    elif args.level == "b":
        res = await run_level_b(args)
        print("\n--- отчёт B ---")
        print(res["table"])
        all_report += ["## Уровень B — MockBigSite", "", res["table"]]
    elif args.level == "c":
        res = await run_level_c(args)
        print("\n--- отчёт C ---")
        print(res["table"])
        all_report += ["## Уровень C — DVWA", "", res["table"],
                       "### Метрики", "",
                       str({k: v for k, v in res.items() if k != "table"})]
    else:
        raise SystemExit(f"Неизвестный --level: {args.level}")

    save_report(out_path, "\n".join(all_report))


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Нагрузочные тесты Scanner")
    ap.add_argument("--level", default="a", choices=["a", "b", "c"])
    ap.add_argument("--max-requests", type=int, default=1000, help="Макс. seed (level a/b)")
    ap.add_argument("--n-checks", type=int, default=len(ACTIVE_CHECK_FACTORIES),
                    help=("Число активных чеков (для быстрого smoke ставьте < 5; "
                          "подробно: 1-2 — sqli/xss уже несут тысячи запросов)"))
    ap.add_argument("--concurrency", type=int, default=25, help="concurrency (level b/c)")
    ap.add_argument("--n-pages", type=int, default=3000, help="MockBigSite pages (level b)")
    ap.add_argument("--params-per-page", type=int, default=3)
    ap.add_argument("--body-size", type=int, default=800)
    ap.add_argument("--mock-port", type=int, default=8766)
    ap.add_argument("--no-cpu", action="store_true", help="Отключить CPU-метрики (level a)")
    args = ap.parse_args()
    asyncio.run(main(args))

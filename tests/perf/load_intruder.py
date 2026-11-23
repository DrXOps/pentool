"""Intruder load tests: payload generation and payload dispatch.

Levels (hybrid, see LOAD_TESTING_PLAN_2026-08-17.md):
  A — payload generation WITHOUT network:
        * NumericPayloadSource / CharPayloadSource (combinatorial explosion) —
          iteration, instant len()/head(), peak RSS O(1);
        * FilePayloadSource over a huge file (100MB..1GB behind a flag) —
          O(1) memory, len(), re-iteration (pitchfork/cluster-bomb
          re-read the file);
        * ProcessedPayloads on top of the file (urlencode/base64);
        * substitute_payload on a payload with 100 §-markers.
  B — dispatch to a local MockServer (real HTTP): IntruderAttack.run()
        for sniper/battering_ram/pitchfork/cluster_bomb, matrix threads × N,
        bounded worker pool (in-flight tasks ≤ threads), RSS/CPU.
  C — DVWA (--level c, low volume, session from dvwa_session).

Run:
    python3 tests/perf/load_intruder.py
    python3 tests/perf/load_intruder.py --level b --threads 10 --max-requests 5000
    python3 tests/perf/load_intruder.py --level a --giga      # pull in the 1GB file
    python3 tests/perf/load_intruder.py --level c            # DVWA smoke
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

from pentool.modules.intruder import (  # noqa: E402
    AttackType,
    CharPayloadSource,
    FilePayloadSource,
    IntruderAttack,
    IntruderConfig,
    NumericPayloadSource,
    ProcessedPayloads,
    count_markers,
    substitute_payload,
)
from pentool.utils.http_client import HTTPClient  # noqa: E402
from tests.perf.memtrack import MemSampler, rss_mb, save_report  # noqa: E402
from tests.perf.mock_server import MockServer  # noqa: E402

_DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_data")
_DEFAULT_FILE = os.path.join(_DATA_DIR, "payload_100MB.txt")


# Template for dispatch to MockServer: two markers (path + GET parameter).
def _template(port: int, path_marker: str = "§100§") -> str:
    return (
        f"GET /page/{path_marker}?p=§01§ HTTP/1.1\r\nHost: 127.0.0.1:{port}\r\nUser-Agent: pentool-loadtest/1.0\r\n\r\n"
    )


# ═══════════════════════════════════════════════════════════════════════════
# Level A — generation (no network)
# ═══════════════════════════════════════════════════════════════════════════


def _timeit(label: str, sampler: MemSampler, fn):
    """Run fn, measuring time and RSS/CPU via sampler, return (res, dt)."""
    sampler.tick(f"before {label}")
    t0 = time.monotonic()
    res = fn()
    dt = time.monotonic() - t0
    sampler.tick(f"after {label}", elapsed=round(dt, 3))
    return res, dt


def run_level_a(args) -> dict:
    print("\n=== УРОВЕНЬ A: генерация пейлоадов (без сети) ===\n")
    sampler = MemSampler(cpu=True)
    out: dict = {}

    # ── A1: NumericPayloadSource 1M ─────────────────────────────────────
    print("--- A1: NumericPayloadSource 1M строк ---")
    src_num = NumericPayloadSource(0, 1_000_000)
    sampler.tick("before len()")
    t0 = time.monotonic()
    n = len(src_num)
    dt_len = time.monotonic() - t0
    sampler.tick(f"after len()={n} in {dt_len * 1000:.0f}ms")

    # traversal
    def _walk_numeric():
        cnt = 0
        for _ in src_num:
            cnt += 1
        return cnt

    walked, dt_walk = _timeit("walk numeric 1M", sampler, _walk_numeric)
    print(f"  walked={walked:_} len()={n} len_dt={(dt_len * 1000):.0f}ms walk_dt={dt_walk:.2f}s")

    # ── A2: CharPayloadSource — combinatorial explosion ────────────────
    print("--- A2: CharPayloadSource 26 букв × len 1..5 (~11.9M) ---")
    src_char = CharPayloadSource("abcdefghijklmnopqrstuvwxyz", 1, 5)
    sampler.tick("before char len()")
    t0 = time.monotonic()
    n_char = len(src_char)
    dt_char_len = time.monotonic() - t0
    # head() must be instant — do not iterate through everything
    t0 = time.monotonic()
    h = src_char.head(5)
    dt_char_head = time.monotonic() - t0
    sampler.tick(f"after char len()={n_char} in {dt_char_len * 1000:.0f}ms, head(5)={dt_char_head * 1000:.0f}ms")
    print(
        f"  char len()={n_char:,} in {dt_char_len * 1000:.0f}ms, head(5)={h} in {dt_char_head * 1000:.0f}ms (должно быть мгновенно)"
    )
    out["char_len"] = n_char

    # ── A3: FilePayloadSource on a huge file ───────────────────────────
    print("--- A3: FilePayloadSource (O(1)-память) ---")
    file_path = args.file
    if args.giga and os.path.exists(file_path.replace("100MB", "1GB")):
        file_path = file_path.replace("100MB", "1GB")
    if not os.path.exists(file_path):
        from tests.perf.gen_payload_file import generate

        target = 1024**3 if "1GB" in file_path else 100 * 1024 * 1024
        print(f"  файл {file_path} не найден — генерирую ~{target // (1024 * 1024)}MiB...")
        res = generate(file_path, target_size=target)
        print(f"  сгенерирован: {res['lines']:,} строк, {res['bytes'] / (1024 * 1024):.0f}MiB")
    mb = os.path.getsize(file_path) / (1024 * 1024)
    print(f"  файл: {file_path} ({mb:.0f} MiB)")

    sfile = FilePayloadSource(file_path)
    sampler.tick("before file len()")
    t0 = time.monotonic()
    n_file = len(sfile)
    dt_file_len = time.monotonic() - t0
    # Cache the count so that a repeated len() is instant
    t0 = time.monotonic()
    _ = len(sfile)
    dt_file_len2 = time.monotonic() - t0
    sampler.tick(f"after file len()=={n_file} ({dt_file_len:.2f}s streem, cached {dt_file_len2 * 1000:.0f}ms)")

    # Traversal with RSS measurement — must stay flat (O(1))
    def _walk_file_stream():
        cnt = 0
        for _ in sfile:
            cnt += 1
        return cnt

    rss_before_walk = rss_mb()
    walked_f, dt_walk_f = _timeit("walk file stream(1 pass)", sampler, _walk_file_stream)
    gc.collect()
    rss_after_walk = rss_mb()
    print(
        f"  walked file: {walked_f:,} строк за {dt_walk_f:.2f}s | RSS {rss_before_walk:.0f}→{rss_after_walk:.0f}MiB "
        f"(Δ{rss_after_walk - rss_before_walk:+.0f}; O(1)-память если Δ≈0)"
    )

    # Re-iteration — pitchfork/cluster-bomb re-read the file
    def _walk_file_2pass():
        s2 = FilePayloadSource(file_path)
        c = 0
        for _ in s2:
            c += 1
        for _ in s2:
            c += 1
        return c

    walked2, dt_walk2 = _timeit("file 2 passes (re-iter)", sampler, _walk_file_2pass)
    print(f"  2 passes: {walked2:,} за {dt_walk2:.2f}s (пере-чтение файла)")

    # ── A4: ProcessedPayloads on top of the file ───────────────────────
    print("--- A4: ProcessedPayloads поверх FilePayloadSource (urlencode+base64) ---")
    s_proc = ProcessedPayloads(FilePayloadSource(file_path), ["urlencode", "base64"], _apply_ops)

    def _walk_processed():
        c = 0
        for _ in s_proc:
            c += 1
        return c

    # walk only the first 200_000 lines so a pure smoke run does not wait for gigabytes
    walked_p, dt_p = _timeit("walk processed (first 200k)", sampler, lambda: _walk_n_processed(s_proc, 200_000))
    print(f"  walked processed(200k): {walked_p:,} в {dt_p:.2f}s")

    # ── A5: substitute_payload on 100 markers ─────────────────────────
    print("--- A5: substitute_payload на 100 §-маркеров × 1000 payloads ---")
    many = ("a" + "§x§" + "b") * 100  # 100 markers
    assert count_markers(many) == 100
    t0 = time.monotonic()
    for i in range(1000):
        vals = [str(i)] * 100
        substitute_payload(many, vals)
    dt_sub = time.monotonic() - t0
    sampler.tick(f"after substitute_payload 100mark×1000 in {dt_sub * 1000:.0f}ms")
    print(f"  1000 substitution на 100-маркерном шаблоне: {dt_sub * 1000:.0f}ms ({dt_sub / 1000 * 1e6:.0f}µs/op)")

    out["file_lines"] = walked_f
    out["file_mb"] = round(mb, 1)
    out["table"] = sampler.render_report("Intruder Level A — генерация пейлоадов")
    return out


def _walk_n_processed(s, n: int):
    c = 0
    for _ in s:
        c += 1
        if c >= n:
            break
    return c


def _apply_ops(payload: str, ops: list[str]) -> str:
    from pentool.utils.coder import OPERATIONS

    for op in ops:
        fn = OPERATIONS.get(op)
        if fn is not None:
            try:
                payload = fn(payload)
            except Exception:
                pass
    return payload


# ═══════════════════════════════════════════════════════════════════════════
# Level B — dispatch to a local MockServer (real HTTP)
# ═══════════════════════════════════════════════════════════════════════════


async def run_attack_case(
    client, port: int, atype: AttackType, n_combos: int, threads: int, sampler: MemSampler
) -> dict:
    """One IntruderAttack.run() pass for one attack type over n_combos.

    client — a shared HTTPClient (owned by the caller), passed in as the
    injected client into IntruderAttack: run() does NOT close it (Bug-D), so
    one client is reused for all attacks and connections are recycled.
    """
    # Build payload sets that yield n_combos requests
    if atype == AttackType.SNIPER:
        # one marker in the path + one in query → n_positions=2 for a set of 1 position
        template = _template(port, "§1§")
        sets = [[f"p{i}" for i in range(n_combos // 2)]]
        total_expected = n_combos  # 2 positions × (n_combos//2) payloads ≈ n_combos
    elif atype == AttackType.BATTERING_RAM:
        template = _template(port, "§1§")
        sets = [[f"p{i}" for i in range(n_combos)]]
        total_expected = n_combos
    elif atype == AttackType.PITCHFORK:
        template = _template(port, "§1§")
        n = n_combos
        sets = [[f"p{i}" for i in range(n)], [f"q{i}" for i in range(n)]]
        total_expected = n
    elif atype == AttackType.CLUSTER_BOMB:
        template = _template(port, "§1§")
        a = max(1, int(n_combos**0.5))
        b = max(1, n_combos // a)
        sets = [[f"p{i}" for i in range(a)], [f"q{i}" for i in range(b)]]
        total_expected = a * b
    else:
        raise ValueError(atype)

    cfg = IntruderConfig(
        template=template,
        attack_type=atype,
        payload_sets=sets,
        threads=threads,
        timeout=10,
    )
    attack = IntruderAttack(cfg, db_path=":memory:", http_client=client)
    collected = {"results": 0, "statuses": set()}

    def on_result(r):
        collected["results"] += 1
        if r.response_status:
            collected["statuses"].add(r.response_status)

    def on_progress(done, total):
        pass

    sampler.tick(f"{atype.value} start threads={threads} total~{total_expected}")
    t0 = time.monotonic()
    await attack.run(on_result=on_result, on_progress=on_progress)
    dt = time.monotonic() - t0
    gc.collect()
    sampler.tick(
        f"{atype.value} done",
        elapsed=round(dt, 3),
        results=collected["results"],
        statuses=sorted(collected["statuses"]),
    )
    return {
        "type": atype.value,
        "threads": threads,
        "elapsed_s": round(dt, 3),
        "results": collected["results"],
        "statuses": sorted(collected["statuses"]),
        "req_per_s": round(collected["results"] / dt, 1) if dt else 0,
    }


async def run_level_b(args, client) -> dict:
    print("\n=== УРОВЕНЬ B: отправка на локальный MockServer ===\n")
    sampler = MemSampler(cpu=True)
    rows = []
    async with MockServer(port=args.mock_port) as server:
        port = server.port
        n_combos = args.max_requests
        threads = args.threads

        for atype in [AttackType.SNIPER, AttackType.BATTERING_RAM, AttackType.PITCHFORK, AttackType.CLUSTER_BOMB]:
            r = await run_attack_case(client, port, atype, n_combos, threads, sampler)
            rows.append(r)
            print(
                f"  {r['type']:14s} threads={threads:<3} results={r['results']:<7} "
                f"{r['elapsed_s']}s  {r['req_per_s']} req/s  statuses={r['statuses']}"
            )
    out = {"rows": rows, "table": sampler.render_report("Intruder Level B — отправка")}
    return out


# ═══════════════════════════════════════════════════════════════════════════
# Level C — DVWA smoke (low volume, with a session)
# ═══════════════════════════════════════════════════════════════════════════


async def run_level_c(args, client) -> dict:
    print("\n=== УРОВЕНЬ C: DVWA smoke (реальный сайт, сессия) ===\n")
    from tests.perf.dvwa_session import build_session_headers

    headers = await build_session_headers()
    print(f"  сессия: {headers['Cookie'][:40]}…")

    sampler = MemSampler(cpu=True)
    # Intruder against the DVWA login form — POST to /login.php with a username field.
    # Safe: even without a session DVWA just renders the login form again (or
    # redirects to login.php — status 30x), the intruder records it and moves on.
    # Content-Length is not hard-coded — aiohttp sets it from the real body
    # (the length varies with the payload). Small set (~9), capped by threads=2.
    template = (
        "POST /login.php HTTP/1.1\r\n"
        "Host: dvwa.local:7474\r\n"
        "Content-Type: application/x-www-form-urlencoded\r\n"
        "Cookie: " + headers["Cookie"] + "\r\n\r\n"
        "username=§admin§&password=password&Login=Login"
    )
    text_payloads = ["admin'--", "admin", "asd", "user", "root", "test", "or 1=1", "'\"", "x' OR '1'='1"]

    cfg = IntruderConfig(
        template=template, attack_type=AttackType.SNIPER, payload_sets=[text_payloads], threads=2, timeout=10
    )
    attack = IntruderAttack(cfg, db_path=":memory:", http_client=client)
    seen = {"n": 0, "statuses": set()}

    def on_result(r):
        seen["n"] += 1
        if r.response_status:
            seen["statuses"].add(r.response_status)

    sampler.tick("dvwa intruder start")
    t0 = time.monotonic()
    await attack.run(on_result=on_result, on_progress=lambda d, t: None)
    dt = time.monotonic() - t0
    sampler.tick("dvwa intruder done", elapsed=round(dt, 3))
    print(
        f"  надо {len(text_payloads) * 2} запросов (2 позиции), получено {seen['n']}, "
        f"statuses={sorted(seen['statuses'])}, {dt:.2f}s"
    )
    return {
        "n": seen["n"],
        "statuses": sorted(seen["statuses"]),
        "elapsed_s": round(dt, 3),
        "table": sampler.render_report("Intruder Level C — DVWA smoke"),
    }


# ═══════════════════════════════════════════════════════════════════════════


async def main(args):
    ts = time.strftime("%Y%m%d_%H%M%S")
    out_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), f"load_intruder_{ts}.md")
    all_report: list[str] = ["# Intruder load-test", "", f"Дата: {time.strftime('%Y-%m-%d %H:%M:%S')}", ""]

    if args.level == "a":
        res = run_level_a(args)
        print("\n--- отчёт A ---")
        print(res["table"])
        all_report += ["## Уровень A", "", res["table"]]
        res.pop("table", None)
        all_report += ["### Метрики", "", str(res)]
    elif args.level in ("b", "c"):
        client = HTTPClient(verify_ssl=False)
        try:
            if args.level == "b":
                res = await run_level_b(args, client)
            else:
                res = await run_level_c(args, client)
        finally:
            await client.close()
        print(f"\n--- отчёт {args.level.upper()} ---")
        print(res["table"])
        all_report += [f"## Уровень {args.level.upper()}", "", res["table"]]
        if "rows" in res:
            for r in res["rows"]:
                all_report += [
                    f"- {r['type']}: {r['results']} results в {r['elapsed_s']}s "
                    f"({r['req_per_s']} req/s), statuses={r['statuses']}"
                ]
        else:
            all_report += ["### Метрики", "", str({k: v for k, v in res.items() if k != "table"})]
        print("\n--- отчёт C ---")
        print(res["table"])
        all_report += ["## Уровень C", "", res["table"]]
        all_report += ["### Метрики", "", str(res)]
    else:
        raise SystemExit(f"Неизвестный --level: {args.level}")

    save_report(out_path, "\n".join(all_report))


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Нагрузочные тесты Intruder")
    ap.add_argument(
        "--level",
        default="a",
        choices=["a", "b", "c"],
        help="a=генерация (без сети), b=отправка (MockServer), c=DVWA smoke",
    )
    ap.add_argument("--threads", type=int, default=10, help="concurrency (level b)")
    ap.add_argument("--max-requests", type=int, default=2000, help="Число комбинаций на атаку (level b)")
    ap.add_argument("--file", default=_DEFAULT_FILE, help="Файл-пейлоад (level a)")
    ap.add_argument("--giga", action="store_true", help="Использовать 1ГБ-файл вместо 100МБ (level a)")
    ap.add_argument("--mock-port", type=int, default=8765, help="Порт локального MockServer (level b)")
    args = ap.parse_args()
    asyncio.run(main(args))

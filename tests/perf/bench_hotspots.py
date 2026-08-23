"""Микробенчмарк трёх CPU-горячих мест (по профилям из диагностики 2026-08-17).

Изолирует (без сети, на реалистичных объёмах) три функции, которые профили
показали как топ-CPU в сканере/интрудере:
  1. scanner mutator._inject_get — urlparse+urlencode на каждый payload
  2. utils.parser.parse_http_request — разбор raw-шаблона на каждый payload
  3. sqli._has_db_error — regex-перебор по ответу на каждый HTTP
Уже оптимизированный спайдер (spider) НЕ входит — он решён.

Цель: зафиксировать «до» (baseline) перед любыми правками, чтобы после
правки было с чем сравнить. Каждый замер N итераций, N берутся так, чтобы
уложиться в ~1-2с на прогон (стабильно, без таймаутов).

    python3 tests/perf/bench_hotspots.py
    python3 tests/perf/bench_hotspots.py --n 100000      # раздуть объём
"""

from __future__ import annotations

import argparse
import sys
import time

sys.path.insert(0, __file__.rsplit("/", 3)[0])

from pentool.utils.parser import parse_http_request  # noqa: E402

# Рабочая нагрузка-реалистичный шаблон интудера (как в прогонах).
_RAW_TMPL = (
    "GET /page/§id§?q=val&r=1#frag HTTP/1.1\r\n"
    "Host: 127.0.0.1:7474\r\n"
    "User-Agent: Mozilla/5.0\r\n"
    "Cookie: session=x; theme=dark\r\n\r\n"
)
_PAYLOAD = "<script>alert('xss_1')</script>"  # и SQLi-вид ниже чередуем


# ── 1) mutator._inject_get (аналог: сканер на каждый payload) ─────────────
def _bench_mutator_inject(n: int) -> float:
    # Используем РЕАЛЬНЫЙ RequestMutator._inject_get (не собственный parse_qs):
    # только так бенчмарк отражает оптимизацию кэша в классе.
    from pro.pentool.modules.scanner.mutator import RequestMutator
    url = "http://127.0.0.1:7474/page/42?q=val&r=1"
    mut = RequestMutator()
    t0 = time.monotonic()
    for _ in range(n):
        mut._inject_get(url, "q", _PAYLOAD)
    return time.monotonic() - t0


# ── 2) parse_http_request (интудер на каждый payload) ─────────────────────
def _bench_parse_http_request(n: int) -> float:
    t0 = time.monotonic()
    for _ in range(n):
        parse_http_request(_RAW_TMPL)
    return time.monotonic() - t0


# ── 3) sqli._has_db_error (на каждый ответ) — с суррогатом body ──────────
def _db_signature_body() -> str:
    """Синтетический ответ, похожий на DB-ошибку (трогает максимум сигнатур)."""
    return (
        "You have an error in your SQL syntax; SELECT * FROM users WHERE id ="
        "'<script>alert(1)</script>' ORDER BY 1 limit 0,1 --  "
    )


def _bench_has_db_error(n: int) -> float:
    # РЕАЛЬНАЯ функция имеет early-return на первом совпадении — замеряем
    # её как есть. Test-кейс: body с сигнатурой ошибки БД, совпадает рано.
    from pro.pentool.modules.scanner.checks.sqli import _has_db_error
    body = _db_signature_body()
    t0 = time.monotonic()
    for _ in range(n):
        _has_db_error(body)
    return time.monotonic() - t0


def _bench_has_db_error_worst(n: int) -> float:
    # Худший случай: ответы БЕЗ сигнатуры — функция должна обойти ВСЕ паттерны
    # всех БД до конца. Показывает «потолок» стоимости на защичавшийся сайт.
    from pro.pentool.modules.scanner.checks.sqli import _has_db_error
    body = "<html><body>OK — page rendered, 200 OK, no DB error</body></html>"
    t0 = time.monotonic()
    for _ in range(n):
        _has_db_error(body)
    return time.monotonic() - t0


def _cpu_load_sweep(fn, run_s: float = 0.5, n_batch: int = 1000) -> tuple[float, float, float]:
    """Плотно крутит fn() в течение ~run_s, меряет CPU% процесса по интервалу.

    fn — принимает размер батча (n). Крутим батчами по n_batch, повторяя
    пока не истечёт run_s. Возвращает (cpu_pct, user_sys_tot, per_batch_us):
      cpu_pct        — средний CPU% процесса за прогон (0..100×cores).
                        100 = полностью ОДНО ядро; >100 = несколько ядер.
      user_sys_tot   — сумма user+sys процесс (сек) за прогон.
      per_batch_us   — стоимость одного fn(n_batch) вызова.
    """
    import psutil
    proc = psutil.Process()
    proc.cpu_percent(interval=None)  # разогрев (первый вызов ноу-тро → 0)
    t = proc.cpu_times()

    batches = 0
    t0 = time.monotonic()
    end = t0 + run_s
    while time.monotonic() < end:
        fn(n_batch)
        batches += 1
    wall = time.monotonic() - t0

    t2 = proc.cpu_times()
    total = (t2.user - t.user) + (t2.system - t.system)
    cpu_pct = (total / wall * 100.0) if wall else 0.0
    return round(cpu_pct, 1), round(total, 3), round(wall * 1e6 / batches, 0)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--n", type=int, default=50_000)
    ap.add_argument("--cpu-sweep", type=float, default=0.5,
                    help="Секунд плотной петли для CPU-секции (0 = выкл)")
    args = ap.parse_args()
    if args.n < 1:
        raise SystemExit("--n должен быть ≥ 1")
    n = args.n

    print(f"=== bench_hotspots (n={n:,}) — baseline «до» правок ===")
    print(f"  шаблон/URL: 127.0.0.1:7474, N итераций {n:,}\n")

    # прогревающий вызов каждого, чтобы устранить JIT/кэш-шум
    _bench_mutator_inject(100)
    _bench_parse_http_request(100)
    _bench_has_db_error(100)

    results = {}

    d = _bench_mutator_inject(n)
    us = d / n * 1e6
    results["mutator_inject"] = (d, us)
    print(f"1) mutator._inject_get   : {d*1000:8.1f}ms  ({us:6.1f}µs/payload)")

    d = _bench_parse_http_request(n)
    us = d / n * 1e6
    results["parse_http_request"] = (d, us)
    print(f"2) parse_http_request    : {d*1000:8.1f}ms  ({us:6.1f}µs/запрос)")

    d = _bench_has_db_error(n)
    us = d / n * 1e6
    results["has_db_error"] = (d, us)
    print(f"3) sqli._has_db_error    : {d*1000:8.1f}ms  ({us:6.1f}µs/ответ, early-hit)")

    d = _bench_has_db_error_worst(n)
    us = d / n * 1e6
    results["has_db_error_worst"] = (d, us)
    print(f"3b) _has_db_error worst  : {d*1000:8.1f}ms  ({us:6.1f}µs/ответ, no-hit scan-all)")

    print("\nФормула для смета на прогон (при K активных payload):")
    for k, (total, us) in results.items():
        est_k = 60_000  # ~60k HTTP в типичном активном скане/интрудере
        print(f"   {k:20s} ~{us/1e6*est_k:6.2f}с при {est_k:,} вызовах")

    # ── CPU-секция: как КАЖДАЯ функция грузит ядро при плотной работе ──────
    print("\n=== CPU-нагрузка каждой функции (плотная петля, без сети) ===")
    print("  cpu%  = средний % процесса (100 = полностью одно ядро;")
    print("          >100 значит задействует несколько ядер процессами/потоками)\n")
    if args.cpu_sweep > 0:
        named = [
            ("mutator._inject_get   ", _bench_mutator_inject),
            ("parse_http_request    ", _bench_parse_http_request),
            ("sqli._has_db_error    ", _bench_has_db_error),
        ]
        for label, fn in named:
            # Баtch на вызов: поменьше, чтобы за run_s прогрузились десятки
            # батчей → CPU-замер стабилен. Для дешёвого parse_http_request
            # batch покрупнее.
            pct, tot, per_batch = _cpu_load_sweep(fn, args.cpu_sweep, n_batch=2000)
            print(f"  {label}: cpu% ≈ {pct:5.1f}  ({tot:.3f}c user+sys за "
                  f"{args.cpu_sweep:.1f}s)  ~{per_batch:7.0f}µs/batch(2000)")
    else:
        print("  (CPU-секция выключена: --cpu-sweep 0)")


if __name__ == "__main__":
    main()

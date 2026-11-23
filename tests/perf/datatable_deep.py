"""
Deep perf test for DataTable/ArrowBackend — kept separate from quick_check.py.

Separates:
  1. Cost of the first pyarrow/pandas import (one-off, does not scale).
  2. The real cost of inserting N rows (once the library is already imported).
  3. Behavior as size grows (10k / 50k / 100k) — linear growth or jumps.
  4. Behavior of a ProxyScreen-style backend rebuild (rebuild "from scratch" on every batch,
     which is effectively what _flush_pending_rows/_reload_table in screen.py do).

Run:
    python3 tests/perf/datatable_deep.py
"""

from __future__ import annotations

import gc
import os
import sys
import time

import psutil

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

PROC = psutil.Process(os.getpid())


def _rss_mb() -> float:
    return PROC.memory_info().rss / (1024 * 1024)


def _build_table(n_rows: int):
    import pyarrow as pa

    return pa.table(
        {
            "ID": pa.array(list(range(n_rows)), type=pa.int64()),
            "Host": pa.array(["example.com"] * n_rows, type=pa.string()),
            "Method": pa.array(["GET"] * n_rows, type=pa.string()),
            "URL": pa.array([f"http://example.com/path/resource/{i}?p={i}" for i in range(n_rows)], type=pa.string()),
            "Status": pa.array(["200"] * n_rows, type=pa.string()),
            "Size": pa.array([str(512 + (i % 2000)) for i in range(n_rows)], type=pa.string()),
            "Time": pa.array(["12:00:00"] * n_rows, type=pa.string()),
        }
    )


def step1_import_cost() -> dict:
    """Isolated cost of the first pyarrow/pandas/textual_fastdatatable import."""
    gc.collect()
    rss_before = _rss_mb()
    t0 = time.monotonic()
    import pyarrow  # noqa: F401
    from textual_fastdatatable import ArrowBackend  # noqa: F401

    elapsed = time.monotonic() - t0
    rss_after = _rss_mb()
    return {
        "step": "import pyarrow+textual_fastdatatable (первый раз)",
        "elapsed_s": round(elapsed, 3),
        "rss_before_mb": round(rss_before, 1),
        "rss_after_mb": round(rss_after, 1),
        "delta_mb": round(rss_after - rss_before, 1),
    }


def step2_scaling() -> list[dict]:
    """10k / 50k / 100k rows — after pyarrow has already been imported (step 1)."""
    from textual_fastdatatable import ArrowBackend

    results = []
    for n in (10_000, 50_000, 100_000):
        gc.collect()
        rss_before = _rss_mb()
        t0 = time.monotonic()
        table = _build_table(n)
        build_s = time.monotonic() - t0

        t1 = time.monotonic()
        backend = ArrowBackend(table)
        backend_s = time.monotonic() - t1

        t2 = time.monotonic()
        for i in range(0, n, max(n // 20, 1)):
            backend.get_row_at(i)
        scan_s = time.monotonic() - t2

        rss_after = _rss_mb()
        results.append(
            {
                "rows": n,
                "table_build_s": round(build_s, 3),
                "backend_build_s": round(backend_s, 3),
                "sample_scan_s": round(scan_s, 4),
                "rss_before_mb": round(rss_before, 1),
                "rss_after_mb": round(rss_after, 1),
                "delta_mb": round(rss_after - rss_before, 1),
            }
        )
        # Deliberately not deleting table/backend — the next step sees cumulative growth
    return results


def step3_rebuild_churn(n_rebuilds: int = 30, rows_per_rebuild: int = 2000) -> dict:
    """Simulation of ProxyScreen._flush_pending_rows: a full ArrowBackend rebuild
    N times in a row (as under live traffic, where every batch creates a new backend).
    Checks whether memory grows monotonically (a leak of old backend/table objects) or
    stabilizes (GC manages to reclaim the old objects in time).
    """
    from textual_fastdatatable import ArrowBackend

    gc.collect()
    rss_start = _rss_mb()
    rss_samples = []
    for i in range(n_rebuilds):
        table = _build_table(rows_per_rebuild)
        # keep a reference only to the latest backend — as in the real code:
        # the old one loses its last reference here
        _backend = ArrowBackend(table)
        if i % 5 == 0:
            gc.collect()
            rss_samples.append(round(_rss_mb(), 1))
    gc.collect()
    rss_end = _rss_mb()
    return {
        "n_rebuilds": n_rebuilds,
        "rows_per_rebuild": rows_per_rebuild,
        "rss_start_mb": round(rss_start, 1),
        "rss_end_mb": round(rss_end, 1),
        "delta_mb": round(rss_end - rss_start, 1),
        "rss_samples_every_5th": rss_samples,
    }


def main() -> None:
    print("=== Шаг 1: стоимость импорта библиотек ===")
    r1 = step1_import_cost()
    print(r1)

    print("\n=== Шаг 2: масштабирование 10k/50k/100k (после импорта) ===")
    r2 = step2_scaling()
    for r in r2:
        print(r)

    print("\n=== Шаг 3: churn — 30x пересборка backend по 2000 строк (имитация live-трафика) ===")
    r3 = step3_rebuild_churn()
    print(r3)

    ts = time.strftime("%Y%m%d_%H%M%S")
    out_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), f"datatable_deep_{ts}.md")
    lines = [
        "# DataTable/ArrowBackend — углублённый perf-тест",
        "",
        f"Дата: {time.strftime('%Y-%m-%d %H:%M:%S')}",
        "",
        "## Шаг 1 — стоимость первого импорта библиотек (разовая, не масштабируется)",
        "",
        f"- Время: {r1['elapsed_s']}s",
        f"- RSS до: {r1['rss_before_mb']} MB → после: {r1['rss_after_mb']} MB (Δ {r1['delta_mb']:+} MB)",
        "",
        "## Шаг 2 — масштабирование по числу строк (после импорта; кумулятивный RSS)",
        "",
        "| Строк | Построение pa.Table (с) | Построение ArrowBackend (с) | Скан 20 сэмплов (с) | RSS до (MB) | RSS после (MB) | Δ (MB) |",
        "|---|---|---|---|---|---|---|",
    ]
    for r in r2:
        lines.append(
            f"| {r['rows']:,} | {r['table_build_s']} | {r['backend_build_s']} | "
            f"{r['sample_scan_s']} | {r['rss_before_mb']} | {r['rss_after_mb']} | {r['delta_mb']:+} |"
        )
    lines += [
        "",
        "## Шаг 3 — Churn: 30 последовательных пересборок ArrowBackend по 2000 строк",
        "(имитирует `ProxyScreen._flush_pending_rows` / `_reload_table` под живым трафиком)",
        "",
        f"- RSS в начале: {r3['rss_start_mb']} MB",
        f"- RSS в конце: {r3['rss_end_mb']} MB",
        f"- Δ за 30 пересборок: {r3['delta_mb']:+} MB",
        f"- Замеры каждые 5 пересборок (после gc.collect): {r3['rss_samples_every_5th']}",
        "",
        "Если ряд `rss_samples_every_5th` монотонно растёт без стабилизации — это",
        "признак утечки (старые `ArrowBackend`/`pa.Table` не собираются GC полностью).",
        "Если ряд выходит на плато после первых 1-2 замеров — поведение здоровое:",
        "GC успевает освобождать предыдущие объекты между пересборками.",
    ]
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"\nОтчёт сохранён: {out_path}")


if __name__ == "__main__":
    main()

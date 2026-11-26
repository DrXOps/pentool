"""Micro-benchmarks of the hot paths the TUI calls on every frame or every result.

Why a separate file: `tui_deep.py` boots the whole app through the Textual pilot (seconds
per scenario, flaky timings under load). These measurements are pure functions — the code
that a screen calls in a loop — so they are stable, fast, and can run in CI. Together with
`tui_deep.py` they form the numbers for `docs/tui-audit/perf-report.md`.

Run:
    uv run python tests/perf/tui_hotpaths.py
"""

from __future__ import annotations

import gc
import statistics
import sys
import time
from pathlib import Path
from typing import Callable

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

RESULTS: list[tuple[str, int, float, float, float]] = []


class _Result:
    __slots__ = (
        "request_number",
        "payload_values",
        "response_status",
        "response_length",
        "response_time_ms",
        "error",
        "request_raw",
    )

    def __init__(self, number: int) -> None:
        self.request_number = number
        self.payload_values = [f"payload-{number}", "p2"]
        self.response_status = 200
        self.response_length = 1024
        self.response_time_ms = 12
        self.error = None
        self.request_raw = "GET /x HTTP/1.1\r\nHost: example.com\r\n\r\n"


def measure(label: str, rows: int, fn: Callable[[], object], repeat: int = 5) -> None:
    """Time *fn* a few times, keep the median — single runs are dominated by GC noise."""
    fn()  # warm up imports/caches
    timings = []
    for _ in range(repeat):
        gc.collect()
        start = time.perf_counter()
        fn()
        timings.append((time.perf_counter() - start) * 1000)
    median = statistics.median(timings)
    RESULTS.append((label, rows, median, min(timings), max(timings)))
    print(f"{label:<46} rows={rows:>7,}  median={median:8.1f} ms  (min {min(timings):.1f}, max {max(timings):.1f})")


def bench_results_arrow() -> None:
    from pentool.tui.screens.intruder.results_view import build_results_arrow

    columns = ["#", "Payload(s)", "Status", "Length", "Time(ms)", "Error"]
    for count in (1_000, 10_000):
        results = [_Result(i) for i in range(count)]
        measure("Intruder: build_results_arrow", count, lambda r=results: build_results_arrow(r, column_names=columns))
        measure(
            "Intruder: build_results_arrow + Extract",
            count,
            lambda r=results: build_results_arrow(r, column_names=columns, extract_patterns=[r"Host: (\S+)"]),
        )


def bench_proxy_arrow() -> None:
    from pentool.tui.screens.proxy.screen import _rows_to_arrow

    for count in (10_000, 50_000, 200_000):
        rows = [
            {
                "id": i,
                "method": "GET",
                "host": "example.com",
                "url": f"http://example.com/api/{i}",
                "status_code": 200,
                "length": 800,
                "timestamp": "2026-11-26T00:00:00",
                "comment": "",
            }
            for i in range(count)
        ]
        measure("Proxy: _rows_to_arrow", count, lambda r=rows: _rows_to_arrow(r))


def bench_history_paging() -> None:
    from pentool.tui.screens.proxy.history_view import count_text, merge_older, pick_row

    rows = [{"id": i} for i in range(200_000)]
    measure("Proxy: merge_older (200k + 300)", 200_300, lambda: merge_older(rows, [{"id": -i} for i in range(300)]))
    measure("Proxy: pick_row (200k)", 200_000, lambda: pick_row(rows, 199_999))
    measure("Proxy: count_text", 0, lambda: count_text(199_999, 200_000, more_available=True))


def bench_utils() -> None:
    """Decoder/Comparer work on user-sized texts (1 MB), not on toy strings."""
    from pentool.modules.decoder import decode_data, detect_encoding

    payload = "A" * (1 << 20)
    encoded = "QUFB" * (1 << 18)  # ~1 MB of base64
    measure("Utils: detect_encoding (1 MB)", 1 << 20, lambda: detect_encoding(encoded))
    measure("Utils: base64 decode (1 MB)", 1 << 20, lambda: decode_data(encoded, "base64"))
    measure("Utils: urlencode decode (1 MB)", 1 << 20, lambda: decode_data(payload.replace("A", "%41"), "url"))


def bench_diff() -> None:
    import difflib

    left = "\n".join(f"line {i}: some text" for i in range(5_000))
    right = "\n".join(f"line {i}: other text" for i in range(5_000))
    measure(
        "Comparer: unified diff (5k lines)",
        5_000,
        lambda: list(difflib.unified_diff(left.splitlines(), right.splitlines(), lineterm="")),
    )


def bench_counter() -> None:
    from pentool.tui.screens.proxy.history_view import HistoryCounter

    class _Label:
        def update(self, _text: str) -> None:
            return None

    label = _Label()
    counter = HistoryCounter("#x", "bench")
    counter.update(lambda _selector: label, 300, 200_000, more_available=True)
    measure("Proxy: counter no-op update", 0, lambda: counter.update(lambda _selector: label, 300, 200_000, True))


def main() -> int:
    for bench in (
        bench_results_arrow,
        bench_proxy_arrow,
        bench_history_paging,
        bench_utils,
        bench_diff,
        bench_counter,
    ):
        try:
            bench()
        except Exception as exc:  # noqa: BLE001 - a missing module must not stop the rest
            print(f"[skip] {bench.__name__}: {exc}")
    print("\n| Сценарий | Строк | Медиана, мс | min | max |")
    print("|---|---|---|---|---|")
    for label, rows, median, low, high in RESULTS:
        print(f"| {label} | {rows:,} | {median:.1f} | {low:.1f} | {high:.1f} |")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

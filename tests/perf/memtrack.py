"""Общий хелпер для perf/leak-тестов памяти.

Переиспользуемые примитивы поверх psutil/tracemalloc/gc:
  - MemSampler: периодический сэмплер RSS + число живых asyncio.Task +
    число живых объектов заданных классов (через gc.get_objects()).
  - snapshot_diff(): top-N diff двух tracemalloc-снимков.
  - sparkline(): текстовый график без внешних зависимостей (как в
    datatable_deep.py / dashboard live_dashboard.py).
  - render_report(): Markdown-отчёт с таблицей точек + спарклайном RSS.

Не часть pytest-сьюта — тяжёлые ручные прогоны, запускать напрямую:
    python3 tests/perf/scanner_engine_leak.py
"""

from __future__ import annotations

import asyncio
import gc
import os
import time
import tracemalloc
from dataclasses import dataclass, field

import psutil

PROC = psutil.Process(os.getpid())

_SPARK_CHARS = " ▁▂▃▄▅▆▇█"


def rss_mb() -> float:
    return PROC.memory_info().rss / (1024 * 1024)


def live_task_count() -> int:
    try:
        return len(asyncio.all_tasks())
    except RuntimeError:
        return 0


def count_instances(*classes: type) -> dict[str, int]:
    """Count live instances of given classes via gc.get_objects().

    Expensive (full heap walk) — call sparingly, not on every tick.
    """
    counts = {c.__name__: 0 for c in classes}
    for obj in gc.get_objects():
        for c in classes:
            if type(obj) is c:
                counts[c.__name__] += 1
    return counts


def sparkline(values: list[float], width: int = 40) -> str:
    if not values:
        return ""
    # Downsample/upsample to `width` buckets
    n = len(values)
    if n > width:
        step = n / width
        bucketed = [values[int(i * step)] for i in range(width)]
    else:
        bucketed = values
    lo, hi = min(bucketed), max(bucketed)
    span = (hi - lo) or 1.0
    chars = []
    for v in bucketed:
        idx = int((v - lo) / span * (len(_SPARK_CHARS) - 1))
        chars.append(_SPARK_CHARS[idx])
    return "".join(chars)


@dataclass
class Sample:
    label: str
    t_s: float
    rss_mb: float
    tasks: int
    extra: dict = field(default_factory=dict)


class MemSampler:
    """Manual-tick sampler — call .tick(label) at control points.

    Not a background timer on purpose: leak tests drive their own event
    loop and want deterministic sample points (e.g. "after N tasks
    scheduled", not "whatever happened to be running at t=2.0s").
    """

    def __init__(self, track_classes: tuple[type, ...] = ()) -> None:
        self.samples: list[Sample] = []
        self._t0 = time.monotonic()
        self._track_classes = track_classes

    def tick(self, label: str, heavy_gc_scan: bool = False, **extra) -> Sample:
        extra = dict(extra)
        if heavy_gc_scan and self._track_classes:
            extra["instances"] = count_instances(*self._track_classes)
        s = Sample(
            label=label,
            t_s=round(time.monotonic() - self._t0, 2),
            rss_mb=round(rss_mb(), 1),
            tasks=live_task_count(),
            extra=extra,
        )
        self.samples.append(s)
        return s

    def rss_series(self) -> list[float]:
        return [s.rss_mb for s in self.samples]

    def print_table(self) -> None:
        print(f"{'t(s)':>8} {'RSS(MB)':>9} {'tasks':>7}  label")
        for s in self.samples:
            print(f"{s.t_s:>8} {s.rss_mb:>9} {s.tasks:>7}  {s.label}"
                  + (f"  {s.extra}" if s.extra else ""))

    def render_report(self, title: str, notes: str = "") -> str:
        lines = [f"# {title}", "", f"Дата: {time.strftime('%Y-%m-%d %H:%M:%S')}", ""]
        if notes:
            lines += [notes, ""]
        lines += [
            "```",
            f"RSS(MB) spark: {sparkline(self.rss_series())}",
            f"  min={min(self.rss_series()):.1f}  max={max(self.rss_series()):.1f}  "
            f"delta={self.rss_series()[-1] - self.rss_series()[0]:.1f}",
            "```",
            "",
            "| t(s) | RSS(MB) | tasks | label | extra |",
            "|---|---|---|---|---|",
        ]
        for s in self.samples:
            lines.append(
                f"| {s.t_s} | {s.rss_mb} | {s.tasks} | {s.label} | "
                f"{s.extra if s.extra else ''} |"
            )
        return "\n".join(lines)


class TraceSnaps:
    """tracemalloc top-N diff helper."""

    def __init__(self, nframe: int = 10) -> None:
        tracemalloc.start(nframe)
        self._snaps: dict[str, "tracemalloc.Snapshot"] = {}

    def snap(self, label: str) -> None:
        gc.collect()
        self._snaps[label] = tracemalloc.take_snapshot()

    def diff(self, label_from: str, label_to: str, top: int = 15) -> list[str]:
        if label_from not in self._snaps or label_to not in self._snaps:
            return []
        stats = self._snaps[label_to].compare_to(
            self._snaps[label_from], "lineno"
        )
        out = []
        for stat in stats[:top]:
            out.append(str(stat))
        return out

    def stop(self) -> None:
        try:
            tracemalloc.stop()
        except Exception:
            pass


def save_report(path: str, content: str) -> None:
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    print(f"\nОтчёт сохранён: {path}")

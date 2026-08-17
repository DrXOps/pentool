"""Общий хелпер для perf/leak-тестов памяти и ЦПУ.

Переиспользуемые примитивы поверх psutil/tracemalloc/gc:
  - MemSampler: периодический сэмплер RSS + число живых asyncio.Task +
    число живых объектов заданных классов (через gc.get_objects()), а с
    флагом heavy_cpu — также CPU% (процесс/процесс+ядра), ctx-switches и
    накопленное user/sys время.
  - snapshot_diff(): top-N diff двух tracemalloc-снимков.
  - sparkline(): текстовый график без внешних зависимостей (как в
    datatable_deep.py / dashboard live_dashboard.py).
  - render_report(): Markdown-отчёт с таблицей точек + спарклайнами
    RSS и CPU.

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


def cpu_percent_total() -> float:
    """CPU% процесса за интервал с последнего вызова (ноу-тро, 0..Ncores*100)."""
    try:
        return PROC.cpu_percent(interval=None)
    except Exception:
        return 0.0


def cpu_times_user_sys() -> tuple[float, float]:
    """Накопленные user/sys секунды процесса (кумулятив, только растут)."""
    try:
        t = PROC.cpu_times()
        return t.user, t.system
    except Exception:
        return 0.0, 0.0


def cpu_ctx_switches() -> tuple[int, int]:
    """(voluntary, involuntary) ctx-switches процесса — кумулятив."""
    try:
        c = PROC.num_ctx_switches()
        return c.voluntary, c.involuntary
    except Exception:
        return 0, 0


def cpu_percent_percore() -> list[float]:
    """CPU% по каждому ядру системы за интервал с прошлого вызова."""
    try:
        return psutil.cpu_percent(interval=None, percpu=True)
    except Exception:
        return []


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
    # CPU-метрики заполняются только когда MemSampler(cpu=True) —
    # по умолчанию None, чтобы не тащить psutil-наценку в простых прогонах
    # (файл разделяют и leak-тесты, которым CPU-замер не нужен).
    cpu_pct: float | None = None
    cpu_user_sys: tuple[float, float] | None = None
    ctx_switches: tuple[int, int] | None = None
    perfcore_max: float | None = None
    extra: dict = field(default_factory=dict)


class MemSampler:
    """Manual-tick sampler — call .tick(label) at control points.

    Not a background timer on purpose: leak tests drive their own event
    loop and want deterministic sample points (e.g. "after N tasks
    scheduled", not "whatever happened to be running at t=2.0s").

    cpu=True включает замер CPU на каждый tick: cpu_pct — CPU% процесса за
    интервал с прошлого вызова (0..Ncores*100, ноу-тро уровень сразу после
    сна нагружающего задания), perfcore_max — максимум % по одному ядру,
    ctx_switches — (voluntary, involuntary) накопленные. cpu_user_sys —
    накопленное (user, sys) время.
    """

    def __init__(self, track_classes: tuple[type, ...] = (), *, cpu: bool = False) -> None:
        self.samples: list[Sample] = []
        self._t0 = time.monotonic()
        self._track_classes = track_classes
        self._cpu = cpu
        if cpu:
            # Первый вызов cpu_percent() возвращает 0.0 (нужен warm-up) —
            # делаем его на инициализации, чтобы первый tick имел реальный
            # дельта-интервал.
            cpu_percent_total()

    def tick(self, label: str, heavy_gc_scan: bool = False, **extra) -> Sample:
        extra = dict(extra)
        if heavy_gc_scan and self._track_classes:
            extra["instances"] = count_instances(*self._track_classes)
        cpu_pct = None
        cpu_user_sys = None
        ctx = None
        perfcore_max = None
        if self._cpu:
            cpu_pct = round(cpu_percent_total(), 1)
            cpu_user_sys = tuple(round(v, 2) for v in cpu_times_user_sys())  # type: ignore[assignment]
            ctx = cpu_ctx_switches()
            cores = cpu_percent_percore()
            perfcore_max = round(max(cores), 1) if cores else None
        s = Sample(
            label=label,
            t_s=round(time.monotonic() - self._t0, 2),
            rss_mb=round(rss_mb(), 1),
            tasks=live_task_count(),
            cpu_pct=cpu_pct,
            cpu_user_sys=cpu_user_sys,
            ctx_switches=ctx,
            perfcore_max=perfcore_max,
            extra=extra,
        )
        self.samples.append(s)
        return s

    def rss_series(self) -> list[float]:
        return [s.rss_mb for s in self.samples]

    def cpu_series(self) -> list[float]:
        return [s.cpu_pct for s in self.samples if s.cpu_pct is not None]

    def print_table(self) -> None:
        header = f"{'t(s)':>8} {'RSS(MB)':>9} {'tasks':>7}"
        if self._cpu:
            header += f" {'cpu%':>6} {'core%':>6} {'vsw':>6} {'isw':>6} {'user':>6} {'sys':>6}"
        header += "  label"
        print(header)
        for s in self.samples:
            row = f"{s.t_s:>8} {s.rss_mb:>9} {s.tasks:>7}"
            if self._cpu:
                vsw, isw = s.ctx_switches or (0, 0)
                user, sys = s.cpu_user_sys or (0.0, 0.0)
                row += (
                    f" {s.cpu_pct:>6.1f} {s.perfcore_max:>6.1f} "
                    f"{vsw:>6} {isw:>6} {user:>6.2f} {sys:>6.2f}"
                )
            print(row + "  " + s.label
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
        ]
        if self._cpu and self.cpu_series():
            lines += [
                f"CPU%   spark: {sparkline(self.cpu_series())}",
                f"  min={min(self.cpu_series()):.1f}  max={max(self.cpu_series()):.1f}",
            ]
        lines += ["```", ""]
        # Таблица
        if self._cpu:
            lines += [
                "| t(s) | RSS(MB) | tasks | cpu% | core% | vsw | isw | user(s) | sys(s) | label | extra |",
                "|---|---|---|---|---|---|---|---|---|---|---|",
            ]
        else:
            lines += ["| t(s) | RSS(MB) | tasks | label | extra |",
                      "|---|---|---|---|---|"]
        for s in self.samples:
            if self._cpu:
                vsw, isw = s.ctx_switches or (0, 0)
                user, sys = s.cpu_user_sys or (0.0, 0.0)
                lines.append(
                    f"| {s.t_s} | {s.rss_mb} | {s.tasks} | {s.cpu_pct} | {s.perfcore_max} "
                    f"| {vsw} | {isw} | {user} | {sys} | {s.label} | "
                    f"{s.extra if s.extra else ''} |"
                )
            else:
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

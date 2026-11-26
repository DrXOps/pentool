"""UI scenarios of the TUI on a real (pilot) application — the numbers for the release gate.

`tui_hotpaths.py` measures the pure functions a screen calls in a loop; this file measures
what the user actually experiences: how long a module takes to appear, how long a big table
takes to paint, how the window behaves under resize, and what the app costs when idle.

Run:
    uv run python tests/perf/tui_ui_scenarios.py
"""

from __future__ import annotations

import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

ROWS: list[tuple[str, str, str, str]] = []


def record(scenario: str, metric: str, value_ms: float | None = None, note: str = "") -> None:
    shown = f"{value_ms:.0f} мс" if value_ms is not None else "—"
    ROWS.append((scenario, metric, shown, note))
    print(f"{scenario:<38} {metric:<26} {shown:>8}  {note}")


async def settle(pilot, rounds: int = 12) -> None:
    for _ in range(rounds):
        await pilot.pause()


async def measure_switch(pilot, app, module: str) -> tuple[float, float]:
    """Time to the first frame and to a stable screen when opening *module*."""
    t0 = time.perf_counter()
    app.action_switch_module(module)
    await pilot.pause()
    first = (time.perf_counter() - t0) * 1000
    await settle(pilot, 20)
    stable = (time.perf_counter() - t0) * 1000
    return first, stable


async def main() -> int:
    import psutil

    from pentool.tui import module_catalog
    from pentool.tui.app import PentoolApp

    process = psutil.Process()
    boot_start = time.perf_counter()
    app = PentoolApp()
    app._skip_project_guard = True

    async with app.run_test(size=(160, 45)) as pilot:
        await settle(pilot, 15)
        record(
            "Старт приложения",
            "до интерактивности",
            (time.perf_counter() - boot_start) * 1000,
            f"RSS {process.memory_info().rss / 1e6:.0f} МБ",
        )

        # ── module switching: cold (first open) and warm (return) ──────────
        cold: list[float] = []
        warm: list[float] = []
        for entry in module_catalog.CATALOG:
            first, stable = await measure_switch(pilot, app, entry.id)
            cold.append(first)
            record(f"Открытие модуля: {entry.id}", "первый кадр", first, f"стабилизация {stable:.0f} мс")
        for entry in module_catalog.CATALOG[:5]:
            first, _stable = await measure_switch(pilot, app, entry.id)
            warm.append(first)
        record("Повторное переключение (5 модулей)", "медиана", statistics.median(warm), f"макс {max(warm):.0f} мс")

        # ── big tables: what a paint costs the widget ──────────────────────
        from pentool.tui.screens.proxy.screen import _rows_to_arrow

        app.action_switch_module("proxy")
        await settle(pilot, 25)
        table = app.query_one("#request-list")
        for count in (300, 5_000, 50_000):
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
            arrow = _rows_to_arrow(rows)
            t0 = time.perf_counter()
            table.set_data(arrow)
            await pilot.pause()
            record(f"Proxy: история {count:,} строк", "отрисовка таблицы", (time.perf_counter() - t0) * 1000)

        # ── resize round trip ─────────────────────────────────────────────
        t0 = time.perf_counter()
        await pilot.resize_terminal(80, 24)
        await pilot.pause()
        await pilot.resize_terminal(200, 60)
        await pilot.pause()
        record("Resize 80×24 ↔ 200×60", "перерасчёт раскладки", (time.perf_counter() - t0) * 1000)

        # ── idle cost ─────────────────────────────────────────────────────
        await settle(pilot, 5)
        cpu_before = process.cpu_times()
        rss_before = process.memory_info().rss
        await pilot.pause()
        time.sleep(3)
        cpu_after = process.cpu_times()
        cpu_seconds = (cpu_after.user + cpu_after.system) - (cpu_before.user + cpu_before.system)
        record("Простой (3 с)", "CPU", cpu_seconds / 3 * 100, "%")
        record("Простой (3 с)", "RSS", None, f"{(process.memory_info().rss - rss_before) / 1e6:+.1f} МБ")

    print("\n| Сценарий | Метрика | Значение | Примечание |")
    print("|---|---|---|---|")
    for scenario, metric, value, note in ROWS:
        print(f"| {scenario} | {metric} | {value} | {note} |")
    return 0


if __name__ == "__main__":
    import asyncio

    raise SystemExit(asyncio.run(main()))

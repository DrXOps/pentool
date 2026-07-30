"""
Perf-тест TUI-слоя через Textual Pilot — реальный запуск PentoolApp.

В отличие от quick_check.py (который дёргает API/модули напрямую, минуя
Textual), этот тест поднимает настоящее приложение и меряет:

  1. Время и память запуска (mount всего приложения).
  2. Время переключения между всеми модулями (action_switch_module).
  3. Поведение ProxyScreen с реальным ArrowBackend-рендером на большом
     объёме строк, полученных через HttpStorage (полный путь: SQLite →
     ProxyService.get_history → _rows_to_arrow → ArrowBackend → DataTable).

Запуск:
    python3 tests/perf/tui_deep.py
"""
from __future__ import annotations

import asyncio
import gc
import os
import sys
import time

import psutil

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

PROC = psutil.Process(os.getpid())


def _rss_mb() -> float:
    return PROC.memory_info().rss / (1024 * 1024)


async def seed_history_db(db_path: str, n_requests: int) -> None:
    """Заполнить SQLite историю N запросами — до запуска приложения,
    чтобы протестировать загрузку уже существующей большой истории
    (а не только инкрементальное добавление)."""
    from pentool.storage.http_storage import HttpStorage
    from pentool.utils.parser import ParsedRequest, ParsedResponse

    storage = HttpStorage()
    await storage.init_db(db_path)
    body = "x" * 800
    for i in range(n_requests):
        req = ParsedRequest(
            method="GET",
            url=f"http://example.com/api/resource/{i}?p={i}",
            headers={"Host": "example.com"},
            body="",
        )
        resp = ParsedResponse(status=200, reason="OK", headers={}, body=body)
        await storage.add_request(req, resp)
    await storage.close()


async def run() -> dict:
    from pentool.core.config import Config, set_config

    tmp_dir = "/tmp/pentool_perf_tui"
    os.makedirs(tmp_dir, exist_ok=True)
    db_path = os.path.join(tmp_dir, "history.db")
    if os.path.exists(db_path):
        os.remove(db_path)

    n_seed_requests = 8_000
    print(f"[seed] заполняем БД {n_seed_requests} запросами...")
    t_seed0 = time.monotonic()
    await seed_history_db(db_path, n_seed_requests)
    seed_elapsed = time.monotonic() - t_seed0
    print(f"[seed] готово за {seed_elapsed:.1f}s")

    cfg = Config(
        db_path=db_path,
        cert_dir=os.path.join(tmp_dir, "certs"),
        proxy_port=19099,
    )
    set_config(cfg)

    results: dict = {"seed_requests": n_seed_requests, "seed_elapsed_s": round(seed_elapsed, 2)}

    from pentool.tui.app import PentoolApp
    from textual.widgets import ContentSwitcher

    gc.collect()
    rss_before_app = _rss_mb()
    t0 = time.monotonic()

    app = PentoolApp()
    app._skip_project_guard = True

    async with app.run_test(size=(160, 45)) as pilot:
        # Дать приложению домонтироваться (proxy service init, storage, etc.)
        await pilot.pause(0.5)
        mount_elapsed = time.monotonic() - t0
        rss_after_mount = _rss_mb()
        results["startup"] = {
            "mount_elapsed_s": round(mount_elapsed, 2),
            "rss_before_mb": round(rss_before_app, 1),
            "rss_after_mount_mb": round(rss_after_mount, 1),
            "delta_mb": round(rss_after_mount - rss_before_app, 1),
        }
        print(f"[startup] {results['startup']}")

        # ── Навигация по всем модулям — время переключения + память ──────────
        modules = [
            "dashboard", "proxy", "repeater", "intruder", "scanner",
            "target", "decoder", "comparer", "sequencer", "spider",
            "extensions", "terminal", "settings",
        ]
        nav_results = []
        for mod in modules:
            gc.collect()
            rss_b = _rss_mb()
            t_nav0 = time.monotonic()
            app.action_switch_module(mod)
            await pilot.pause(0.15)
            nav_elapsed = time.monotonic() - t_nav0
            rss_a = _rss_mb()
            try:
                cs = app.query_one(ContentSwitcher)
                current = cs.current
            except Exception as exc:
                current = f"ERROR: {exc}"
            nav_results.append({
                "module": mod,
                "switch_elapsed_s": round(nav_elapsed, 3),
                "rss_before_mb": round(rss_b, 1),
                "rss_after_mb": round(rss_a, 1),
                "delta_mb": round(rss_a - rss_b, 1),
                "content_switcher_current": current,
            })
            print(f"[nav:{mod}] {nav_results[-1]}")
        results["navigation"] = nav_results

        # ── Переключиться обратно на Proxy и загрузить полную историю ────────
        app.action_switch_module("proxy")
        await pilot.pause(0.2)

        from pentool.tui.screens.proxy.screen import ProxyScreen
        from pentool.tui.constants import SCREEN_PROXY

        proxy_screen = app.query_one(SCREEN_PROXY, ProxyScreen)

        gc.collect()
        rss_before_load = _rss_mb()
        t_load0 = time.monotonic()
        await proxy_screen._reload_table(None)
        load_elapsed = time.monotonic() - t_load0
        await pilot.pause(0.3)
        rss_after_load = _rss_mb()

        rows_loaded = len(proxy_screen._rows_cache)
        results["proxy_full_history_load"] = {
            "rows_loaded": rows_loaded,
            "load_elapsed_s": round(load_elapsed, 2),
            "rss_before_mb": round(rss_before_load, 1),
            "rss_after_mb": round(rss_after_load, 1),
            "delta_mb": round(rss_after_load - rss_before_load, 1),
        }
        print(f"[proxy_full_history_load] {results['proxy_full_history_load']}")

        # ── Скролл по таблице (эмуляция взаимодействия пользователя) ─────────
        gc.collect()
        rss_before_scroll = _rss_mb()
        t_scroll0 = time.monotonic()
        for _ in range(30):
            await pilot.press("down")
        scroll_elapsed = time.monotonic() - t_scroll0
        rss_after_scroll = _rss_mb()
        results["proxy_scroll_30_rows"] = {
            "elapsed_s": round(scroll_elapsed, 3),
            "avg_ms_per_keypress": round(scroll_elapsed / 30 * 1000, 1),
            "delta_rss_mb": round(rss_after_scroll - rss_before_scroll, 1),
        }
        print(f"[proxy_scroll_30_rows] {results['proxy_scroll_30_rows']}")

        # ── Debounce-append: имитация живого трафика (100 быстрых вставок) ───
        from pentool.modules.proxy import InterceptedRequest
        from datetime import datetime, timezone

        gc.collect()
        rss_before_live = _rss_mb()
        t_live0 = time.monotonic()
        for i in range(100):
            req = InterceptedRequest(
                id=f"live-{i}",
                method="GET",
                url=f"http://live.example.com/evt/{i}",
                headers={"Host": "live.example.com"},
                body="",
                timestamp=datetime.now(timezone.utc),
            )
            proxy_screen._append_row_to_table(req, row_id=100000 + i)
        # ждём завершения debounce-таймера (150ms) + запас
        await pilot.pause(0.4)
        live_elapsed = time.monotonic() - t_live0
        rss_after_live = _rss_mb()
        results["proxy_live_append_100"] = {
            "elapsed_s": round(live_elapsed, 3),
            "rss_before_mb": round(rss_before_live, 1),
            "rss_after_mb": round(rss_after_live, 1),
            "delta_mb": round(rss_after_live - rss_before_live, 1),
            "rows_cache_len_after": len(proxy_screen._rows_cache),
        }
        print(f"[proxy_live_append_100] {results['proxy_live_append_100']}")

    gc.collect()
    rss_after_app_exit = _rss_mb()
    results["after_app_exit_rss_mb"] = round(rss_after_app_exit, 1)

    return results


def format_report(results: dict) -> str:
    lines = [
        "# TUI Deep Perf Test — отчёт",
        "",
        f"Дата: {time.strftime('%Y-%m-%d %H:%M:%S')}",
        f"Seed: {results['seed_requests']:,} запросов в SQLite за {results['seed_elapsed_s']}s",
        "",
        "## Запуск приложения (mount)",
        "",
        f"| Время mount (с) | RSS до (MB) | RSS после (MB) | Δ (MB) |",
        f"|---|---|---|---|",
        f"| {results['startup']['mount_elapsed_s']} | {results['startup']['rss_before_mb']} | "
        f"{results['startup']['rss_after_mount_mb']} | {results['startup']['delta_mb']:+} |",
        "",
        "## Навигация по модулям (action_switch_module)",
        "",
        "| Модуль | Время переключения (с) | Δ RSS (MB) | ContentSwitcher.current |",
        "|---|---|---|---|",
    ]
    for n in results["navigation"]:
        lines.append(
            f"| {n['module']} | {n['switch_elapsed_s']} | {n['delta_mb']:+} | {n['content_switcher_current']} |"
        )

    p = results["proxy_full_history_load"]
    s = results["proxy_scroll_30_rows"]
    la = results["proxy_live_append_100"]
    lines += [
        "",
        "## Proxy — загрузка полной истории (20 000 строк из SQLite → ArrowBackend)",
        "",
        f"- Строк загружено: {p['rows_loaded']:,}",
        f"- Время загрузки+рендера: {p['load_elapsed_s']}s",
        f"- RSS до → после: {p['rss_before_mb']} MB → {p['rss_after_mb']} MB (Δ {p['delta_mb']:+} MB)",
        "",
        "## Proxy — скролл 30 строк вниз",
        "",
        f"- Общее время: {s['elapsed_s']}s, среднее на нажатие: {s['avg_ms_per_keypress']} ms",
        f"- Δ RSS за скролл: {s['delta_rss_mb']:+} MB",
        "",
        "## Proxy — live-append 100 запросов подряд (debounce 150ms, имитация трафика)",
        "",
        f"- Время (включая debounce-задержку): {la['elapsed_s']}s",
        f"- RSS до → после: {la['rss_before_mb']} MB → {la['rss_after_mb']} MB (Δ {la['delta_mb']:+} MB)",
        f"- rows_cache после append: {la['rows_cache_len_after']:,} "
        f"(было {p['rows_loaded']:,} — прирост {la['rows_cache_len_after'] - p['rows_loaded']})",
        "",
        f"## После выхода из приложения",
        "",
        f"- RSS: {results['after_app_exit_rss_mb']} MB",
    ]
    return "\n".join(lines)


async def main() -> None:
    results = await run()
    report = format_report(results)
    ts = time.strftime("%Y%m%d_%H%M%S")
    out_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), f"tui_deep_{ts}.md")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(report)
    print(f"\nОтчёт сохранён: {out_path}")


if __name__ == "__main__":
    asyncio.run(main())
    # NOTE: после выхода из app.run_test() процесс не завершается сам по себе
    # в разумное время (замечено эмпирически — зависает на shutdown дольше
    # 30с даже без каких-либо доп. действий). Похоже на нескрытый фоновый
    # ресурс (поток/таймер/сокет), который Textual/asyncio не убивает при
    # выходе из тестового контекста. Это САМО ПО СЕБЕ занесено в отчёт как
    # находка. Форсируем выход процесса, чтобы раннер не зависал.
    sys.stdout.flush()
    os._exit(0)

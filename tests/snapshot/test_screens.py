"""Snapshot-тесты: визуальные регрессии TUI.

Запуск (первый раз — создать baseline):
    pytest tests/snapshot/ -v

Повторный запуск (сравнение с baseline):
    pytest tests/snapshot/ -v

Обновить baseline после намеренных изменений UI:
    pytest tests/snapshot/ --snapshot-update

Размер окна всегда 200×50 — полный экран без обрезки виджетов.
Снимки хранятся в tests/snapshot/snaps/*.svg
"""

from __future__ import annotations

import pytest

from pentool.core.config import Config, set_config

# Стандартный размер для всех снимков: полное окно
SNAP_SIZE = (200, 50)


@pytest.fixture(autouse=True)
def isolated_config(tmp_path):
    cfg = Config(
        db_path=str(tmp_path / "test.db"),
        cert_dir=str(tmp_path / "certs"),
        proxy_port=19095,
    )
    set_config(cfg)
    return cfg


@pytest.mark.snapshot
@pytest.mark.asyncio
@pytest.mark.xfail(strict=False, reason="DashboardScreen contains TerminalScreen with non-deterministic bash output")
async def test_proxy_screen(assert_snapshot) -> None:
    """Proxy-экран по умолчанию: тулбар, субтабы, пустая таблица."""
    from pentool.tui.app import PentoolApp
    app = PentoolApp()
    app._skip_project_guard = True
    async with app.run_test(size=SNAP_SIZE) as pilot:
        await pilot.pause()
        await pilot.pause()
        svg = app.export_screenshot()
    assert_snapshot(svg, "proxy_screen")


@pytest.mark.snapshot
@pytest.mark.asyncio
async def test_repeater_screen(assert_snapshot) -> None:
    """Repeater-экран: TabbedContent с вкладкой Tab 1, два редактора."""
    from pentool.tui.app import PentoolApp
    app = PentoolApp()
    app._skip_project_guard = True
    async with app.run_test(size=SNAP_SIZE) as pilot:
        await pilot.pause()
        await pilot.press("R")
        await pilot.pause()
        await pilot.pause()
        svg = app.export_screenshot()
    assert_snapshot(svg, "repeater_screen")


@pytest.mark.snapshot
@pytest.mark.asyncio
async def test_intruder_screen(assert_snapshot) -> None:
    """Intruder-экран: тулбар Start/Pause/Stop, Positions+Payloads, Results."""
    from pentool.tui.app import PentoolApp
    app = PentoolApp()
    app._skip_project_guard = True
    async with app.run_test(size=SNAP_SIZE) as pilot:
        await pilot.pause()
        await pilot.press("I")
        await pilot.pause()
        await pilot.pause()
        svg = app.export_screenshot()
    assert_snapshot(svg, "intruder_screen")


@pytest.mark.snapshot
@pytest.mark.asyncio
async def test_decoder_screen(assert_snapshot) -> None:
    """Decoder-экран: заглушка Coming in Stage 13."""
    from pentool.tui.app import PentoolApp
    app = PentoolApp()
    app._skip_project_guard = True
    async with app.run_test(size=SNAP_SIZE) as pilot:
        await pilot.pause()
        await pilot.press("D")
        await pilot.pause()
        svg = app.export_screenshot()
    assert_snapshot(svg, "decoder_screen")


@pytest.mark.snapshot
@pytest.mark.asyncio
async def test_settings_screen(assert_snapshot) -> None:
    """Settings-экран: Interface/Proxy/Hotkeys/Project субтабы."""
    from pentool.tui.app import PentoolApp
    app = PentoolApp()
    async with app.run_test(size=SNAP_SIZE) as pilot:
        await pilot.pause()
        await pilot.press("ctrl+comma")
        await pilot.pause()
        svg = app.export_screenshot()
    assert_snapshot(svg, "settings_screen")


@pytest.mark.snapshot
@pytest.mark.asyncio
@pytest.mark.xfail(strict=False, reason="DashboardScreen contains TerminalScreen with non-deterministic bash output")
async def test_proxy_intercept_tab(assert_snapshot) -> None:
    """Proxy → вкладка Intercept: пустой перехват."""
    from pentool.tui.app import PentoolApp
    app = PentoolApp()
    app._skip_project_guard = True
    async with app.run_test(size=SNAP_SIZE) as pilot:
        await pilot.pause()
        # По умолчанию активна вкладка Intercept
        svg = app.export_screenshot()
    assert_snapshot(svg, "proxy_intercept_tab")


@pytest.mark.snapshot
@pytest.mark.asyncio
async def test_repeater_with_request(assert_snapshot) -> None:
    """Repeater: загружен реальный HTTP-запрос в редактор."""
    from pentool.tui.app import PentoolApp
    from pentool.tui.screens.repeater.screen import RepeaterScreen
    from pentool.utils.parser import ParsedRequest

    app = PentoolApp()
    app._skip_project_guard = True
    async with app.run_test(size=SNAP_SIZE) as pilot:
        await pilot.pause()
        await pilot.press("R")
        await pilot.pause()

        req = ParsedRequest(
            method="POST",
            url="http://target.example.com/api/login",
            headers={
                "Host": "target.example.com",
                "Content-Type": "application/json",
                "Authorization": "Bearer eyJ0eXAiOiJKV1Q...",
            },
            body='{"username":"admin","password":"secret123"}',
        )
        screen = app.query_one(RepeaterScreen)
        screen.load_request(req)
        await pilot.pause()
        svg = app.export_screenshot()
    assert_snapshot(svg, "repeater_with_request")


@pytest.mark.snapshot
@pytest.mark.asyncio
async def test_intruder_with_markers(assert_snapshot) -> None:
    """Intruder: запрос с маркерами §§ загружен в Positions."""
    from pentool.tui.app import PentoolApp
    from pentool.tui.screens.intruder.screen import IntruderScreen
    from pentool.utils.parser import ParsedRequest

    app = PentoolApp()
    app._skip_project_guard = True
    async with app.run_test(size=SNAP_SIZE) as pilot:
        await pilot.pause()
        await pilot.press("I")
        await pilot.pause()

        req = ParsedRequest(
            method="POST",
            url="http://target.example.com/login",
            headers={"Host": "target.example.com"},
            body="user=§admin§&pass=§secret§",
        )
        screen = app.query_one(IntruderScreen)
        screen.load_request(req)
        await pilot.pause()
        svg = app.export_screenshot()
    assert_snapshot(svg, "intruder_with_markers")


@pytest.mark.snapshot
@pytest.mark.asyncio
@pytest.mark.xfail(strict=False, reason="TerminalScreen bash output is non-deterministic")
async def test_module_tabs_proxy_active(assert_snapshot) -> None:
    """ModuleTabs: активна вкладка Proxy (подсвечена синим)."""
    from pentool.tui.app import PentoolApp
    app = PentoolApp()
    app._skip_project_guard = True
    async with app.run_test(size=SNAP_SIZE) as pilot:
        await pilot.pause()
        svg = app.export_screenshot()
    assert_snapshot(svg, "module_tabs_proxy")


@pytest.mark.snapshot
@pytest.mark.asyncio
async def test_module_tabs_repeater_active(assert_snapshot) -> None:
    """ModuleTabs: активна вкладка Repeater."""
    from pentool.tui.app import PentoolApp
    app = PentoolApp()
    app._skip_project_guard = True
    async with app.run_test(size=SNAP_SIZE) as pilot:
        await pilot.pause()
        await pilot.press("R")
        await pilot.pause()
        svg = app.export_screenshot()
    assert_snapshot(svg, "module_tabs_repeater")


@pytest.mark.snapshot
@pytest.mark.asyncio
async def test_comparer_screen(assert_snapshot) -> None:
    """Comparer-экран: side-by-side diff."""
    from pentool.tui.app import PentoolApp
    app = PentoolApp()
    app._skip_project_guard = True
    async with app.run_test(size=SNAP_SIZE) as pilot:
        await pilot.pause()
        await pilot.press("C")
        await pilot.pause()
        svg = app.export_screenshot()
    assert_snapshot(svg, "comparer_screen")


@pytest.mark.snapshot
@pytest.mark.asyncio
@pytest.mark.xfail(strict=False, reason="Live Dashboard has time-dependent widgets (sparkline, resource monitor)")
async def test_dashboard_live_tab(assert_snapshot) -> None:
    """Dashboard → вкладка Live: TrafficSparkline, BubbleChart, EventFeed."""
    from pentool.tui.app import PentoolApp
    app = PentoolApp()
    app._skip_project_guard = True
    async with app.run_test(size=SNAP_SIZE) as pilot:
        await pilot.pause()
        # Переключаемся на Dashboard
        await pilot.press("ctrl+d")
        await pilot.pause()
        await pilot.pause()
        svg = app.export_screenshot()
    assert_snapshot(svg, "dashboard_live_tab")

    """Sequencer-экран: энтропийный анализ токенов."""
    from pentool.tui.app import PentoolApp
    app = PentoolApp()
    app._skip_project_guard = True
    async with app.run_test(size=SNAP_SIZE) as pilot:
        await pilot.pause()
        await pilot.press("Q")
        await pilot.pause()
        svg = app.export_screenshot()
    assert_snapshot(svg, "sequencer_screen")

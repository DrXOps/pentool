"""Snapshot tests: TUI visual regressions.

Run (first time — create baseline):
    pytest tests/snapshot/ -v

Subsequent run (compare with baseline):
    pytest tests/snapshot/ -v

Update baseline after intentional UI changes:
    pytest tests/snapshot/ --snapshot-update

Window size is always 200x50 — full screen without widget clipping.
Snapshots are stored in tests/snapshot/snaps/*.svg
"""

from __future__ import annotations

import pytest

from pentool.core.config import Config, set_config

# Standard size for all snapshots: full window
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
    """Proxy screen by default: toolbar, subtabs, empty table."""
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
    """Repeater screen: TabbedContent with Tab 1, two editors."""
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
    """Intruder screen: Start/Pause/Stop toolbar, Positions+Payloads, Results."""
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
    """Decoder screen: Coming in Stage 13 stub."""
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
    """Settings screen: Interface/Proxy/Hotkeys/Project subtabs."""
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
    """Proxy → Intercept tab: empty intercept."""
    from pentool.tui.app import PentoolApp
    app = PentoolApp()
    app._skip_project_guard = True
    async with app.run_test(size=SNAP_SIZE) as pilot:
        await pilot.pause()
        # Intercept tab is active by default
        svg = app.export_screenshot()
    assert_snapshot(svg, "proxy_intercept_tab")


@pytest.mark.snapshot
@pytest.mark.asyncio
async def test_repeater_with_request(assert_snapshot) -> None:
    """Repeater: real HTTP request loaded into editor."""
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
    """Intruder: request with §§ markers loaded into Positions."""
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
    """ModuleTabs: Proxy tab active (highlighted in blue)."""
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
    """ModuleTabs: Repeater tab active."""
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
    """Comparer screen: side-by-side diff."""
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
    """Dashboard screen (live widgets — chart, threat meter, resources)."""
    from pentool.tui.app import PentoolApp
    app = PentoolApp()
    app._skip_project_guard = True
    async with app.run_test(size=SNAP_SIZE) as pilot:
        await pilot.pause()
        # Switch to Dashboard
        await pilot.press("ctrl+d")
        await pilot.pause()
        await pilot.pause()
        svg = app.export_screenshot()
    assert_snapshot(svg, "dashboard_live_tab")

    """Sequencer screen: token entropy analysis."""
    from pentool.tui.app import PentoolApp
    app = PentoolApp()
    app._skip_project_guard = True
    async with app.run_test(size=SNAP_SIZE) as pilot:
        await pilot.pause()
        await pilot.press("Q")
        await pilot.pause()
        svg = app.export_screenshot()
    assert_snapshot(svg, "sequencer_screen")

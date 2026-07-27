"""E2E: keyboard navigation between modules."""
from __future__ import annotations

import pytest
from textual.widgets import ContentSwitcher

from pentool.tui.app import PentoolApp
from pentool.tui.screens.scanner.screen import ScannerScreen  # noqa: F401


@pytest.mark.e2e
class TestNavigation:

    async def test_switch_to_repeater(self) -> None:
        """Клавиша R → RepeaterScreen активна в ContentSwitcher."""
        app = PentoolApp()
        app._skip_project_guard = True
        async with app.run_test(size=(120, 30)) as pilot:
            await pilot.pause()
            await pilot.press("R")
            await pilot.pause()
            await pilot.pause()
            cs = app.query_one(ContentSwitcher)
            assert cs.current == "screen-repeater"

    async def test_switch_to_intruder(self) -> None:
        """Клавиша I → IntruderScreen активна в ContentSwitcher."""
        app = PentoolApp()
        app._skip_project_guard = True
        async with app.run_test(size=(120, 30)) as pilot:
            await pilot.pause()
            await pilot.press("I")
            await pilot.pause()
            await pilot.pause()
            cs = app.query_one(ContentSwitcher)
            assert cs.current == "screen-intruder"

    async def test_switch_to_decoder(self) -> None:
        """Клавиша D → DecoderScreen активна в ContentSwitcher."""
        app = PentoolApp()
        app._skip_project_guard = True
        async with app.run_test(size=(120, 30)) as pilot:
            await pilot.pause()
            await pilot.press("D")
            await pilot.pause()
            await pilot.pause()
            cs = app.query_one(ContentSwitcher)
            assert cs.current == "screen-decoder"

    async def test_back_to_proxy(self) -> None:
        """R → P → ProxyScreen активна в ContentSwitcher."""
        app = PentoolApp()
        app._skip_project_guard = True
        async with app.run_test(size=(120, 30)) as pilot:
            await pilot.pause()
            await pilot.press("R")
            await pilot.pause()
            await pilot.press("P")
            await pilot.pause()
            await pilot.pause()
            cs = app.query_one(ContentSwitcher)
            assert cs.current == "screen-proxy"

    async def test_switch_to_scanner(self) -> None:
        """Клавиша S → ScannerScreen активна в ContentSwitcher."""
        app = PentoolApp()
        app._skip_project_guard = True
        async with app.run_test(size=(120, 30)) as pilot:
            await pilot.pause()
            await pilot.press("S")
            await pilot.pause()
            await pilot.pause()
            cs = app.query_one(ContentSwitcher)
            assert cs.current == "screen-scanner"

    async def test_multiple_switches(self) -> None:
        """P → R → I → D без краша."""
        app = PentoolApp()
        app._skip_project_guard = True
        async with app.run_test(size=(120, 30)) as pilot:
            await pilot.pause()
            await pilot.press("P")
            await pilot.pause()
            await pilot.press("R")
            await pilot.pause()
            await pilot.press("I")
            await pilot.pause()
            await pilot.press("D")
            await pilot.pause()
            await pilot.pause()
            cs = app.query_one(ContentSwitcher)
            assert cs.current == "screen-decoder"

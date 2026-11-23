"""E2E: keyboard navigation between modules."""

from __future__ import annotations

import pytest
from pentool.tui.screens.scanner.screen import ScannerScreen  # noqa: F401
from textual.widgets import ContentSwitcher

from pentool.tui.app import PentoolApp


@pytest.mark.e2e
class TestNavigation:
    async def test_switch_to_repeater(self) -> None:
        """Key R → RepeaterScreen is active in ContentSwitcher."""
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
        """Key I → IntruderScreen is active in ContentSwitcher."""
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
        """Key D → DecoderScreen is active in ContentSwitcher."""
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
        """R → P → ProxyScreen is active in ContentSwitcher."""
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
        """Key S → ScannerScreen is active in ContentSwitcher.

        Scanner is gated by the `scanner_pro` feature: without a license `_switch_to`
        falls through to notify and stays on the previous screen. The test injects a
        valid license — otherwise it would verify the absence of a key in the CI
        environment instead of navigation.
        """
        from unittest.mock import patch

        from pentool.core.license import LicenseInfo

        pro = LicenseInfo(valid=True, plan="pro", features=["scanner_pro"])
        app = PentoolApp()
        app._skip_project_guard = True
        with patch("pentool.core.license.get_session_license", return_value=pro):
            async with app.run_test(size=(120, 30)) as pilot:
                await pilot.pause()
                await pilot.press("S")
                await pilot.pause()
                await pilot.pause()
                cs = app.query_one(ContentSwitcher)
                assert cs.current == "screen-scanner"

    async def test_switch_to_scanner_is_license_gated(self) -> None:
        """Without `scanner_pro` the S key does not switch screens, it only notifies."""
        from unittest.mock import patch

        from pentool.core.license import LicenseInfo

        free = LicenseInfo(valid=False)
        app = PentoolApp()
        app._skip_project_guard = True
        with patch("pentool.core.license.get_session_license", return_value=free):
            async with app.run_test(size=(120, 30)) as pilot:
                await pilot.pause()
                await pilot.press("S")
                await pilot.pause()
                await pilot.pause()
                cs = app.query_one(ContentSwitcher)
                assert cs.current != "screen-scanner", "unlicensed Scanner must not open"

    async def test_multiple_switches(self) -> None:
        """P → R → I → D without a crash."""
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

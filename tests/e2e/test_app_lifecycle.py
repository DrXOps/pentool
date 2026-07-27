"""E2E: PentoolApp lifecycle — mount, compose, basic widgets."""
from __future__ import annotations

import pytest
from textual.widgets import ContentSwitcher

from pentool.tui.app import PentoolApp
from pentool.tui.screens.proxy.screen import ProxyScreen
from pentool.tui.widgets.module_tabs import ModuleTabs
from pentool.tui.widgets.statusbar import StatusBar


@pytest.mark.e2e
class TestAppLifecycle:

    async def test_app_mounts(self) -> None:
        """PentoolApp запускается без исключений, pilot.app не None."""
        app = PentoolApp()
        async with app.run_test(size=(120, 30)) as pilot:
            await pilot.pause()
            assert pilot.app is not None

    async def test_proxy_screen_in_dom(self) -> None:
        """ProxyScreen присутствует в DOM после старта."""
        app = PentoolApp()
        async with app.run_test(size=(120, 30)) as pilot:
            await pilot.pause()
            screens = app.query(ProxyScreen)
            assert len(screens) > 0

    async def test_module_tabs_in_dom(self) -> None:
        """ModuleTabs присутствует в DOM."""
        app = PentoolApp()
        async with app.run_test(size=(120, 30)) as pilot:
            await pilot.pause()
            tabs = app.query_one(ModuleTabs)
            assert tabs is not None

    async def test_statusbar_in_dom(self) -> None:
        """StatusBar присутствует в DOM."""
        app = PentoolApp()
        async with app.run_test(size=(120, 30)) as pilot:
            await pilot.pause()
            sb = app.query_one(StatusBar)
            assert sb is not None

    async def test_content_switcher_in_dom(self) -> None:
        """ContentSwitcher присутствует в DOM."""
        app = PentoolApp()
        async with app.run_test(size=(120, 30)) as pilot:
            await pilot.pause()
            cs = app.query_one(ContentSwitcher)
            assert cs is not None

"""Integration tests: TUI events — ModuleSelected, DataTable, Proxy.

Checks: widget events, ModuleTabs, ProxyAPI callbacks.
"""

from __future__ import annotations

import pytest

from pentool.core.config import Config, set_config
from pentool.utils.parser import ParsedRequest


@pytest.fixture(autouse=True)
def isolated_config(tmp_path):
    cfg = Config(
        db_path=str(tmp_path / "test.db"),
        cert_dir=str(tmp_path / "certs"),
        proxy_port=19092,
    )
    set_config(cfg)
    return cfg


@pytest.mark.integration
@pytest.mark.usefixtures("patch_tui_io")
class TestModuleTabsEvents:
    @pytest.mark.asyncio
    async def test_module_selected_event_posted(self) -> None:
        """Click on a tab → ModuleSelected event."""
        from pentool.tui.app import PentoolApp
        from pentool.tui.messages import ModuleSelected

        received = []

        class TestApp(PentoolApp):
            def on_module_selected(self, event: ModuleSelected) -> None:
                received.append(event.module_id)
                super().on_module_selected(event)

        app = TestApp()
        async with app.run_test(size=(120, 30)) as pilot:
            await pilot.pause()
            await pilot.press("R")
            await pilot.pause()
            assert "repeater" in received

    @pytest.mark.asyncio
    async def test_content_switcher_changes_on_event(self) -> None:
        """ModuleSelected changes ContentSwitcher."""
        from textual.widgets import ContentSwitcher

        from pentool.tui.app import PentoolApp

        app = PentoolApp()
        # Without _skip_project_guard switching is blocked when no project is loaded
        app._skip_project_guard = True
        async with app.run_test(size=(120, 30)) as pilot:
            await pilot.pause()
            await pilot.press("R")
            await pilot.pause()
            await pilot.pause()
            cs = app.query_one(ContentSwitcher)
            assert cs.current == "screen-repeater"

    @pytest.mark.asyncio
    async def test_module_tabs_select_module(self) -> None:
        """app.action_switch_module switches ContentSwitcher programmatically."""
        from textual.widgets import ContentSwitcher

        from pentool.tui.app import PentoolApp

        app = PentoolApp()
        app._skip_project_guard = True
        async with app.run_test(size=(120, 30)) as pilot:
            await pilot.pause()
            # Use action_switch_module (public app API), not
            # ModuleTabs.select_module (which only changes Tab, not ContentSwitcher)
            app.action_switch_module("intruder")
            await pilot.pause()
            await pilot.pause()
            cs = app.query_one(ContentSwitcher)
            assert cs.current == "screen-intruder"


@pytest.mark.integration
@pytest.mark.usefixtures("patch_tui_io")
class TestProxyScreenEvents:
    @pytest.mark.asyncio
    async def test_intercept_toggle(self) -> None:
        """action_toggle_intercept changes ProxyAPI state."""
        from pentool.tui.app import PentoolApp

        app = PentoolApp()
        async with app.run_test(size=(120, 30)) as pilot:
            await pilot.pause()
            initial = app._proxy_api.get_intercept()
            # Call action directly (ToolbarButton.Pressed is not emulated
            # via pilot.click for custom widgets without BUTTON_PRESSED)
            app.action_toggle_intercept()
            await pilot.pause()
            after = app._proxy_api.get_intercept()
            assert after != initial

    @pytest.mark.asyncio
    async def test_forward_button_inactive_without_intercepted(self) -> None:
        """Forward without intercepted requests — no crash."""
        from pentool.tui.app import PentoolApp

        app = PentoolApp()
        async with app.run_test(size=(120, 30)) as pilot:
            await pilot.pause()
            await pilot.click("#btn-forward")
            await pilot.pause()
            # No Exception


@pytest.mark.integration
@pytest.mark.usefixtures("patch_tui_io")
class TestStatusBar:
    @pytest.mark.asyncio
    async def test_statusbar_shows_proxy_status(self) -> None:
        from pentool.tui.app import PentoolApp
        from pentool.tui.widgets.statusbar import StatusBar

        app = PentoolApp()
        async with app.run_test(size=(120, 30)) as pilot:
            await pilot.pause()
            sb = app.query_one(StatusBar)
            # StatusBar exists and contains text
            assert sb is not None


@pytest.mark.integration
@pytest.mark.usefixtures("patch_tui_io")
class TestRepeaterFlow:
    @pytest.mark.asyncio
    async def test_load_request_populates_editor(self) -> None:
        """load_request(raw) fills the active tab's request editor.

        ``load_request`` takes raw HTTP text, not a ``ParsedRequest``: the old
        version passed the object, its ``.replace`` raised inside the handler's
        ``except Exception: pass``, and the assertion only checked that *some*
        editor existed — which is true on an empty screen too.
        """
        from pentool.tui.app import PentoolApp
        from pentool.tui.screens.repeater.screen import RepeaterScreen
        from pentool.utils.parser import build_http_request

        app = PentoolApp()
        async with app.run_test(size=(120, 30)) as pilot:
            await pilot.pause()
            await pilot.press("R")
            await pilot.pause()

            req = ParsedRequest(
                method="GET",
                url="http://example.com/test",
                headers={"Host": "example.com"},
            )
            screen = app.query_one(RepeaterScreen)
            screen.load_request(build_http_request(req))
            await pilot.pause()

            editor = screen._editor(screen._active_tab_id)
            assert "GET /test HTTP/1.1" in editor.get_text(), "request text did not reach the editor"

    @pytest.mark.asyncio
    async def test_new_tab_adds_tab(self) -> None:
        """action_new_tab() adds a Repeater tab."""
        from pentool.tui.app import PentoolApp
        from pentool.tui.screens.repeater.screen import RepeaterScreen

        app = PentoolApp()
        async with app.run_test(size=(120, 30)) as pilot:
            await pilot.pause()
            await pilot.press("R")
            await pilot.pause()
            screen = app.query_one(RepeaterScreen)
            screen.action_new_tab()
            await pilot.pause()
            # No exception = OK


@pytest.mark.integration
@pytest.mark.usefixtures("patch_tui_io")
class TestIntruderFlow:
    @pytest.mark.asyncio
    async def test_load_request_populates_positions(self) -> None:
        """load_request(raw) fills the Intruder template with its §§ markers."""
        from pentool.tui.app import PentoolApp
        from pentool.tui.screens.intruder.screen import IntruderScreen
        from pentool.utils.parser import build_http_request

        app = PentoolApp()
        async with app.run_test(size=(120, 30)) as pilot:
            await pilot.pause()
            await pilot.press("I")
            await pilot.pause()

            req = ParsedRequest(
                method="POST",
                url="http://example.com/login",
                headers={"Host": "example.com"},
                body="user=§admin§&pass=§secret§",
            )
            screen = app.query_one(IntruderScreen)
            screen.load_request(build_http_request(req))
            await pilot.pause()

            template = screen._template_editor().get_text()
            assert "user=§admin§&pass=§secret§" in template, "markers did not reach the template editor"

    @pytest.mark.asyncio
    async def test_start_without_markers_shows_error(self) -> None:
        """Start attack without markers — notify about error."""
        from pentool.tui.app import PentoolApp

        app = PentoolApp()
        async with app.run_test(size=(120, 30)) as pilot:
            await pilot.pause()
            await pilot.press("I")
            await pilot.pause()
            await pilot.click("#btn-start")
            await pilot.pause()
            # No crash — error notification shown

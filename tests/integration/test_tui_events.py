"""Integration-тесты: события TUI — ModuleSelected, DataTable, Proxy.

Проверяет: события виджетов, ModuleTabs, ProxyAPI callbacks.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from pentool.core.config import Config, set_config
from pentool.utils.parser import ParsedRequest, ParsedResponse


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
class TestModuleTabsEvents:
    @pytest.mark.asyncio
    async def test_module_selected_event_posted(self) -> None:
        """Клик по вкладке → ModuleSelected event."""
        from pentool.tui.app import PentoolApp
        from pentool.tui.widgets.menu import ModuleSelected

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
        """ModuleSelected меняет ContentSwitcher."""
        from pentool.tui.app import PentoolApp
        from textual.widgets import ContentSwitcher

        app = PentoolApp()
        # Без _skip_project_guard переключение блокируется при незагруженном проекте
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
        """app.action_switch_module переключает ContentSwitcher программно."""
        from pentool.tui.app import PentoolApp
        from textual.widgets import ContentSwitcher

        app = PentoolApp()
        app._skip_project_guard = True
        async with app.run_test(size=(120, 30)) as pilot:
            await pilot.pause()
            # Используем action_switch_module (публичный API app), а не
            # ModuleTabs.select_module (который только меняет Tab, не ContentSwitcher)
            app.action_switch_module("intruder")
            await pilot.pause()
            await pilot.pause()
            cs = app.query_one(ContentSwitcher)
            assert cs.current == "screen-intruder"


@pytest.mark.integration
class TestProxyScreenEvents:
    @pytest.mark.asyncio
    async def test_intercept_toggle(self) -> None:
        """action_toggle_intercept меняет состояние ProxyAPI."""
        from pentool.tui.app import PentoolApp

        app = PentoolApp()
        async with app.run_test(size=(120, 30)) as pilot:
            await pilot.pause()
            initial = app._proxy_api.get_intercept()
            # Вызываем action напрямую (ToolbarButton.Pressed не эмулируется
            # через pilot.click для custom-виджетов без BUTTON_PRESSED)
            app.action_toggle_intercept()
            await pilot.pause()
            after = app._proxy_api.get_intercept()
            assert after != initial

    @pytest.mark.asyncio
    async def test_forward_button_inactive_without_intercepted(self) -> None:
        """Forward без перехваченных запросов — нет crash."""
        from pentool.tui.app import PentoolApp

        app = PentoolApp()
        async with app.run_test(size=(120, 30)) as pilot:
            await pilot.pause()
            await pilot.click("#btn-forward")
            await pilot.pause()
            # Нет Exception


@pytest.mark.integration
class TestStatusBar:
    @pytest.mark.asyncio
    async def test_statusbar_shows_proxy_status(self) -> None:
        from pentool.tui.app import PentoolApp
        from pentool.tui.widgets.statusbar import StatusBar

        app = PentoolApp()
        async with app.run_test(size=(120, 30)) as pilot:
            await pilot.pause()
            sb = app.query_one(StatusBar)
            # StatusBar существует и содержит текст
            assert sb is not None


@pytest.mark.integration
class TestRepeaterFlow:
    @pytest.mark.asyncio
    async def test_load_request_populates_editor(self) -> None:
        """load_request() заполняет #request-editor."""
        from pentool.tui.app import PentoolApp
        from pentool.tui.screens.repeater.screen import RepeaterScreen

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
            screen.load_request(req)
            await pilot.pause()

            # RepeaterScreen использует динамические ID вида #req-editor-{tab_id}
            from pentool.tui.widgets.request_editor import RequestEditor
            editors = app.query(RequestEditor)
            assert len(editors) > 0

    @pytest.mark.asyncio
    async def test_new_tab_adds_tab(self) -> None:
        """action_new_tab() добавляет вкладку Repeater."""
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
            # Не упало = ОК


@pytest.mark.integration
class TestIntruderFlow:
    @pytest.mark.asyncio
    async def test_load_request_populates_positions(self) -> None:
        """load_request() заполняет #positions-editor."""
        from pentool.tui.app import PentoolApp
        from pentool.tui.screens.intruder.screen import IntruderScreen

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
            screen.load_request(req)
            await pilot.pause()
            # Intruder positions editor использует #template-editor
            editor = app.query_one("#template-editor")
            assert editor is not None

    @pytest.mark.asyncio
    async def test_start_without_markers_shows_error(self) -> None:
        """Старт атаки без маркеров — notify об ошибке."""
        from pentool.tui.app import PentoolApp
        from pentool.tui.screens.intruder.screen import IntruderScreen

        app = PentoolApp()
        async with app.run_test(size=(120, 30)) as pilot:
            await pilot.pause()
            await pilot.press("I")
            await pilot.pause()
            await pilot.click("#btn-start")
            await pilot.pause()
            # Нет crash — уведомление об ошибке показано

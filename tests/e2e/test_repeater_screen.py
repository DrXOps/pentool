"""E2E: RepeaterScreen — load request, new tab."""
from __future__ import annotations

import pytest

from pentool.tui.app import PentoolApp
from pentool.tui.screens.repeater.screen import RepeaterScreen
from pentool.tui.widgets.request_editor import RequestEditor
from pentool.utils.parser import ParsedRequest


@pytest.mark.e2e
class TestRepeaterScreen:

    async def test_send_button_present(self) -> None:
        """После press R → #btn-send присутствует в DOM."""
        app = PentoolApp()
        app._skip_project_guard = True
        async with app.run_test(size=(120, 30)) as pilot:
            await pilot.pause()
            await pilot.press("R")
            await pilot.pause()
            btn = app.query("#btn-send")
            assert len(btn) > 0

    async def test_request_editor_present(self) -> None:
        """RequestEditor присутствует в DOM после перехода на Repeater."""
        app = PentoolApp()
        app._skip_project_guard = True
        async with app.run_test(size=(120, 30)) as pilot:
            await pilot.pause()
            await pilot.press("R")
            await pilot.pause()
            await pilot.pause()
            editors = app.query(RequestEditor)
            assert len(editors) > 0

    async def test_load_request(self) -> None:
        """load_request(ParsedRequest(...)) — RequestEditor существует."""
        app = PentoolApp()
        app._skip_project_guard = True
        async with app.run_test(size=(120, 30)) as pilot:
            await pilot.pause()
            await pilot.press("R")
            await pilot.pause()
            await pilot.pause()

            req = ParsedRequest(
                method="GET",
                url="http://example.com/",
                headers={"Host": "example.com"},
            )
            screen = app.query_one(RepeaterScreen)
            screen.load_request(req)
            await pilot.pause()

            editors = app.query(RequestEditor)
            assert len(editors) > 0

    async def test_new_tab_action(self) -> None:
        """screen.action_new_tab() не крашит."""
        app = PentoolApp()
        app._skip_project_guard = True
        async with app.run_test(size=(120, 30)) as pilot:
            await pilot.pause()
            await pilot.press("R")
            await pilot.pause()
            screen = app.query_one(RepeaterScreen)
            screen.action_new_tab()
            await pilot.pause()
            # Нет исключения — тест пройден

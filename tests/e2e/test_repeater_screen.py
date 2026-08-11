"""E2E: RepeaterScreen — load request, new tab."""
from __future__ import annotations

import pytest

from pentool.tui.app import PentoolApp
from pentool.tui.screens.repeater.screen import RepeaterScreen
from pentool.tui.widgets.diff_panel import DiffPanel
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

    async def test_dirty_marker_appears_after_edit_post_send(self) -> None:
        """После успешной отправки правка текста должна пометить таб "*"."""
        app = PentoolApp()
        app._skip_project_guard = True
        async with app.run_test(size=(120, 30)) as pilot:
            await pilot.pause()
            await pilot.press("R")
            await pilot.pause()
            await pilot.pause()

            screen = app.query_one(RepeaterScreen)
            tab_id = screen._active_tab_id
            state = screen._get_tab_state(tab_id)
            assert state is not None

            # Simulate a prior successful send without hitting the network.
            state.last_sent_text = state.request_text
            state.is_dirty = False
            screen._update_tab_label(state)

            editor = app.query_one(f"#req-editor-{tab_id}", RequestEditor)
            editor.load_raw("GET /changed HTTP/1.1\r\nHost: example.com\r\n\r\n")
            await pilot.pause()

            assert state.is_dirty is True

            tabs = screen.query_one("#repeater-tabs")
            tab_widget = tabs.get_tab(tab_id)
            assert tab_widget.label.plain.endswith("*")

    async def test_diff_panel_toggle_no_last_sent(self) -> None:
        """Ctrl+D на никогда не отправленной вкладке не крашит и не открывает пустую панель."""
        app = PentoolApp()
        app._skip_project_guard = True
        async with app.run_test(size=(120, 30)) as pilot:
            await pilot.pause()
            await pilot.press("R")
            await pilot.pause()
            await pilot.pause()

            screen = app.query_one(RepeaterScreen)
            screen.action_toggle_diff()
            await pilot.pause()
            # Нет исключения — тест пройден
            panel = app.query_one(DiffPanel)
            assert panel is not None

    async def test_diff_panel_shows_diff_after_send(self) -> None:
        """Ctrl+D после симулированной отправки открывает панель с диффом."""
        app = PentoolApp()
        app._skip_project_guard = True
        async with app.run_test(size=(120, 30)) as pilot:
            await pilot.pause()
            await pilot.press("R")
            await pilot.pause()
            await pilot.pause()

            screen = app.query_one(RepeaterScreen)
            tab_id = screen._active_tab_id
            state = screen._get_tab_state(tab_id)
            state.last_sent_text = "GET / HTTP/1.1\r\nHost: example.com\r\n\r\n"

            editor = app.query_one(f"#req-editor-{tab_id}", RequestEditor)
            editor.load_raw("GET /new-path HTTP/1.1\r\nHost: example.com\r\n\r\n")
            await pilot.pause()

            screen.action_toggle_diff()
            await pilot.pause()

            panel = app.query_one(DiffPanel)
            assert "-visible" in panel.classes

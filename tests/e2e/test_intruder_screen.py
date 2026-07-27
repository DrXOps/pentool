"""E2E: IntruderScreen — load request, widgets."""
from __future__ import annotations

import pytest

from pentool.tui.app import PentoolApp
from pentool.tui.screens.intruder.screen import IntruderScreen
from pentool.utils.parser import ParsedRequest


@pytest.mark.e2e
class TestIntruderScreen:

    async def test_intruder_mounts(self) -> None:
        """press I → IntruderScreen присутствует в DOM."""
        app = PentoolApp()
        app._skip_project_guard = True
        async with app.run_test(size=(120, 30)) as pilot:
            await pilot.pause()
            await pilot.press("I")
            await pilot.pause()
            await pilot.pause()
            screens = app.query(IntruderScreen)
            assert len(screens) > 0

    async def test_start_button_present(self) -> None:
        """#btn-start присутствует в IntruderScreen."""
        app = PentoolApp()
        app._skip_project_guard = True
        async with app.run_test(size=(120, 30)) as pilot:
            await pilot.pause()
            await pilot.press("I")
            await pilot.pause()
            await pilot.pause()
            btn = app.query("#btn-start")
            assert len(btn) > 0

    async def test_template_editor_present(self) -> None:
        """#template-editor присутствует в IntruderScreen."""
        app = PentoolApp()
        app._skip_project_guard = True
        async with app.run_test(size=(120, 30)) as pilot:
            await pilot.pause()
            await pilot.press("I")
            await pilot.pause()
            await pilot.pause()
            editor = app.query("#template-editor")
            assert len(editor) > 0

    async def test_load_request(self) -> None:
        """screen.load_request(req) не крашит."""
        app = PentoolApp()
        app._skip_project_guard = True
        async with app.run_test(size=(120, 30)) as pilot:
            await pilot.pause()
            await pilot.press("I")
            await pilot.pause()
            await pilot.pause()

            req = ParsedRequest(
                method="POST",
                url="http://example.com/login",
                headers={"Host": "example.com"},
                body="user=admin&pass=secret",
            )
            screen = app.query_one(IntruderScreen)
            screen.load_request(req)
            await pilot.pause()
            # Нет исключения — тест пройден

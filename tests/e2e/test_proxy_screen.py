"""E2E: ProxyScreen widgets and basic interactions."""
from __future__ import annotations

import pytest

from pentool.tui.app import PentoolApp


@pytest.mark.e2e
class TestProxyScreen:

    async def test_intercept_button_present(self) -> None:
        """#btn-intercept присутствует в DOM."""
        app = PentoolApp()
        async with app.run_test(size=(120, 30)) as pilot:
            await pilot.pause()
            btn = app.query("#btn-intercept")
            assert len(btn) > 0

    async def test_forward_button_present(self) -> None:
        """#btn-forward присутствует в DOM."""
        app = PentoolApp()
        async with app.run_test(size=(120, 30)) as pilot:
            await pilot.pause()
            btn = app.query("#btn-forward")
            assert len(btn) > 0

    async def test_request_list_present(self) -> None:
        """#request-list присутствует в DOM."""
        app = PentoolApp()
        async with app.run_test(size=(120, 30)) as pilot:
            await pilot.pause()
            table = app.query("#request-list")
            assert len(table) > 0

    async def test_toggle_intercept_changes_state(self) -> None:
        """action_toggle_intercept() меняет состояние intercept."""
        app = PentoolApp()
        async with app.run_test(size=(120, 30)) as pilot:
            await pilot.pause()
            initial = app._proxy_api.get_intercept()
            app.action_toggle_intercept()
            await pilot.pause()
            assert app._proxy_api.get_intercept() != initial

    async def test_forward_no_crash(self) -> None:
        """Нажатие #btn-forward без перехваченного запроса — не крашит."""
        app = PentoolApp()
        async with app.run_test(size=(120, 30)) as pilot:
            await pilot.pause()
            await pilot.click("#btn-forward")
            await pilot.pause()
            # Нет исключения — тест пройден

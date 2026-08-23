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

    async def test_enforce_scope_button_label_matches_state_after_first_click(self) -> None:
        """Regression: '☐/☑ Skip out-of-scope' button label must reflect the
        NEW state right after the first click — not lag one click behind.

        Before the fix, action_toggle_enforce_scope() called
        proxy.set_enforce_scope(enabled) (which defers the actual attribute
        write via call_soon_threadsafe onto the proxy's own event loop when
        it's running) and then immediately re-read proxy.enforce_scope in
        _sync_enforce_scope_button() — seeing the OLD value. So clicking
        once turned the filter on for real but showed unchecked (☐); a
        second click then showed the FIRST click's real state while
        toggling the flag again — an off-by-one-click lag between the
        button's checkbox and the actual enforce_scope flag.
        """
        from pentool.tui.screens.proxy.screen import ProxyScreen
        from pentool.tui.widgets.toolbar_button import ToolbarButton

        app = PentoolApp()
        async with app.run_test(size=(120, 30)) as pilot:
            await pilot.pause()
            screen = app.query_one(ProxyScreen)
            proxy = screen._get_proxy()
            btn = screen.query_one("#btn-enforce-scope", ToolbarButton)

            assert proxy.enforce_scope is False
            assert btn.label == "☐ Skip out-of-scope"

            screen.action_toggle_enforce_scope()
            await pilot.pause()

            # The real flag and the button label must agree immediately —
            # both reflect "ON" right after the first click.
            assert proxy.enforce_scope is True
            assert btn.label == "☑ Skip out-of-scope"

            screen.action_toggle_enforce_scope()
            await pilot.pause()

            assert proxy.enforce_scope is False
            assert btn.label == "☐ Skip out-of-scope"


    async def test_selection_race_ignores_stale_slow_load(self) -> None:
        """Regression: clicking A then quickly B must NOT paint A's details
        when A's async load finishes last (slow disk / weak hardware).

        Before the fix _load_row_details had no gate, so a slow
        get_full_entry(A) that returned after the user had moved to B would
        draw A over the B the user actually selected. The gate drops any
        load whose id no longer matches the current selection.
        """
        import asyncio

        from unittest.mock import AsyncMock

        from pentool.tui.screens.proxy.screen import ProxyScreen

        app = PentoolApp()
        async with app.run_test(size=(120, 30)) as pilot:
            await pilot.pause()
            screen = app.query_one(ProxyScreen)

            # Seed the display cache so _select_row has rows to pick from.
            screen._rows_cache = [{"id": 1, "host": "a"}, {"id": 2, "host": "b"}]

            # get_full_entry: id=1 is SLOW, id=2 returns immediately.
            async def fake_get_full_entry(row_id: int) -> dict | None:
                if row_id == 1:
                    await asyncio.sleep(0.2)  # slow disk
                return {"id": row_id, "method": "GET", "url": f"http://x/{row_id}"}

            screen._proxy_service.get_full_entry = AsyncMock(side_effect=fake_get_full_entry)
            screen._proxy_service.is_storage_ready = lambda: True

            # Spy on the paint so we can assert which entry was actually drawn.
            painted: list[int] = []
            real_paint = screen._load_entry_details

            def spy_paint(entry: dict) -> None:
                painted.append(entry.get("id"))
                real_paint(entry)

            screen._load_entry_details = spy_paint

            # Click A, then immediately click B.
            screen._select_row(0)  # id=1 (slow)
            screen._select_row(1)  # id=2 (fast)
            for _ in range(30):
                await pilot.pause()
                if painted:
                    break

            assert screen._selected_req_id == 2
            # Only B may have been painted; the stale A must have been dropped.
            assert painted == [2], f"stale row A leaked into details: {painted}"

"""E2E: ProxyScreen widgets and basic interactions."""

from __future__ import annotations

import pytest

from pentool.tui.app import PentoolApp


async def _open_proxy(pilot) -> None:
    """Switch to the Proxy module (lazy screens: it is mounted on demand)."""
    # The project guard blocks module switches while no project is open; the
    # tests below exercise widgets, not the guard.
    pilot.app._skip_project_guard = True
    pilot.app._switch_to("proxy")
    for _ in range(8):
        await pilot.pause()


@pytest.mark.e2e
class TestProxyScreen:
    async def test_intercept_button_present(self) -> None:
        """The intercept toggle is in the module header (row 2, state zone)."""
        app = PentoolApp()
        async with app.run_test(size=(120, 30)) as pilot:
            await pilot.pause()
            await _open_proxy(pilot)
            buttons = [btn for btn in app.query("#hdr-state-1, #hdr-state-2") if btn.data_action == "intercept"]
            assert buttons, "intercept toggle missing from the header state zone"

    async def test_forward_button_present(self) -> None:
        """Forward lives in the header actions (Intercept sub-tab)."""
        app = PentoolApp()
        async with app.run_test(size=(120, 30)) as pilot:
            await pilot.pause()
            await _open_proxy(pilot)
            app.query_one("#proxy-subtabs").active = "tab-intercept"
            await pilot.pause()
            await pilot.pause()
            buttons = [btn for btn in app.query(".hdr-act") if btn.data_action == "forward"]
            assert buttons, "Forward missing from the header actions"

    async def test_request_list_present(self) -> None:
        """#request-list exists once the module is mounted (lazy screens)."""
        app = PentoolApp()
        async with app.run_test(size=(120, 30)) as pilot:
            await pilot.pause()
            await _open_proxy(pilot)
            table = app.query("#request-list")
            assert len(table) > 0

    async def test_toggle_intercept_changes_state(self) -> None:
        """action_toggle_intercept() меняет состояние intercept."""
        app = PentoolApp()
        async with app.run_test(size=(120, 30)) as pilot:
            await pilot.pause()
            await _open_proxy(pilot)
            initial = app._proxy_api.get_intercept()
            app.action_toggle_intercept()
            await pilot.pause()
            assert app._proxy_api.get_intercept() != initial

    async def test_forward_no_crash(self) -> None:
        """Pressing Forward with nothing intercepted must not crash."""
        app = PentoolApp()
        async with app.run_test(size=(120, 30)) as pilot:
            await pilot.pause()
            await _open_proxy(pilot)
            app.query_one("#proxy-subtabs").active = "tab-intercept"
            await pilot.pause()
            await pilot.pause()
            app._dispatch_header_action("forward")
            await pilot.pause()

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

        app = PentoolApp()
        async with app.run_test(size=(120, 30)) as pilot:
            await pilot.pause()
            await _open_proxy(pilot)
            screen = app.query_one(ProxyScreen)
            proxy = screen._get_proxy()

            def skip_label() -> str:
                spec = screen.header_spec()
                return next(item.label for item in spec.more if item.action == "skip")

            assert proxy.enforce_scope is False
            assert skip_label() == "☐ Skip out-of-scope: OFF"

            screen.action_toggle_enforce_scope()
            await pilot.pause()

            # The real flag and the header label must agree immediately.
            assert proxy.enforce_scope is True
            assert skip_label() == "☑ Skip out-of-scope: ON"

            screen.action_toggle_enforce_scope()
            await pilot.pause()

            assert proxy.enforce_scope is False
            assert skip_label() == "☐ Skip out-of-scope: OFF"

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
            await _open_proxy(pilot)
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

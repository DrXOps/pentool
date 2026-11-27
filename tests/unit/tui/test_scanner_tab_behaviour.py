"""Characterization test for Scanner's tabs — the safety net for step 11 (Scanner).

Scanner keeps the last hand-written tab bookkeeping: a list, an active id and a counter
inside the screen. These tests record today's behaviour in user terms *before* that moves
into `TabRegistry`, and they must stay green without edits.

Scanner is PRO: without the `scanner_pro` feature the `S` key only shows a notification, so
the tests inject a license — the same way `tests/e2e/test_navigation.py` does. The machine's
project is kept out of the picture (`app.db_path = ""`): otherwise the number and targets of
the restored tabs would depend on what the developer scanned before.
"""

from __future__ import annotations

import pytest
from pentool.tui.screens.scanner.screen import ScannerScreen
from textual.widgets import Input, TabbedContent

from pentool.core.license import LicenseInfo
from pentool.tui.app import PentoolApp

PRO = LicenseInfo(valid=True, plan="pro", features=["scanner_pro"])


@pytest.fixture(autouse=True)
def _pro_license(monkeypatch):
    """Scanner is gated by `scanner_pro`; without it pressing S stays on the previous screen."""
    import pentool.core.license

    monkeypatch.setattr(pentool.core.license, "get_session_license", lambda: PRO)


@pytest.fixture(autouse=True)
def _no_project(monkeypatch):
    """No restored tabs: the tab count and targets must not depend on the machine's DB."""
    monkeypatch.setattr(PentoolApp, "db_path", property(lambda _self: ""))


async def _wait(predicate, pilot, frames: int = 120) -> None:
    """Wait for a concrete state, not for "a couple of pulses" (the CI flakiness rule)."""
    for _ in range(frames):
        if predicate():
            return
        await pilot.pause()
    raise AssertionError("состояние не наступило за 120 кадров")


def _pane_ids(screen: ScannerScreen) -> list[str]:
    return [pane.id for pane in screen.query("#scanner-tabs TabPane") if pane.id is not None]


async def _open_scanner(pilot) -> ScannerScreen:
    await pilot.pause()
    pilot.app.action_switch_module("scanner")
    screen: ScannerScreen | None = None
    for _ in range(120):
        await pilot.pause()
        screen = pilot.app.module_screen("scanner")
        if screen is not None and screen._active_tab_id is not None:
            return screen
    raise AssertionError("экран Scanner не смонтировался с активной вкладкой")


@pytest.mark.asyncio
async def test_opening_scanner_gives_one_active_tab() -> None:
    """The screen opens with exactly one tab, and the strip lives in `#scanner-tabs`."""
    app = PentoolApp()
    app._skip_project_guard = True
    async with app.run_test(size=(160, 45)) as pilot:
        screen = await _open_scanner(pilot)

        assert screen.query("#scanner-tabs"), "лента вкладок Scanner не найдена"
        assert [t.tab_id for t in screen._tabs] == [screen._active_tab_id]
        assert len(_pane_ids(screen)) == 1, "на экране должна быть ровно одна вкладка"
        active = screen._active_tab
        assert active is not None and active.rows == []


@pytest.mark.asyncio
async def test_new_tab_is_added_and_becomes_active() -> None:
    """`action_new_tab()` adds a tab, makes it active, and gives it its own empty state."""
    app = PentoolApp()
    app._skip_project_guard = True
    async with app.run_test(size=(160, 45)) as pilot:
        screen = await _open_scanner(pilot)
        first = screen._active_tab_id
        panes_before = len(_pane_ids(screen))

        screen.action_new_tab()
        await _wait(lambda: len(_pane_ids(screen)) == panes_before + 1, pilot)
        await _wait(lambda: screen._active_tab_id != first, pilot)

        assert len(screen._tabs) == panes_before + 1
        assert all(tab.tab_id in _pane_ids(screen) for tab in screen._tabs)
        active = screen._active_tab
        first_state = next(tab for tab in screen._tabs if tab.tab_id == first)
        assert active is not None and active is not first_state, (
            "новая вкладка делит состояние со старой — данные скана перепутаются"
        )


@pytest.mark.asyncio
async def test_closing_the_active_tab_leaves_its_neighbour_active() -> None:
    """Closing a middle tab leaves the *next* tab active; closing the last — the previous.

    The neighbour rule is Textual's, not the screen's: `action_close_tab` assigns the tab on
    the left, but `remove_pane()` finishes a frame later and activates the next tab, and the
    screen follows the widget's `TabActivated`. The net effect a user sees (and what this
    test pins) is "next, else previous" — the same rule `Tabs` applies.
    """
    app = PentoolApp()
    app._skip_project_guard = True
    async with app.run_test(size=(160, 48)) as pilot:
        screen = await _open_scanner(pilot)
        screen.action_new_tab()
        await _wait(lambda: len(_pane_ids(screen)) == 2, pilot)
        screen.action_new_tab()
        await _wait(lambda: len(_pane_ids(screen)) == 3, pilot)

        second_id = screen._tabs[1].tab_id
        third_id = screen._tabs[2].tab_id
        tabs = screen.query_one("#scanner-tabs", TabbedContent)
        tabs.active = second_id
        await _wait(lambda: screen._active_tab_id == second_id, pilot)

        screen.action_close_tab()
        await _wait(lambda: len(_pane_ids(screen)) == 2, pilot)
        await _wait(lambda: screen._active_tab_id != second_id, pilot)

        assert second_id not in [tab.tab_id for tab in screen._tabs], "состояние закрытой вкладки осталось"
        assert second_id not in _pane_ids(screen), "панель закрытой вкладки осталась на экране"
        assert screen._active_tab_id == third_id, (
            "после закрытия активной вкладки Textual активирует следующую — экран должен следовать за ней"
        )

        # Closing the last tab has no "next", so the previous one becomes active.
        tabs.active = third_id
        await _wait(lambda: screen._active_tab_id == third_id, pilot)
        screen.action_close_tab()
        await _wait(lambda: len(_pane_ids(screen)) == 1, pilot)

        assert [tab.tab_id for tab in screen._tabs] == [screen._tabs[0].tab_id]
        assert screen._active_tab_id == screen._tabs[0].tab_id, (
            "последняя закрытая вкладка не отдала активность соседней"
        )


@pytest.mark.asyncio
async def test_submitting_a_new_name_renames_the_tab() -> None:
    """Double-click rename writes the state and the tab label."""
    app = PentoolApp()
    app._skip_project_guard = True
    async with app.run_test(size=(160, 45)) as pilot:
        screen = await _open_scanner(pilot)
        tab_id = screen._active_tab_id
        assert tab_id is not None

        screen._start_rename(tab_id)
        await _wait(lambda: bool(screen.query("#scan-rename-input")), pilot)
        field = screen.query_one("#scan-rename-input", Input)
        field.value = "Renamed scan"
        field.post_message(Input.Submitted(field, "Renamed scan"))

        await _wait(lambda: screen._rename_state(tab_id).name == "Renamed scan", pilot)

        tabs = screen.query_one("#scanner-tabs", TabbedContent)
        assert tabs.get_tab(tab_id).label == "Renamed scan"

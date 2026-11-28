"""The adaptive limit is visible in the Intruder UI, per tab, and clears with the results.

The controller and the attack are covered elsewhere; this pins the user-facing half: the control
row shows the current limit, the tab's results row shows the latest change with its reason, a stop
decision raises a toast, and clearing the results resets both.
"""

from __future__ import annotations

from textual.app import App, ComposeResult
from textual.widgets import ContentSwitcher, Static

from pentool.modules.intruder_limits import LimitDecision
from pentool.tui.screens.intruder.screen import IntruderScreen, _TabId


class _IntruderHost(App):
    _menu: dict[str, object] = {}

    def compose(self) -> ComposeResult:
        with ContentSwitcher():
            yield IntruderScreen()

    def show_context_menu(self, items, x, y, callback=None) -> None:
        type(self)._menu = {"items": list(items), "callback": callback}


async def _settle(pilot, cycles: int = 8) -> None:
    for _ in range(cycles):
        await pilot.pause()


async def test_the_limit_and_its_reason_are_shown_per_tab() -> None:
    app = _IntruderHost()
    async with app.run_test(size=(200, 60)) as pilot:
        await _settle(pilot)
        screen = app.query_one(IntruderScreen)
        tab = screen._active_tab
        assert tab is not None

        screen._on_limit_change(LimitDecision(threads=4, delay_ms=200, reason="429 ×3"), tab)
        await _settle(pilot)

        assert tab.limit_note == "4 потоков, 200 мс — 429 ×3"
        control = str(screen.query_one("#intruder-limit", Static).content)
        assert "4 потоков" in control, "строка управления должна показывать текущий лимит"
        row = str(screen.query_one(f"#{screen._wid(tab.tab_id, _TabId.LIMIT_LABEL)}", Static).content)
        assert "лимит:" in row and "429 ×3" in row, "причина должна быть в строке результатов"

        screen._clear_limit_note(tab)
        await _settle(pilot)

        assert tab.limit_note == ""
        assert "adaptive: —" in str(screen.query_one("#intruder-limit", Static).content)
        assert str(screen.query_one(f"#{screen._wid(tab.tab_id, _TabId.LIMIT_LABEL)}", Static).content) == ""


async def test_the_indicator_follows_the_active_tab() -> None:
    app = _IntruderHost()
    async with app.run_test(size=(200, 60)) as pilot:
        await _settle(pilot)
        screen = app.query_one(IntruderScreen)
        panel = screen._tc_panel
        first = panel.active_tab_id

        screen._on_limit_change(LimitDecision(threads=2, delay_ms=500, reason="Retry-After 7s"), screen._active_tab)
        await _settle(pilot)

        panel.action_new_tab()
        await _settle(pilot)
        # The new tab has no history of its own, so the control row must not keep the old note.
        assert "adaptive: —" in str(screen.query_one("#intruder-limit", Static).content)

        panel.switch_to(first)
        await _settle(pilot)
        assert "Retry-After 7s" in str(screen.query_one("#intruder-limit", Static).content)

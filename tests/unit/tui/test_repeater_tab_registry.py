"""Repeater's tabs are owned by one registry (step 11).

The characterization files (`test_repeater_tab_behaviour`,
`test_repeater_tab_state_survives`) pin how the tab strip behaves. This file pins
what the migration changed: the screen keeps no tab list and no active id of its
own — both come from `TabRegistry`, while the widget is still a plain
`TabbedContent`. That is what makes the next step (swapping the widget) a change
of one layer instead of two copies of the same bookkeeping.
"""

from __future__ import annotations

import pytest
from textual.widgets import TabPane

from pentool.tui.app import PentoolApp
from pentool.tui.screens.repeater.screen import RepeaterScreen
from pentool.tui.widgets.tab_registry import TabRegistry


@pytest.fixture(autouse=True)
def _no_project_history(monkeypatch):
    """The machine's project must not decide how many tabs the screen starts with."""
    monkeypatch.setattr(RepeaterScreen, "_get_db_path", lambda _self: "")


async def _wait(predicate, pilot, frames: int = 100) -> None:
    """Wait for a concrete state, not for "a couple of pulses" (the CI flakiness rule)."""
    for _ in range(frames):
        if predicate():
            return
        await pilot.pause()
    raise AssertionError("состояние не наступило за 100 кадров")


def _pane_ids(screen: RepeaterScreen) -> list[str]:
    return [pane.id for pane in screen._tabs_w.query(TabPane) if pane.id is not None]


async def _open_repeater(pilot) -> RepeaterScreen:
    await pilot.pause()
    await pilot.press("R")
    screen = pilot.app.query_one(RepeaterScreen)
    await _wait(lambda: len(screen._tab_registry) > 0 and screen._active_tab_id is not None, pilot)
    return screen


@pytest.mark.asyncio
async def test_the_screen_keeps_no_tab_list_of_its_own() -> None:
    app = PentoolApp()
    app._skip_project_guard = True
    async with app.run_test(size=(140, 40)) as pilot:
        screen = await _open_repeater(pilot)

        assert isinstance(screen._tab_registry, TabRegistry)
        assert "_tabs" not in screen.__dict__, (
            "у экрана снова свой список вкладок — два источника правды, расхождение будет молчаливым"
        )
        assert "_active_tab_id" not in screen.__dict__, "у экрана снова своя активная вкладка"
        assert screen._tabs == screen._tab_registry.states
        assert screen._active_tab_id == screen._tab_registry.active_id


@pytest.mark.asyncio
async def test_a_new_tab_is_registered_and_shown_in_the_same_order() -> None:
    app = PentoolApp()
    app._skip_project_guard = True
    async with app.run_test(size=(140, 40)) as pilot:
        screen = await _open_repeater(pilot)
        first = screen._active_tab_id
        panes_before = len(_pane_ids(screen))

        screen.action_new_tab()
        await _wait(lambda: len(_pane_ids(screen)) == panes_before + 1, pilot)
        await _wait(lambda: screen._active_tab_id != first, pilot)

        assert screen._tab_registry.ids == _pane_ids(screen), "реестр и лента разошлись по порядку"
        active = screen._active_tab_id
        assert active is not None
        assert screen._get_tab_state(active) is screen._tab_registry.active, (
            "активная вкладка экрана и активная вкладка реестра — разные объекты"
        )


@pytest.mark.asyncio
async def test_closing_a_tab_forgets_it_in_the_registry() -> None:
    app = PentoolApp()
    app._skip_project_guard = True
    async with app.run_test(size=(140, 40)) as pilot:
        screen = await _open_repeater(pilot)
        first = screen._active_tab_id
        panes_before = len(_pane_ids(screen))

        screen.action_new_tab()
        await _wait(lambda: len(_pane_ids(screen)) == panes_before + 1, pilot)
        closing = screen._active_tab_id
        assert closing is not None and closing != first

        screen.action_close_tab()
        await _wait(lambda: len(_pane_ids(screen)) == panes_before, pilot)
        await _wait(lambda: screen._active_tab_id != closing, pilot)

        assert closing not in screen._tab_registry, "закрытая вкладка осталась в реестре"
        assert screen._tab_registry.ids == _pane_ids(screen), "реестр и лента разошлись после закрытия"
        assert screen._active_tab_id == screen._tab_registry.active_id == first

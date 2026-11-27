"""Renaming an Intruder tab (double click / F2).

Defect: the screen mounted ITS OWN `Input` with the same id that the tab panel
already creates. The tree ended up with two fields sharing an identical
identifier, so `query_one` found the hidden first one — the visible field never
got focus and renaming "did not work". On top of that, Intruder had no CSS rule
for the field (Repeater did), so the field popped up in the middle of the panel.

The tests pin down: there is a single field, it is visible and focused,
submitting changes the tab label and state, and the field is hidden afterwards.
"""

from __future__ import annotations

import types

import pytest
from textual.widgets import Input

from pentool.tui.app import PentoolApp


async def _settle(pilot, cycles: int = 15) -> None:
    for _ in range(cycles):
        await pilot.pause()


async def _open_intruder(pilot):
    app = pilot.app
    await _settle(pilot)
    app.action_switch_module("intruder")
    await _settle(pilot, 25)
    return app.query_one("IntruderScreen")


@pytest.mark.asyncio
async def test_rename_input_is_not_duplicated() -> None:
    app = PentoolApp()
    app._skip_project_guard = True
    async with app.run_test(size=(160, 45)) as pilot:
        screen = await _open_intruder(pilot)
        panel = screen._tc_panel
        tab_id = panel.active_tab_id

        screen._start_rename(tab_id)
        await _settle(pilot, 10)

        matches = panel.query(f"#{screen._rename_input_id}")
        assert len(matches) == 1, f"полей переименования {len(matches)} — снова дубликат id"


@pytest.mark.asyncio
async def test_rename_input_becomes_visible_and_focused() -> None:
    app = PentoolApp()
    app._skip_project_guard = True
    async with app.run_test(size=(160, 45)) as pilot:
        screen = await _open_intruder(pilot)
        panel = screen._tc_panel
        tab_id = panel.active_tab_id

        screen._start_rename(tab_id)
        await _settle(pilot, 10)

        inp = panel.query_one(f"#{screen._rename_input_id}", Input)
        assert inp.display is True, "поле переименования осталось скрытым"
        assert inp.has_focus, "поле не получило фокус — ввод уйдёт в другое место"
        assert inp.value == panel.get_state(tab_id).name


@pytest.mark.asyncio
async def test_submitting_a_new_name_renames_the_tab() -> None:
    app = PentoolApp()
    app._skip_project_guard = True
    async with app.run_test(size=(160, 45)) as pilot:
        screen = await _open_intruder(pilot)
        panel = screen._tc_panel
        tab_id = panel.active_tab_id

        screen._start_rename(tab_id)
        await _settle(pilot, 10)
        inp = panel.query_one(f"#{screen._rename_input_id}", Input)

        # Bubbling order matches the app: the panel first, then the screen (saves).
        event = types.SimpleNamespace(input=inp, value="RENAMED-TAB")
        panel.on_input_submitted(event)
        screen.on_input_submitted(event)
        await _settle(pilot, 15)

        assert panel.get_state(tab_id).name == "RENAMED-TAB"
        assert panel.tabs_content.get_tab(tab_id).label == "RENAMED-TAB"
        assert inp.display is False, "поле осталось висеть поверх вкладок"

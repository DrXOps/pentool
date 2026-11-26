"""Every module's header must actually show what its `HeaderSpec` describes.

This is the check that was missing when the owner reported "Recon has no Start/Stop": the
spec could list state buttons while the header showed none, and no test compared the two —
the header was only ever tested for the modules that happened to be covered by hand.
"""

from __future__ import annotations

import pytest

from pentool.tui import module_catalog
from pentool.tui.app import PentoolApp
from pentool.tui.header import HeaderProvider


async def _settle(pilot, rounds: int = 20) -> None:
    for _ in range(rounds):
        await pilot.pause()


@pytest.mark.asyncio
async def test_header_shows_the_state_and_actions_the_screen_declares() -> None:
    app = PentoolApp()
    app._skip_project_guard = True
    problems: list[str] = []

    async with app.run_test(size=(200, 50)) as pilot:
        await _settle(pilot)
        for entry in module_catalog.CATALOG:
            app.action_switch_module(entry.id)
            await _settle(pilot, 30)

            screen = app.module_screen(entry.id)
            if not isinstance(screen, HeaderProvider):
                continue
            spec = screen.header_spec()
            if spec.is_empty():
                continue

            visible_state = [b for b in app.query("#hdr-state ToolbarButton") if b.display]
            visible_actions = [b for b in app.query("#hdr-actions ToolbarButton") if b.display]
            visible_tabs = [b for b in app.query("#hdr-tabs ToolbarButton") if b.display]

            if len(spec.state) > len(visible_state):
                problems.append(f"{entry.id}: state {len(spec.state)} в спеке, {len(visible_state)} на экране")
            if len(spec.actions) > len(visible_actions):
                problems.append(f"{entry.id}: actions {len(spec.actions)} в спеке, {len(visible_actions)} на экране")
            if len(spec.tabs) > len(visible_tabs):
                problems.append(f"{entry.id}: tabs {len(spec.tabs)} в спеке, {len(visible_tabs)} на экране")

    assert not problems, "шапка не показывает то, что объявляет экран:\n  " + "\n  ".join(problems)

"""A one-line row with a bottom border must leave a row for its content.

Owner's report (Comparer tools vanished) was not a missing widget: `#cmp-stat-bar` had
`height: 1` plus `border-bottom`, so the border consumed the only row and the row's content area
was 0 tall. The buttons were in the DOM, had sizes, and were painted outside their parent's area
— invisible. The check is geometry, not presence.
"""

from __future__ import annotations

import pytest

from pentool.tui.app import PentoolApp


async def _settle(pilot, rounds: int = 20) -> None:
    for _ in range(rounds):
        await pilot.pause()


@pytest.mark.asyncio
async def test_comparer_tool_row_has_room_for_its_buttons() -> None:
    app = PentoolApp()
    app._skip_project_guard = True
    async with app.run_test(size=(160, 45)) as pilot:
        await _settle(pilot, 15)
        app.action_switch_module("utils")
        await _settle(pilot, 25)

        screen = app.module_screen("utils")
        screen.select_subtab("comparer")
        await _settle(pilot, 25)

        bar = app.query_one("#cmp-stat-bar")
        assert bar.size.height >= 1, (
            f"Comparer tool row content height is {bar.size.height}: "
            "border-bottom consumed the only row, so the buttons paint outside their parent"
        )

        buttons = list(app.query("#cmp-stat-bar ToolbarButton"))
        assert len(buttons) >= 5, f"row has {len(buttons)} buttons instead of 5"
        for button in buttons:
            assert button.display, f"{button.id} is hidden"
            assert button.size.height >= 1, f"{button.id} has no height and will not render"

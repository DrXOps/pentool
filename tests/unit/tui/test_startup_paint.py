"""Startup paint must equal steady state: no empty placeholder buttons at any point.

The owner reported the interface "blinking" on launch. The header is composed with all
slots up front (to avoid rebuilding it), so the real defect was empty buttons being
*visible* for the first frames and then vanishing. Dashboard legitimately shows state and
counters, so the assertion is about empty slots, not about the header being hidden.
"""

from __future__ import annotations

import pytest

from pentool.tui.app import PentoolApp

EMPTY_SLOT_SELECTOR = (
    "#module-header ToolbarButton.hdr-act, "
    "#module-header ToolbarButton.hdr-tab, "
    "#module-header ToolbarButton.hdr-state, "
    "#module-header ToolbarButton.hdr-more"
)


async def _settle(pilot, rounds: int = 12) -> None:
    for _ in range(rounds):
        await pilot.pause()


def _visible_empty_buttons(app) -> list:
    return [button for button in app.query(EMPTY_SLOT_SELECTOR) if button.display and not str(button.label).strip()]


@pytest.mark.asyncio
async def test_first_frame_has_no_visible_empty_buttons() -> None:
    app = PentoolApp()
    app._skip_project_guard = True
    async with app.run_test(size=(160, 45)) as pilot:
        await _settle(pilot)
        empty = _visible_empty_buttons(app)
        assert not empty, f"на первом кадре видны пустые кнопки шапки: {len(empty)}"


@pytest.mark.asyncio
async def test_opening_a_module_still_has_no_empty_buttons() -> None:
    app = PentoolApp()
    app._skip_project_guard = True
    async with app.run_test(size=(160, 45)) as pilot:
        await _settle(pilot)
        app.action_switch_module("proxy")
        await _settle(pilot, 25)

        empty = _visible_empty_buttons(app)
        assert not empty, f"после открытия модуля видны пустые кнопки шапки: {len(empty)}"

        header = app.query_one("#module-header")
        assert header.display is True, "у модуля с описанием шапка должна быть видна"

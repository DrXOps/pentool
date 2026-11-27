"""Characterization test for Repeater's tabs — the safety net for step 11, stage 2.

Stage 2 replaces the screen's own tab bookkeeping with `TabRegistry` and must not change behaviour.
This test records the behaviour that exists today, in user terms: a new tab appears and becomes
active, closing it leaves the previous tab active, and the tab strip lives in `#repeater-tabs`.
"""

from __future__ import annotations

import pytest

from pentool.tui.app import PentoolApp


async def _settle(pilot, rounds: int = 20) -> None:
    for _ in range(rounds):
        await pilot.pause()


@pytest.mark.asyncio
async def test_new_repeater_tab_becomes_active_and_can_be_closed() -> None:
    app = PentoolApp()
    app._skip_project_guard = True
    async with app.run_test(size=(160, 45)) as pilot:
        await _settle(pilot, 15)
        app.action_switch_module("repeater")
        await _settle(pilot, 30)

        screen = app.module_screen("repeater")
        panels = screen.query("#repeater-tabs")
        assert panels, "лента вкладок Repeater не найдена"

        first_id = screen._active_tab_id
        assert first_id, "экран должен открыться с одной вкладкой"
        first_count = len(screen.query("#repeater-tabs TabPane"))

        screen.action_new_tab()
        for _ in range(100):
            if len(screen.query("#repeater-tabs TabPane")) > first_count:
                break
            await pilot.pause()

        assert len(screen.query("#repeater-tabs TabPane")) == first_count + 1, "новая вкладка не появилась"
        assert screen._active_tab_id != first_id, "новая вкладка должна стать активной"

        second_id = screen._active_tab_id
        screen.action_close_tab()
        for _ in range(200):
            if len(screen.query("#repeater-tabs TabPane")) == first_count:
                break
            await pilot.pause()

        assert len(screen.query("#repeater-tabs TabPane")) == first_count, "вкладка не закрылась"
        assert screen._active_tab_id != second_id, "после закрытия активной вкладки должна остаться другая"

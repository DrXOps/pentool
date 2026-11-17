"""Переименование вкладки Intruder (двойной клик / F2).

Дефект: экран монтировал СВОЙ `Input` с тем же id, что уже создаёт панель
вкладок. В дереве оказывались два поля с одинаковым идентификатором,
`query_one` находил скрытое первое — видимое оставалось без фокуса, и
переименование «не работало». Плюс у Intruder не было CSS-правила для поля
(у Repeater было), поэтому поле всплывало посреди панели.

Тесты фиксируют: поле одно, оно видимо и в фокусе, отправка меняет подпись
вкладки и состояние, после ввода поле скрывается.
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
        assert inp.value == panel._states[tab_id].name


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

        # Порядок всплытия как в приложении: панель, затем экран (сохранение).
        event = types.SimpleNamespace(input=inp, value="RENAMED-TAB")
        panel.on_input_submitted(event)
        screen.on_input_submitted(event)
        await _settle(pilot, 15)

        assert panel._states[tab_id].name == "RENAMED-TAB"
        assert panel.tabs_content.get_tab(tab_id).label == "RENAMED-TAB"
        assert inp.display is False, "поле осталось висеть поверх вкладок"

"""Scanner's tabs are owned by one registry (step 11, stage 5).

`test_scanner_tab_behaviour.py` pins what the user sees. This file pins the ownership the
migration introduced: the screen keeps no tab list and no active id of its own, the widget is
still a plain `TabbedContent`, and registry/strip agree after a tab is created or closed.
"""

from __future__ import annotations

import pytest
from pentool.tui.screens.scanner.screen import ScannerScreen

from pentool.core.license import LicenseInfo
from pentool.tui.app import PentoolApp
from pentool.tui.widgets.tab_registry import TabRegistry

PRO = LicenseInfo(valid=True, plan="pro", features=["scanner_pro"])


@pytest.fixture(autouse=True)
def _pro_license(monkeypatch):
    import pentool.core.license

    monkeypatch.setattr(pentool.core.license, "get_session_license", lambda: PRO)


@pytest.fixture(autouse=True)
def _no_project(monkeypatch):
    monkeypatch.setattr(PentoolApp, "db_path", property(lambda _self: ""))


async def _wait(predicate, pilot, frames: int = 120) -> None:
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
async def test_the_screen_keeps_no_tab_list_of_its_own() -> None:
    app = PentoolApp()
    app._skip_project_guard = True
    async with app.run_test(size=(160, 45)) as pilot:
        screen = await _open_scanner(pilot)

        assert isinstance(screen._tab_registry, TabRegistry)
        assert "_tabs" not in screen.__dict__, (
            "у экрана снова свой список вкладок — два источника правды, расхождение будет молчаливым"
        )
        assert "_active_tab_id" not in screen.__dict__, "у экрана снова своя активная вкладка"
        assert screen._tabs == screen._tab_registry.states
        assert screen._active_tab_id == screen._tab_registry.active_id
        assert screen._active_tab is screen._tab_registry.active


@pytest.mark.asyncio
async def test_new_and_closed_tabs_keep_registry_and_strip_in_step() -> None:
    app = PentoolApp()
    app._skip_project_guard = True
    async with app.run_test(size=(160, 45)) as pilot:
        screen = await _open_scanner(pilot)
        assert screen._tab_registry.ids == _pane_ids(screen)
        first = screen._active_tab_id

        screen.action_new_tab()
        await _wait(lambda: len(_pane_ids(screen)) == 2, pilot)
        await _wait(lambda: screen._active_tab_id != first, pilot)
        assert screen._tab_registry.ids == _pane_ids(screen), "реестр и лента разошлись по порядку"

        closing = screen._active_tab_id
        assert closing is not None
        screen.action_close_tab()
        await _wait(lambda: len(_pane_ids(screen)) == 1, pilot)

        assert closing not in screen._tab_registry, "закрытая вкладка осталась в реестре"
        assert screen._tab_registry.ids == _pane_ids(screen), "реестр и лента разошлись после закрытия"
        assert screen._active_tab_id == screen._tab_registry.active_id == first

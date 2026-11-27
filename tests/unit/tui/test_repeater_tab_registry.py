"""Repeater's tabs are owned by one registry and one panel (step 11).

The characterization files (`test_repeater_tab_behaviour`,
`test_repeater_tab_state_survives`) pin how the tab strip behaves. This file pins
what the migration changed: the screen keeps no tab list, no active id and no tab
counter of its own — states come from `TabRegistry`, panes from
`TabbedContentPanel`, and the screen only owns the document data (request text,
persistence). The panel's own messages are the only way the screen learns about tabs.
"""

from __future__ import annotations

import pytest
from textual.widgets import Input, TabPane

from pentool.tui.app import PentoolApp
from pentool.tui.screens.repeater.screen import RepeaterScreen
from pentool.tui.widgets.tab_panel import TabbedContentPanel
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
        assert "_tab_counter" not in screen.__dict__, "у экрана снова свой счётчик вкладок"
        assert screen._tabs == screen._tab_registry.states
        assert screen._active_tab_id == screen._tab_registry.active_id

        # Panes and labels are the panel's; states are the same registry object the
        # screen reads, so there is nothing to keep in sync between them.
        panel = screen.query_one("#repeater-tabs-panel", TabbedContentPanel)
        assert panel is screen._tabs_panel
        assert panel.tab_count == len(screen._tab_registry)
        assert panel.active_state is screen._tab_registry.active
        assert screen.query_one("#repeater-tabs") is screen._tabs_w, (
            "внутренний TabbedContent потерял исторический id #repeater-tabs"
        )


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


# ── The panel's messages are the screen's only tab contract ─────────────────
# These tests drive the real registry table (`repeater_tabs`): the screen must
# persist a rename, and a project switch must not be mistaken for "the user
# deleted these tabs".


async def _db_tabs(db_path: str) -> list[dict]:
    from pentool.modules.repeater import Repeater

    repeater = Repeater(db_path=db_path)
    try:
        return await repeater.get_tabs()
    finally:
        await repeater.close()


async def _wait_tabs(db_path: str, count: int, pilot) -> list[dict]:
    tabs: list[dict] = []
    for _ in range(80):
        tabs = await _db_tabs(db_path)
        if len(tabs) == count:
            return tabs
        await pilot.pause()
    return tabs


async def _empty_project_db(tmp_path, monkeypatch) -> str:
    from pentool.core.db_schema import init_db

    db_path = str(tmp_path / "project.db")
    await init_db(db_path)
    # Overrides the autouse fixture that steers the screen away from the machine DB.
    monkeypatch.setattr(RepeaterScreen, "_get_db_path", lambda _self: db_path)
    return db_path


@pytest.mark.asyncio
async def test_renaming_a_tab_persists_the_new_name(tmp_path, monkeypatch) -> None:
    db_path = await _empty_project_db(tmp_path, monkeypatch)

    app = PentoolApp()
    app._skip_project_guard = True
    async with app.run_test(size=(140, 40)) as pilot:
        screen = await _open_repeater(pilot)
        await _wait_tabs(db_path, 1, pilot)
        tab_id = screen._active_tab_id
        assert tab_id is not None

        panel = screen._tabs_panel
        panel.start_rename(tab_id)
        field = panel.query_one("#repeater-rename-input", Input)
        field.value = "Login"
        field.post_message(Input.Submitted(field, "Login"))

        tabs: list[dict] = []
        for _ in range(80):
            tabs = await _db_tabs(db_path)
            if tabs and tabs[0]["tab_name"] == "Login":
                break
            await pilot.pause()

    assert tabs and tabs[0]["tab_name"] == "Login", "переименование не дошло до таблицы вкладок"
    state = screen._get_tab_state(tab_id)
    assert state is not None and state.name == "Login"


@pytest.mark.asyncio
async def test_project_switch_does_not_delete_the_previous_projects_tabs(tmp_path, monkeypatch) -> None:
    from pentool.core.db_schema import init_db
    from pentool.modules.repeater import Repeater

    original = str(tmp_path / "original.db")
    other = str(tmp_path / "other.db")
    await init_db(original)
    await init_db(other)
    seed = Repeater(db_path=original)
    await seed.save_tab("uid-one", "Login", "PUT /login HTTP/1.1\r\nHost: a\r\n\r\n", 0)
    await seed.save_tab("uid-two", "Search", "GET /s HTTP/1.1\r\nHost: b\r\n\r\n", 1)
    await seed.close()
    monkeypatch.setattr(RepeaterScreen, "_get_db_path", lambda _self: original)

    app = PentoolApp()
    app._skip_project_guard = True
    async with app.run_test(size=(140, 40)) as pilot:
        screen = await _open_repeater(pilot)
        await _wait(lambda: len(screen._tabs) == 2, pilot)

        await screen.reload_from_project(other)
        await _wait(lambda: len(screen._tabs) == 1, pilot)

    rows = await _db_tabs(original)
    assert [row["tab_name"] for row in rows] == ["Login", "Search"], (
        "переключение проекта удалило вкладки прошлого проекта: закрытие вкладок при смене "
        "проекта означало «пользователь их удалил»"
    )

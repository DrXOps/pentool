"""Repeater: a tab's state must catch up with its editor when the tab changes.

The defect this file was written for. ``action_new_tab()`` sets
``_active_tab_id`` to the new tab immediately, while ``TabActivated`` arrives
later and first of all calls ``_save_current_tab_state()`` — and that reads
exactly ``_active_tab_id``. By that moment it already holds the new tab, whose
editor is not built yet, so the save comes out a no-op (``ui_ready`` guards
that), and the text typed in the tab being left lands neither in its ``state``
nor in the DB.

The user does not see this: the widget lives in the DOM and remembers the text
until the project is reloaded. The loss shows up exactly where it should have
saved the day — when restoring tabs from history: the tab opens with the previous
request.

The tests run on a live screen (like the neighbouring
``test_repeater_new_tab_request``), but auto-saving to the DB is stubbed out: what
is checked is the tab state, not the project history, and a unit test must not
leave rows in the real database.
"""

from __future__ import annotations

import pytest
from textual.css.query import NoMatches

from pentool.tui.app import PentoolApp
from pentool.tui.screens.repeater.screen import RepeaterScreen

MARK = "PUT /state-probe HTTP/1.1\r\nHost: probe.example\r\n\r\n"


@pytest.fixture(autouse=True)
def _no_project_history(monkeypatch):
    """No project history at all: the test creates the tabs, not the machine's DB.

    Without this, `on_mount` loads tabs from `~/.config/pentool/pentool.db`,
    their number and contents depend on the machine, and waiting for a tab to be
    ready starts depending on how many foreign tabs get mounted next to it.
    """
    monkeypatch.setattr(RepeaterScreen, "_get_db_path", lambda _self: "")


async def _open_repeater(pilot, persist: bool = False) -> RepeaterScreen:
    await pilot.pause()
    await pilot.press("R")
    await _settle(pilot)
    screen = pilot.app.query_one(RepeaterScreen)
    if not persist:
        # The project history must not become part of the test's assertions.
        screen._auto_save_tab_to_db = lambda _state: None  # type: ignore[method-assign]
    return screen


async def _settle(pilot, cycles: int = 20) -> None:
    for _ in range(cycles):
        await pilot.pause()


async def _wait_built(screen: RepeaterScreen, tab_id: str, pilot) -> None:
    """Wait until the tab has an editor and that editor holds something."""
    for _ in range(60):
        state = screen._get_tab_state(tab_id)
        if state is not None and state.ui_ready:
            return
        await pilot.pause()
    raise AssertionError(f"вкладка {tab_id} так и не собралась за 60 кадров")


def _text(screen: RepeaterScreen, tab_id: str) -> str:
    try:
        return screen._editor(tab_id).get_text()
    except NoMatches:
        return ""


@pytest.mark.asyncio
async def test_editing_then_opening_a_new_tab_commits_the_edit() -> None:
    """The text of the tab being left must reach its state before the tab switch."""
    app = PentoolApp()
    app._skip_project_guard = True
    async with app.run_test(size=(140, 40)) as pilot:
        screen = await _open_repeater(pilot)
        first = screen._active_tab_id
        assert first is not None
        await _wait_built(screen, first, pilot)

        screen._editor(first).load_raw(MARK)
        await _settle(pilot)
        assert "state-probe" in _text(screen, first), "предусловие: текст должен быть в редакторе"

        screen.action_new_tab()
        await _settle(pilot)

        state = screen._get_tab_state(first)
        assert state is not None
        assert "state-probe" in state.request_text, (
            "состояние вкладки осталось с прежним запросом: сохранение при открытии "
            "новой вкладки сработало для новой (ещё не собранной) вкладки, а не для покидаемой"
        )


@pytest.mark.asyncio
async def test_switching_tabs_commits_the_outgoing_edit() -> None:
    """The ordinary tab-switching path: the tab left behind saves its own text."""
    app = PentoolApp()
    app._skip_project_guard = True
    async with app.run_test(size=(140, 40)) as pilot:
        screen = await _open_repeater(pilot)
        first = screen._active_tab_id
        await _wait_built(screen, first, pilot)

        screen.action_new_tab()
        await _settle(pilot)
        second = screen._active_tab_id
        assert second is not None and second != first
        await _wait_built(screen, second, pilot)

        screen._editor(second).load_raw(MARK)
        await _settle(pilot)

        screen._tabs_w.active = first
        await _settle(pilot)

        state = screen._get_tab_state(second)
        assert state is not None
        assert "state-probe" in state.request_text, (
            "текст ушедшей вкладки не сохранён при переключении: TabActivated "
            "сохраняет не ту вкладку, или редактор не отдал текст"
        )


@pytest.mark.asyncio
async def test_closing_a_tab_removes_state_and_pane_but_not_the_neighbour() -> None:
    app = PentoolApp()
    app._skip_project_guard = True
    async with app.run_test(size=(140, 40)) as pilot:
        screen = await _open_repeater(pilot)
        first = screen._active_tab_id
        await _wait_built(screen, first, pilot)
        screen._editor(first).load_raw("GET /keeper HTTP/1.1\r\nHost: keeper\r\n\r\n")
        await _settle(pilot)

        screen.action_new_tab()
        await _settle(pilot)
        second = screen._active_tab_id
        assert second is not None and second != first
        await _wait_built(screen, second, pilot)

        panes_before = len(list(screen._tabs_w.query("TabPane")))
        screen.action_close_tab()
        await _settle(pilot)

        assert screen._get_tab_state(second) is None, "состояние закрытой вкладки осталось в _tabs"
        assert second not in [t.tab_id for t in screen._tabs]
        assert len(list(screen._tabs_w.query("TabPane"))) == panes_before - 1, "панель вкладки не снята"

        screen._tabs_w.active = first
        await _settle(pilot)
        assert "keeper" in _text(screen, first), "соседняя вкладка потеряла свой запрос при закрытии"

        # The screen must not be left without tabs: the last one is never closed.
        # How many tabs there were at the start is a question of project history,
        # so it is the invariant that gets checked here, not a specific number.
        while len(screen._tabs) > 1:
            screen._tabs_w.active = screen._tabs[-1].tab_id
            await _settle(pilot)
            screen.action_close_tab()
            await _settle(pilot)
        assert len(screen._tabs) == 1, "вкладки не закрывались до одной"

        screen.action_close_tab()
        await _settle(pilot)
        assert len(screen._tabs) == 1, "последняя вкладка закрылась — экран остался без вкладок"


# ── Tab registry in the DB (F-053) ──────────────────────────────────────────
# The set of tabs is the `repeater_tabs` table, the send history is
# `repeater_entries`. These tests go through the real schema and the real
# module, on a temporary database.


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
async def test_tabs_are_restored_from_the_registry(tmp_path, monkeypatch) -> None:
    """Restoring reads the tab registry, not the send history."""
    from pentool.modules.repeater import Repeater

    db_path = await _empty_project_db(tmp_path, monkeypatch)
    seed = Repeater(db_path=db_path)
    await seed.save_tab("uid-one", "Login", "PUT /login HTTP/1.1\r\nHost: a\r\n\r\n", 0)
    await seed.save_tab("uid-two", "Search", "GET /s?q=1 HTTP/1.1\r\nHost: b\r\n\r\n", 1)
    await seed.close()

    app = PentoolApp()
    app._skip_project_guard = True
    async with app.run_test(size=(140, 40)) as pilot:
        screen = await _open_repeater(pilot)
        for _ in range(80):
            if len(screen._tabs) == 2:
                break
            await pilot.pause()

    assert [t.tab_uid for t in screen._tabs] == ["uid-one", "uid-two"], (
        "вкладки восстановлены не из repeater_tabs или потеряли свои uid — второй перезапуск создал бы дубли строк"
    )
    assert screen._tabs[0].name == "Login"
    assert "PUT /login" in screen._tabs[0].request_text


@pytest.mark.asyncio
async def test_a_new_tab_is_persisted_without_being_edited(tmp_path, monkeypatch) -> None:
    db_path = await _empty_project_db(tmp_path, monkeypatch)

    app = PentoolApp()
    app._skip_project_guard = True
    async with app.run_test(size=(140, 40)) as pilot:
        screen = await _open_repeater(pilot, persist=True)
        tabs = await _wait_tabs(db_path, 1, pilot)

    assert len(tabs) == 1, "вкладка не попала в реестр, пока её не отредактировали"
    assert tabs[0]["tab_uid"] == screen._tabs[0].tab_uid


@pytest.mark.asyncio
async def test_a_closed_tab_is_forgotten_in_the_registry(tmp_path, monkeypatch) -> None:
    """The main property of F-053: a closed tab does not come back after a restart."""
    db_path = await _empty_project_db(tmp_path, monkeypatch)

    app = PentoolApp()
    app._skip_project_guard = True
    async with app.run_test(size=(140, 40)) as pilot:
        screen = await _open_repeater(pilot, persist=True)
        await _wait_tabs(db_path, 1, pilot)

        screen.action_new_tab()
        await _settle(pilot)
        second = screen._active_tab_id
        assert second is not None
        await _wait_built(screen, second, pilot)
        await _wait_tabs(db_path, 2, pilot)

        closing = screen._get_tab_state(second)
        assert closing is not None
        closed_uid = closing.tab_uid

        screen.action_close_tab()
        tabs = await _wait_tabs(db_path, 1, pilot)

    assert closed_uid not in [t["tab_uid"] for t in tabs], (
        "закрытая вкладка осталась в реестре — после перезапуска она вернётся"
    )

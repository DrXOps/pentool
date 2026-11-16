"""A new Repeater tab must open with its request, not an empty editor.

The bug: ``TabbedContent`` announces a freshly added tab twice — once when the
pane is added, once when it becomes active — and the second
``TabActivated`` arrives while the tab body is still being built through a
chain of ``call_after_refresh`` callbacks. ``on_tabbed_content_tab_activated``
saves the outgoing tab's text first, so the second announcement read an editor
that did not exist yet, got ``""`` and wrote it over the tab's own
``request_text``. A brand-new tab therefore opened blank in most runs and
showed the default ``GET / HTTP/1.1`` in the rest — a race, not a design.

Two properties are checked here, because they failed for different reasons:

* the text survives the double announcement (``ui_ready``);
* it is actually loaded into the editor, which had to wait for the editor's
  own ``#cp-body-widget`` to be composed — ``load_raw`` swallowed the
  resulting ``NoMatches`` and left an empty editor while claiming success.
"""

from __future__ import annotations

import pytest
from textual.css.query import NoMatches

from pentool.tui.app import PentoolApp
from pentool.tui.screens.repeater.screen import RepeaterScreen

DEFAULT_REQUEST = "GET / HTTP/1.1"


@pytest.fixture(autouse=True)
def _no_project_history(monkeypatch):
    """Экран должен стартовать без истории проекта этой машины.

    Иначе `on_mount` восстанавливает вкладки из `~/.config/pentool/pentool.db`,
    активной становится восстановленная вкладка со своим сохранённым запросом,
    и утверждение «новая вкладка показывает запрос по умолчанию» зависит от
    того, чем пользователь занимался до запуска тестов. Ровно так этот файл и
    падал в полном прогоне, проходя в одиночку.
    """
    monkeypatch.setattr(RepeaterScreen, "_get_db_path", lambda _self: "")


async def _open_repeater(pilot) -> RepeaterScreen:
    await pilot.pause()
    await pilot.press("R")
    await pilot.pause()
    return pilot.app.query_one(RepeaterScreen)


async def _wait_text(screen: RepeaterScreen, pilot, expected: str) -> str:
    for _ in range(40):
        try:
            text = screen._editor().get_text()
        except NoMatches:
            text = ""
        if text.startswith(expected):
            return text
        await pilot.pause()
    return text


@pytest.mark.asyncio
async def test_new_tab_shows_the_default_request() -> None:
    app = PentoolApp()
    app._skip_project_guard = True
    async with app.run_test(size=(120, 30)) as pilot:
        screen = await _open_repeater(pilot)
        text = await _wait_text(screen, pilot, DEFAULT_REQUEST)

    assert text.startswith(DEFAULT_REQUEST), f"a new tab opened empty: {text!r}"


@pytest.mark.asyncio
async def test_second_tab_keeps_its_own_request() -> None:
    """The outgoing tab's text must not be overwritten by the incoming tab."""
    app = PentoolApp()
    app._skip_project_guard = True
    async with app.run_test(size=(120, 30)) as pilot:
        screen = await _open_repeater(pilot)
        await _wait_text(screen, pilot, DEFAULT_REQUEST)
        screen._editor().load_raw("GET /first HTTP/1.1\r\nHost: a.example\r\n\r\n")

        screen.action_new_tab()
        second = await _wait_text(screen, pilot, DEFAULT_REQUEST)
        assert second.startswith(DEFAULT_REQUEST), f"second tab opened empty: {second!r}"

        first_id = screen._tabs[0].tab_id
        screen._tabs_w.active = first_id
        await pilot.pause()
        first = await _wait_text(screen, pilot, "GET /first")
        assert first.startswith("GET /first"), f"first tab lost its own text: {first!r}"


@pytest.mark.asyncio
async def test_switching_to_a_tab_whose_state_is_not_ready_is_a_no_op() -> None:
    """``ui_ready`` is the gate: a not-yet-built tab must not be read back.

    Reproduces the exact sequence the race produced — activation while the
    body is absent — without depending on frame timing.
    """
    app = PentoolApp()
    app._skip_project_guard = True
    async with app.run_test(size=(120, 30)) as pilot:
        screen = await _open_repeater(pilot)
        await _wait_text(screen, pilot, DEFAULT_REQUEST)
        state = screen._tabs[0]
        state.ui_ready = False

        before = state.request_text
        screen._save_current_tab_state()

        assert state.request_text == before, "an unbuilt tab reported its request as empty and overwrote it"

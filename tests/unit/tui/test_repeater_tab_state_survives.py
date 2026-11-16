"""Repeater: состояние вкладки должно догонять её редактор при смене вкладки.

Дефект, ради которого написан этот файл. ``action_new_tab()`` выставляет
``_active_tab_id`` на новую вкладку сразу, а ``TabActivated`` приходит позже и
первым делом зовёт ``_save_current_tab_state()`` — а тот читает именно
``_active_tab_id``. К этому моменту там уже новая вкладка, редактор которой ещё
не собран, поэтому сохранение выходит no-op (страхует ``ui_ready``), и текст,
набранный в покидаемой вкладке, не попадает ни в её ``state``, ни в БД.

Пользователь этого не видит: виджет живёт в DOM и помнит текст до перезагрузки
проекта. Потеря проявляется ровно там, где должна была спасти — при
восстановлении вкладок из истории: вкладка открывается с прежним запросом.

Тесты работают на живом экране (как соседний ``test_repeater_new_tab_request``),
но автосохранение в БД подменено: проверяется состояние вкладки, а не история
проекта, и юнит-тест не должен оставлять строк в настоящей базе.
"""

from __future__ import annotations

import pytest
from textual.css.query import NoMatches

from pentool.tui.app import PentoolApp
from pentool.tui.screens.repeater.screen import RepeaterScreen

MARK = "PUT /state-probe HTTP/1.1\r\nHost: probe.example\r\n\r\n"


@pytest.fixture(autouse=True)
def _no_project_history(monkeypatch):
    """Никакой истории проекта: вкладки создаёт сам тест, а не база машины.

    Без этого `on_mount` поднимает вкладки из `~/.config/pentool/pentool.db`,
    их число и содержимое зависят от машины, а ожидание готовности вкладки
    начинает зависеть от того, сколько чужих вкладок монтируется рядом.
    """
    monkeypatch.setattr(RepeaterScreen, "_get_db_path", lambda _self: "")


async def _open_repeater(pilot) -> RepeaterScreen:
    await pilot.pause()
    await pilot.press("R")
    await _settle(pilot)
    screen = pilot.app.query_one(RepeaterScreen)
    # История проекта не должна становиться частью утверждений теста.
    screen._auto_save_tab_to_db = lambda _state: None  # type: ignore[method-assign]
    return screen


async def _settle(pilot, cycles: int = 20) -> None:
    for _ in range(cycles):
        await pilot.pause()


async def _wait_built(screen: RepeaterScreen, tab_id: str, pilot) -> None:
    """Дождаться, пока у вкладки появится редактор и он чем-то заполнен."""
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
    """Текст покидаемой вкладки обязан попасть в её state до смены активной."""
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
    """Обычный путь смены вкладки: ушедшая вкладка сохраняет свой текст."""
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

        # Экран не должен остаться без вкладок: последняя не закрывается.
        # Сколько вкладок было на старте — вопрос истории проекта, поэтому
        # проверяется именно инвариант, а не конкретное число.
        while len(screen._tabs) > 1:
            screen._tabs_w.active = screen._tabs[-1].tab_id
            await _settle(pilot)
            screen.action_close_tab()
            await _settle(pilot)
        assert len(screen._tabs) == 1, "вкладки не закрывались до одной"

        screen.action_close_tab()
        await _settle(pilot)
        assert len(screen._tabs) == 1, "последняя вкладка закрылась — экран остался без вкладок"

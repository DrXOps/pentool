"""Тесты для TabbedContentPanel — универсального таб-контейнера.

Проверяет:
- Создание/удаление табов
- Переключение
- Сигналы (TabCreated, TabActivated, TabDeactivated, TabClosed)
- rename
- load_from_storage / close_all
"""
from __future__ import annotations

from dataclasses import dataclass

import pytest
from unittest.mock import MagicMock, patch

from textual.widgets import TabPane


@pytest.fixture
def panel():
    """Create a TabbedContentPanel fixture for testing."""
    from pentool.tui.widgets.tab_panel import TabbedContentPanel
    p = TabbedContentPanel(
        id="test-tabs",
        tab_id_prefix="test-tab-",
        min_tabs=1,
    )
    mock_tc = MagicMock()
    p.query_one = MagicMock(return_value=mock_tc)
    # call_after_refresh — вызываем синхронно
    p.call_after_refresh = lambda fn, *a, **kw: fn(*a)
    # post_message — записываем для проверки
    p._test_messages = []
    p.post_message = lambda msg: p._test_messages.append(msg)
    return p


@dataclass
class _TestState:
    tab_id: str = ""
    tab_uid: str = ""
    name: str = ""
    value: str = ""


def test_can_instantiate():
    from pentool.tui.widgets.tab_panel import TabbedContentPanel
    p = TabbedContentPanel(id="x", tab_id_prefix="x-")
    assert p.tab_count == 0


def test_action_new_tab_creates_internal_state(panel):
    state = _TestState(tab_id="test-tab-1", name="Tab 1")
    panel.action_new_tab(state=state)
    assert panel.tab_count == 1
    assert panel.active_tab_id == "test-tab-1"
    assert panel.active_state is state
    assert panel.get_state("test-tab-1") is state


def test_action_new_tab_auto_generates_default(panel):
    tab_id = panel.action_new_tab(name="Default Tab")
    assert tab_id is not None
    assert panel.tab_count == 1
    state = panel.active_state
    assert state is not None
    assert getattr(state, "name", None) == "Default Tab"


def test_action_new_tab_multiple(panel):
    s1 = _TestState(tab_id="test-tab-1", name="Tab 1")
    s2 = _TestState(tab_id="test-tab-2", name="Tab 2")
    panel.action_new_tab(state=s1)
    panel.action_new_tab(state=s2)
    assert panel.tab_count == 2
    assert panel.active_state is s2


def test_close_tab_last_does_not_close(panel):
    state = _TestState(tab_id="test-tab-1", name="Tab 1")
    panel.action_new_tab(state=state)
    panel.action_close_tab()
    assert panel.tab_count == 1


def test_close_tab_removes_tab(panel):
    s1 = _TestState(tab_id="test-tab-1", name="Tab 1")
    s2 = _TestState(tab_id="test-tab-2", name="Tab 2")
    panel.action_new_tab(state=s1)
    panel.action_new_tab(state=s2)
    assert panel.tab_count == 2
    panel.action_close_tab()
    assert panel.tab_count == 1
    assert panel.active_state is s1


def test_switch_to(panel):
    s1 = _TestState(tab_id="test-tab-1", name="Tab 1")
    s2 = _TestState(tab_id="test-tab-2", name="Tab 2")
    panel.action_new_tab(state=s1)
    panel.action_new_tab(state=s2)
    panel.switch_to("test-tab-1")
    assert panel.active_state is s1


def test_close_all(panel):
    import asyncio
    s1 = _TestState(tab_id="test-tab-1", name="Tab 1")
    s2 = _TestState(tab_id="test-tab-2", name="Tab 2")
    panel.action_new_tab(state=s1)
    panel.action_new_tab(state=s2)
    asyncio.run(panel.close_all())
    assert panel.tab_count == 0
    assert panel.active_tab_id is None


def test_all_states(panel):
    s1 = _TestState(tab_id="test-tab-1", name="Tab 1")
    s2 = _TestState(tab_id="test-tab-2", name="Tab 2")
    panel.action_new_tab(state=s1)
    panel.action_new_tab(state=s2)
    states = panel.all_states
    assert len(states) == 2
    assert s1 in states
    assert s2 in states


# ── Test signals ──────────────────────────────────────────────────────

def test_tab_created_signal(panel):
    state = _TestState(tab_id="test-tab-1", name="Tab 1")
    panel.action_new_tab(state=state)
    created = [m for m in panel._test_messages if isinstance(m, panel.TabCreated)]
    assert len(created) >= 1
    assert created[0].tab_id == "test-tab-1"
    assert created[0].tab_state is state


def test_tab_activated_signal(panel):
    state = _TestState(tab_id="test-tab-1", name="Tab 1")
    panel.action_new_tab(state=state)
    activated = [m for m in panel._test_messages if isinstance(m, panel.TabActivated)]
    assert len(activated) >= 1


def test_tab_deactivated_signal(panel):
    s1 = _TestState(tab_id="test-tab-1", name="Tab 1")
    s2 = _TestState(tab_id="test-tab-2", name="Tab 2")
    panel.action_new_tab(state=s1)
    panel.action_new_tab(state=s2)
    panel._test_messages.clear()
    panel.switch_to("test-tab-1")
    deactivated = [m for m in panel._test_messages if isinstance(m, panel.TabDeactivated)]
    assert len(deactivated) >= 1
    assert deactivated[0].tab_state is s2


def test_tab_closed_signal(panel):
    panel._min_tabs = 0
    state = _TestState(tab_id="test-tab-1", name="Tab 1")
    panel.action_new_tab(state=state)
    panel._test_messages.clear()
    panel.action_close_tab()
    closed = [m for m in panel._test_messages if isinstance(m, panel.TabClosed)]
    assert len(closed) >= 1
    assert closed[0].tab_state is state


def test_get_tab_id_by_uid(panel):
    s1 = _TestState(tab_id="test-tab-1", name="Tab 1", tab_uid="abc")
    s2 = _TestState(tab_id="test-tab-2", name="Tab 2", tab_uid="xyz")
    panel.action_new_tab(state=s1)
    panel.action_new_tab(state=s2)
    assert panel.get_tab_id_by_uid("abc") == "test-tab-1"
    assert panel.get_tab_id_by_uid("xyz") == "test-tab-2"
    assert panel.get_tab_id_by_uid("nonexistent") is None

# ── Регрессия: message.control должен возвращать владельца-панель ─────
# Раньше 4 сообщения возвращали `self._widget`, которого у Message НЕТ в
# __slots__ → `AttributeError: 'TabActivated' object has no attribute '_widget'`
# при попытке Textual доставить @on(..., "#id"). Фикс: сообщение хранит owner.


def test_message_control_returns_panel(panel):
    from pentool.tui.widgets.tab_panel import TabbedContentPanel
    st = _TestState(tab_id="test-tab-1", name="Tab 1")
    for cls, args in (
        (TabbedContentPanel.TabCreated, (panel, "test-tab-1", st)),
        (TabbedContentPanel.TabActivated, (panel, "test-tab-1", st)),
        (TabbedContentPanel.TabDeactivated, (panel, "test-tab-1", st)),
        (TabbedContentPanel.TabClosed, (panel, "test-tab-1", st)),
    ):
        msg = cls(*args)
        assert msg.tab_id == "test-tab-1"
        assert msg.tab_state is st
        assert msg.control is panel, f"{cls.__name__}.control должен быть панелью"


def test_dispatch_via_on_selector_no_attribute_error():
    """Доставка @on(..., '#id') через реальный App не должна падать на '._widget'."""
    from textual.app import App, ComposeResult
    from textual import on
    from pentool.tui.widgets.tab_panel import TabbedContentPanel

    received = {"created": 0, "activated": 0, "deactivated": 0}

    class _S:
        tab_id: str = ""
        name: str = ""
        tab_uid: str = ""

    class _App(App):
        def compose(self) -> ComposeResult:
            yield TabbedContentPanel(id="regress-tabs", tab_id_prefix="rt-", min_tabs=1)

        def on_mount(self) -> None:
            self._p = self.query_one("#regress-tabs", TabbedContentPanel)
            self._p.set_default_state_factory(lambda tid, n: _S())
            self._p.action_new_tab(name="A")
            self._p.action_new_tab(name="B")
            self._p.switch_to("rt-2")

        @on(TabbedContentPanel.TabCreated, "#regress-tabs")
        def _created(self, e: TabbedContentPanel.TabCreated) -> None:
            received["created"] += 1
            assert e.control is self._p

        @on(TabbedContentPanel.TabActivated, "#regress-tabs")
        def _activated(self, e: TabbedContentPanel.TabActivated) -> None:
            received["activated"] += 1
            assert e.control is self._p

        @on(TabbedContentPanel.TabDeactivated, "#regress-tabs")
        def _deactivated(self, e: TabbedContentPanel.TabDeactivated) -> None:
            received["deactivated"] += 1
            assert e.control is self._p

    async def _run() -> None:
        async with _App().run_test() as pilot:
            await pilot.pause()

    import asyncio
    asyncio.run(_run())

    assert received["created"] >= 2
    assert received["activated"] >= 2
    assert received["deactivated"] >= 1

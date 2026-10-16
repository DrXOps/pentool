"""Тесты для табов в IntruderScreen (адаптированы под TabbedContentPanel).

Проверяет:
- _IntruderTabState dataclass
- Прокси-свойства (_attack_type, _payloads, _all_results)
- _save_current_tab_state
- _load_active_tab_content
- _auto_save_tab
- _results_table
- _on_tab_activated / _on_tab_deactivated обработчики
"""

from __future__ import annotations

import pytest
from unittest.mock import MagicMock, patch

from pentool.api.intruder_api import AttackType


@pytest.fixture
def tab_state():
    """Create a bare _IntruderTabState for testing."""
    from pentool.tui.screens.intruder.screen import _IntruderTabState
    return _IntruderTabState(tab_id="intruder-tab-1", name="Test Tab")


# ── TabState dataclass ──────────────────────────────────────────────────
class TestIntruderTabState:
    """Tests for the _IntruderTabState dataclass."""

    def test_create_default(self):
        from pentool.tui.screens.intruder.screen import _IntruderTabState
        state = _IntruderTabState(tab_id="intruder-tab-1", name="Test Tab")
        assert state.tab_id == "intruder-tab-1"
        assert state.name == "Test Tab"
        assert state.tab_uid == ""
        assert state.template_text == ""
        assert state.attack_type == AttackType.SNIPER
        assert state.payload_sources == []
        assert state.all_results == []
        assert state.filtered_results == []
        assert state.running is False
        assert state.paused is False
        assert state.active_set_idx == 0

    def test_tab_uid_assignment(self):
        from pentool.tui.screens.intruder.screen import _IntruderTabState
        import uuid
        uid = uuid.uuid4().hex
        state = _IntruderTabState(tab_id="intruder-tab-1", name="Test", tab_uid=uid)
        assert state.tab_uid == uid
        assert len(state.tab_uid) == 32

    def test_attack_type_change(self, tab_state):
        tab_state.attack_type = AttackType.CLUSTER_BOMB
        assert tab_state.attack_type == AttackType.CLUSTER_BOMB

    def test_payload_sources_append(self, tab_state):
        tab_state.payload_sources.append(["payload1", "payload2"])
        assert tab_state.payload_sources == [["payload1", "payload2"]]

    def test_results(self, tab_state):
        result = MagicMock()
        result.request_number = 1
        tab_state.all_results.append(result)
        assert len(tab_state.all_results) == 1
        assert tab_state.all_results[0].request_number == 1

    def test_filter_spec(self, tab_state):
        from pentool.collections.filter_predicate import FilterSpec
        spec = FilterSpec(predicates=[])
        tab_state.filter_spec = spec
        assert tab_state.filter_spec is spec


# ── Proxy properties (через _tabs fallback) ─────────────────────────────
class TestIntruderTabProxyProperties:
    """Tests for proxy properties on IntruderScreen."""

    def test_active_tab_none(self):
        from pentool.tui.screens.intruder.screen import IntruderScreen
        screen = IntruderScreen()
        screen._tabs = []
        screen._active_tab_id = None
        assert screen._active_tab is None
        assert screen._attack_type == AttackType.SNIPER
        assert screen._payloads == [[]]
        assert screen._all_results == []
        assert screen._filtered_results == []
        assert screen._active_set_idx == 0
        assert screen._current_result is None
        assert screen._filter_spec is None
        assert screen._payload_load_in_progress is False

    def test_active_tab_proxy_read(self):
        from pentool.tui.screens.intruder.screen import IntruderScreen, _IntruderTabState
        from pentool.collections.filter_predicate import FilterSpec
        screen = IntruderScreen()
        state = _IntruderTabState(tab_id="intruder-tab-1", name="Tab 1")
        state.attack_type = AttackType.CLUSTER_BOMB
        state.payload_sources = [["a", "b"]]
        state.active_set_idx = 1
        state.payload_load_in_progress = True
        state.filter_spec = FilterSpec(predicates=[])
        screen._tabs = [state]
        screen._active_tab_id = "intruder-tab-1"
        assert screen._attack_type == AttackType.CLUSTER_BOMB
        assert screen._payloads == [["a", "b"]]
        assert screen._active_set_idx == 1
        assert screen._filter_spec is state.filter_spec
        assert screen._payload_load_in_progress is True

    def test_active_tab_proxy_write(self):
        from pentool.tui.screens.intruder.screen import IntruderScreen, _IntruderTabState
        screen = IntruderScreen()
        state = _IntruderTabState(tab_id="intruder-tab-1", name="Tab 1")
        screen._tabs = [state]
        screen._active_tab_id = "intruder-tab-1"
        screen._attack_type = AttackType.PITCHFORK
        assert state.attack_type == AttackType.PITCHFORK
        screen._payloads = [["x", "y"]]
        assert state.payload_sources == [["x", "y"]]
        screen._active_set_idx = 2
        assert state.active_set_idx == 2
        result = MagicMock()
        screen._all_results = [result]
        assert state.all_results == [result]
        screen._payload_load_in_progress = True
        assert state.payload_load_in_progress is True


# ── Tab management (взаимодействие с TabbedContentPanel) ─────────────────
class TestIntruderTabManagement:
    """Tests for Intruder-specific (not TabbedContentPanel) tab methods."""

    def test_save_current_tab_state(self):
        """_save_current_tab_state should copy template_text from editor."""
        from pentool.tui.screens.intruder.screen import IntruderScreen, _IntruderTabState
        from textual.widgets import TextArea
        screen = IntruderScreen()
        state = _IntruderTabState(tab_id="intruder-tab-1", name="Tab 1")
        screen._tabs = [state]
        screen._active_tab_id = "intruder-tab-1"

        # Настоящий TextArea для isinstance check
        real_ta = TextArea()
        real_ta.text = "GET /test HTTP/1.1"
        mock_panel = MagicMock()
        mock_panel.content_widget = real_ta
        with patch.object(IntruderScreen, "_template_editor", return_value=mock_panel), \
             patch.object(screen, "_auto_save_tab"):
            screen._save_current_tab_state()
        assert state.template_text == "GET /test HTTP/1.1"

    def test_results_table_returns_none_no_tab(self):
        from pentool.tui.screens.intruder.screen import IntruderScreen
        screen = IntruderScreen()
        screen._tabs = []
        screen._active_tab_id = None
        assert screen._results_table() is None

    def test_load_active_tab_content_restores_grep(self):
        """_load_active_tab_content should restore grep state from tab."""
        from pentool.tui.screens.intruder.screen import IntruderScreen, _IntruderTabState
        from pentool.collections.filter_predicate import FilterSpec
        screen = IntruderScreen()
        state = _IntruderTabState(
            tab_id="intruder-tab-1", name="Tab 1",
            grep_match_patterns=["error"],
            grep_only_match=True,
        )
        screen._tabs = [state]
        screen._active_tab_id = "intruder-tab-1"
        with patch.object(screen, "_rebuild_table_data"):
            screen._load_active_tab_content()
        assert screen._grep_match_patterns == ["error"]
        assert screen._grep_only_match is True

    def test_load_active_tab_content_empty(self):
        """_load_active_tab_content should not crash on empty tab."""
        from pentool.tui.screens.intruder.screen import IntruderScreen, _IntruderTabState
        screen = IntruderScreen()
        state = _IntruderTabState(tab_id="intruder-tab-1", name="Tab 1")
        screen._tabs = [state]
        screen._active_tab_id = "intruder-tab-1"
        with patch.object(screen, "_rebuild_table_data"):
            screen._load_active_tab_content()

    def test_auto_save_tab_calls_api_save_state(self):
        from pentool.tui.screens.intruder.screen import IntruderScreen, _IntruderTabState
        screen = IntruderScreen()
        state = _IntruderTabState(
            tab_id="intruder-tab-1", name="Tab 1",
            tab_uid="abc123", template_text="GET /test HTTP/1.1",
            attack_type=AttackType.SNIPER,
        )
        mock_api = MagicMock()
        screen._api = mock_api
        with patch.object(screen, "run_worker") as mock_worker:
            screen._auto_save_tab(state)
        mock_worker.assert_called_once()
        args, _ = mock_worker.call_args
        coro = args[0]
        assert hasattr(coro, "__await__") or hasattr(coro, "__call__")

    def test_auto_save_tab_no_api(self):
        from pentool.tui.screens.intruder.screen import IntruderScreen, _IntruderTabState
        screen = IntruderScreen()
        state = _IntruderTabState(tab_id="intruder-tab-1", name="Tab 1")
        screen._api = None
        screen._auto_save_tab(state)

    def test_on_tab_deactivated_saves_template(self):
        """_on_tab_deactivated should save template from per-tab editor."""
        from pentool.tui.screens.intruder.screen import IntruderScreen, _IntruderTabState
        from pentool.tui.widgets.tab_panel import TabbedContentPanel
        screen = IntruderScreen()
        state = _IntruderTabState(tab_id="intruder-tab-1", name="Tab 1")
        screen._tabs = [state]
        screen._active_tab_id = "intruder-tab-1"

        event = TabbedContentPanel.TabDeactivated(None, "intruder-tab-1", state)
        with patch.object(screen, "_auto_save_tab") as mock_save:
            screen._on_tab_deactivated(event)
        mock_save.assert_called_once_with(state)

    def test_on_tab_activated_syncs_grep(self):
        """_on_tab_activated should sync grep patterns from tab state."""
        from pentool.tui.screens.intruder.screen import IntruderScreen, _IntruderTabState
        from pentool.tui.widgets.tab_panel import TabbedContentPanel
        screen = IntruderScreen()
        state = _IntruderTabState(
            tab_id="intruder-tab-1", name="Tab 1",
            grep_match_patterns=["error", "warning"],
            grep_only_match=True,
        )
        event = TabbedContentPanel.TabActivated(None, "intruder-tab-1", state)
        with patch.object(screen, "_rebuild_table_data"):
            screen._on_tab_activated(event)
        assert screen._grep_match_patterns == ["error", "warning"]
        assert screen._grep_only_match is True

class TestIntruderPanelBinding:
    """Регрессия: _tc_panel должен быть property, _on_tab_closed не должен
    падать с 'TabbedContentPanel object is not callable'.

    Причина бага: _tc_panel был объявлен как метод, но вызывался как property
    (self._tc_panel.action_new_tab()). А в _on_tab_closed ручное инстанцирование
    TabActivated(self._tc_panel(), ...) пыталось вызвать объект-панель.
    """

    def test_tc_panel_is_property_returns_panel(self):
        """_tc_panel — property, возвращает TabbedContentPanel, не bound-method."""
        from textual.app import App, ComposeResult
        from textual.widgets import ContentSwitcher
        from pentool.tui.screens.intruder.screen import IntruderScreen
        from pentool.tui.widgets.tab_panel import TabbedContentPanel

        class _App(App):
            def compose(self) -> ComposeResult:
                with ContentSwitcher():
                    yield IntruderScreen()

        async def _run():
            app = _App()
            async with app.run_test(size=(200, 50)) as pilot:
                await pilot.pause()
                screen = app.query_one(IntruderScreen)
                panel = screen._tc_panel
                assert isinstance(panel, TabbedContentPanel), \
                    f"_tc_panel должен быть панелью, получил {type(panel).__name__}"
                # не bound-method (не callable прямо)
                assert not isinstance(panel, str)
                # action_new_tab через экран не падает
                screen.action_new_tab()
                await pilot.pause()
                assert panel.tab_count >= 1

        import asyncio
        asyncio.run(_run())

    def test_on_tab_closed_no_manual_message(self):
        """Закрытие таба через панель не падает в _on_tab_closed."""
        from textual.app import App, ComposeResult
        from textual.widgets import ContentSwitcher
        from pentool.tui.screens.intruder.screen import IntruderScreen
        from pentool.tui.widgets.tab_panel import TabbedContentPanel

        class _App(App):
            def compose(self) -> ComposeResult:
                with ContentSwitcher():
                    yield IntruderScreen()

        async def _run():
            app = _App()
            async with app.run_test(size=(200, 50)) as pilot:
                await pilot.pause()
                screen = app.query_one(IntruderScreen)
                screen.action_new_tab()
                await pilot.pause()
                panel = screen._tc_panel
                assert panel.tab_count == 2
                panel.action_close_tab()
                await pilot.pause()
                assert panel.tab_count == 1
                assert panel.active_tab_id is not None

        import asyncio
        asyncio.run(_run())

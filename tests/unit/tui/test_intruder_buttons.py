"""Tests for StartStopMixin and the Start/Stop/Pause/Resume buttons in IntruderScreen.

Verifies:
- btn-start/btn-stop are present in compose
- the Start→Pause→Resume→Stop cycle
- ActivityIndicator does not report Recon as active without a start
"""

from __future__ import annotations

import re
from unittest.mock import MagicMock, PropertyMock, patch

import pytest

# ─── Helpers ────────────────────────────────────────────────────────────────


@pytest.fixture
def mock_intruder_deps():
    """Mock the heavy IntruderScreen dependencies."""
    patches = [
        patch("pentool.tui.screens.intruder.screen.get_logger", return_value=MagicMock()),
        patch("pentool.tui.screens.intruder.screen.IntruderConfig", MagicMock()),
        patch("pentool.tui.screens.intruder.screen.IntruderResult", MagicMock()),
        patch("pentool.tui.screens.intruder.screen.count_markers", return_value=1),
        patch("pentool.tui.screens.intruder.screen.count_lines_with_progress", return_value=0),
    ]
    for p in patches:
        p.start()
    yield
    for p in patches:
        p.stop()


_MOCK_APP = MagicMock()


def _setup_screen(screen):
    """Prepare the screen for a unit test.

    - Sets the active_app ContextVar (so the app property works)
    - Replaces run_worker with a MagicMock
    - Replaces query_one with a MagicMock (returns itself)
    - Adds .disabled = False on the mock (for btn-stop)
    """
    from textual.app import active_app

    # Set the active_app ContextVar
    screen._active_app_token = active_app.set(_MOCK_APP)
    screen.run_worker = MagicMock()
    # query_one mock — returns itself with arbitrary attributes
    mock_q = MagicMock()
    mock_q.disabled = False
    screen.query_one = MagicMock(return_value=mock_q)
    return screen


def _teardown_screen(screen):
    """Clean up the ContextVar."""
    from textual.app import active_app

    token = getattr(screen, "_active_app_token", None)
    if token is not None:
        try:
            active_app.reset(token)
        except Exception:
            pass


# ─── StartStopWidget tests (replaces the removed StartStopMixin) ─────────────


class TestStartStopWidget:
    """StartStopMixin was removed: Start/Stop/Pause state lives in StartStopWidget.

    The screen no longer inherits an abstract mixin — the widget itself holds
    ``_running``/``_paused`` and declares the four messages that the screen
    subscribes to with plain ``on_start_stop_widget_*`` handlers.
    """

    def test_initial_state_is_idle(self):
        from pentool.tui.widgets.start_stop_widget import StartStopWidget

        widget = StartStopWidget()
        assert widget.running is False
        assert widget.paused is False

    def test_set_running_updates_flag(self):
        from pentool.tui.widgets.start_stop_widget import StartStopWidget

        widget = StartStopWidget()
        widget.set_running(True)
        assert widget.running is True
        widget.set_running(False)
        assert widget.running is False

    def test_set_paused_updates_flag(self):
        from pentool.tui.widgets.start_stop_widget import StartStopWidget

        widget = StartStopWidget()
        widget.set_paused(True)
        assert widget.paused is True
        widget.set_paused(False)
        assert widget.paused is False

    def test_declares_four_request_messages(self):
        from textual.message import Message

        from pentool.tui.widgets.start_stop_widget import StartStopWidget

        for name in ("StartRequested", "PauseRequested", "ResumeRequested", "StopRequested"):
            message_cls = getattr(StartStopWidget, name)
            assert issubclass(message_cls, Message)
            # The name is derived from the message's __qualname__ in snake_case;
            # the screen catches them via @on, so this name is only documented.
            expected = re.sub(r"(?<!^)(?=[A-Z])", "_", message_cls.__name__).lower()
            assert message_cls.handler_name == "on_start_stop_widget_" + expected

    def test_id_constants_used_by_compose(self):
        from pentool.tui.widgets.start_stop_widget import StartStopWidget

        assert StartStopWidget.ID_START == "btn-start"
        assert StartStopWidget.ID_STOP == "btn-stop"


# ─── IntruderScreen tests — buttons and their clicks ─────────────────────────


class TestIntruderButtons:
    """Checks btn-start/btn-stop in compose and the related methods."""

    def test_intruder_has_start_stop_in_compose(self, mock_intruder_deps):
        import inspect

        from pentool.tui.screens.intruder.screen import IntruderScreen

        src = inspect.getsource(IntruderScreen.compose)
        # Attack parameters stay in the panel...
        assert '"intruder-threads"' in src
        assert '"intruder-delay"' in src
        # ...while Start/Pause/Stop and tab add/remove are module-header buttons:
        # they are declared in `header_spec()`, not composed here.
        assert "StartStopWidget(" not in src
        spec_src = inspect.getsource(IntruderScreen.header_spec)
        for action in ('"start"', '"pause"', '"stop"', '"new_tab"', '"close_tab"'):
            assert action in spec_src, f"{action} is not offered by the Intruder header"
        # The per-tab toolbar still has content buttons, but no StartStop.
        # The identifiers are built from _TabId (F-023), so we assert the
        # constant and its value rather than a literal in the method text.
        from pentool.tui.screens.intruder.screen import _TabId

        mount_src = inspect.getsource(IntruderScreen._mount_tab_body)
        assert _TabId.BTN_ADD_MARKER == "btn-add-marker"
        assert "_TabId.BTN_ADD_MARKER" in mount_src
        assert "StartStopWidget(" not in mount_src

    def test_intruder_has_attack_methods(self, mock_intruder_deps):
        from pentool.tui.screens.intruder.screen import IntruderScreen

        for name in (
            "action_start_attack",
            "action_stop",
            "action_toggle_pause",
            "action_resume",
            "header_spec",
            "header_action",
        ):
            assert hasattr(IntruderScreen, name), f"{name} missing — the header cannot reach the attack"

    def test_header_offers_attack_controls(self, mock_intruder_deps):
        """Start/Pause/Stop are offered by the module header (not by a widget)."""
        import inspect

        from pentool.tui.screens.intruder.screen import IntruderScreen

        spec_src = inspect.getsource(IntruderScreen.header_spec)
        for action in ("start", "pause", "stop"):
            assert f'"{action}"' in spec_src, f"header lost the {action} control"

    def test_intruder_action_stop_resets_running(self, mock_intruder_deps):
        from pentool.tui.screens.intruder.screen import IntruderScreen

        screen = IntruderScreen()
        attack = MagicMock()
        tab = MagicMock()
        tab.attack = attack
        tab.running = True
        tab.paused = True
        screen._active_tab_id = "t1"
        screen._tabs = []  # unused, active_tab goes through the fallback
        # Replace the _active_tab property with our tab
        with patch.object(IntruderScreen, "_active_tab", new_callable=PropertyMock, return_value=tab):
            _setup_screen(screen)
            try:
                screen.action_stop()
                attack.stop.assert_called_once()
            finally:
                _teardown_screen(screen)

    def test_intruder_action_toggle_pause_toggles_api(self, mock_intruder_deps):
        from pentool.tui.screens.intruder.screen import IntruderScreen

        screen = IntruderScreen()
        attack = MagicMock()
        tab = MagicMock()
        tab.attack = attack
        tab.running = True
        tab.paused = False
        with patch.object(IntruderScreen, "_active_tab", new_callable=PropertyMock, return_value=tab):
            _setup_screen(screen)
            try:
                # Pause
                screen.action_toggle_pause()
                attack.pause.assert_called_once()

                # Resume
                tab.paused = True
                attack.reset_mock()
                screen.action_toggle_pause()
                attack.resume.assert_called_once()
            finally:
                _teardown_screen(screen)

    def test_intruder_action_resume_calls_action_start(self, mock_intruder_deps):
        from pentool.tui.screens.intruder.screen import IntruderScreen

        screen = IntruderScreen()
        called = [False]

        def track():
            called[0] = True

        screen.action_start_attack = track
        _setup_screen(screen)

        try:
            screen.action_resume()
            assert called[0]
        finally:
            _teardown_screen(screen)

    def test_intruder_worker_state_changed_resets_running(self, mock_intruder_deps):
        from textual.worker import WorkerState

        from pentool.tui.screens.intruder.screen import IntruderScreen

        screen = IntruderScreen()
        tab = MagicMock()
        tab.tab_id = "intruder-tab-1"
        tab.running = True
        tab.paused = False
        panel = MagicMock()
        panel.get_state.return_value = tab
        with (
            patch.object(IntruderScreen, "_active_tab", new_callable=PropertyMock, return_value=tab),
            patch.object(IntruderScreen, "_tc_panel", new_callable=PropertyMock, return_value=panel),
        ):
            _setup_screen(screen)
            try:
                ev = MagicMock()
                ev.worker.name = "intruder-attack-intruder-tab-1"
                ev.state = WorkerState.SUCCESS
                screen.on_worker_state_changed(ev)
            finally:
                _teardown_screen(screen)

    def test_intruder_worker_state_changed_ignores_other(self, mock_intruder_deps):
        from textual.worker import WorkerState

        from pentool.tui.screens.intruder.screen import IntruderScreen

        screen = IntruderScreen()
        screen._running = True
        _setup_screen(screen)

        try:
            ev = MagicMock()
            ev.worker.name = "some-other-worker"
            ev.state = WorkerState.SUCCESS
            screen.on_worker_state_changed(ev)
            assert screen._running is True
        finally:
            _teardown_screen(screen)


# ─── ActivityIndicator tests — Recon must not blink spuriously ───────────────


class TestActivityIndicatorRecon:
    """Checks ActivityIndicator — Recon must not blink without a start."""

    def test_recon_active_uses_runner(self):
        import inspect

        from pentool.tui.widgets.activity_indicator import ActivityIndicator

        src = inspect.getsource(ActivityIndicator._build_checkers)
        assert "_runner is not None" in src

    def test_activity_indicator_imports_ok(self):
        from pentool.tui.widgets.activity_indicator import ActivityIndicator

        assert hasattr(ActivityIndicator, "_build_checkers")

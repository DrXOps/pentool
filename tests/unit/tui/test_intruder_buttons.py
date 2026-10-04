"""Тесты для StartStopMixin и кнопок Start/Stop/Pause/Resume в IntruderScreen.

Проверяет:
- Наличие btn-start/btn-stop в compose
- Цикл Start→Pause→Resume→Stop
- ActivityIndicator не показывает Recon активным без запуска
"""

from __future__ import annotations

import pytest
from unittest.mock import MagicMock, patch

from textual.css.query import NoMatches


# ─── Хелперы ────────────────────────────────────────────────────────────────


@pytest.fixture
def mock_intruder_deps():
    """Мокаем тяжёлые зависимости IntruderScreen."""
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
    """Настраивает экран для unit-теста.

    - Устанавливает active_app ContextVar (чтобы app property работал)
    - Подменяет run_worker на MagicMock
    - Подменяет query_one на MagicMock (возвращает сам себя)
    - Добавляет .disabled = False на мок (для btn-stop)
    """
    from textual.app import active_app
    # Устанавливаем active_app ContextVar
    screen._active_app_token = active_app.set(_MOCK_APP)
    screen.run_worker = MagicMock()
    # Мок query_one — возвращает сам себя с любыми атрибутами
    mock_q = MagicMock()
    mock_q.disabled = False
    screen.query_one = MagicMock(return_value=mock_q)
    return screen


def _teardown_screen(screen):
    """Чистит ContextVar."""
    from textual.app import active_app
    token = getattr(screen, '_active_app_token', None)
    if token is not None:
        try:
            active_app.reset(token)
        except Exception:
            pass


# ─── Тесты StartStopMixin в изоляции ─────────────────────────────────────────


class TestStartStopMixin:
    """Проверка StartStopMixin как standalone-класса."""

    def test_mixin_has_required_attrs(self):
        from pentool.tui.widgets.start_stop_mixin import StartStopMixin
        mixin = StartStopMixin()
        assert mixin._running is False
        assert mixin._paused is False

    def test_mixin_raises_not_implemented(self):
        from pentool.tui.widgets.start_stop_mixin import StartStopMixin
        mixin = StartStopMixin()
        with pytest.raises(NotImplementedError):
            mixin.action_start()

    def test_mixin_action_stop_resets_flags(self):
        from pentool.tui.widgets.start_stop_mixin import StartStopMixin
        mixin = StartStopMixin()
        mixin._running = True
        mixin._paused = True
        mixin.action_stop()
        assert mixin._running is False
        assert mixin._paused is False

    def test_mixin_action_resume_calls_action_start(self):
        from pentool.tui.widgets.start_stop_mixin import StartStopMixin
        mixin = StartStopMixin()
        called = [False]
        def fake_start():
            called[0] = True
            raise NotImplementedError
        mixin.action_start = fake_start
        with pytest.raises(NotImplementedError):
            mixin.action_resume()
        assert called[0]

    def test_mixin_toggle_pause_when_not_running(self):
        from pentool.tui.widgets.start_stop_mixin import StartStopMixin
        mixin = StartStopMixin()
        mixin.action_toggle_pause()  # no-op потому что _running=False
        assert mixin._paused is False

    def test_mixin_on_btn_start_dispatches_by_state(self):
        from pentool.tui.widgets.start_stop_mixin import StartStopMixin
        mixin = StartStopMixin()
        calls = []
        mixin.action_start = lambda: calls.append("start")
        mixin.action_resume = lambda: calls.append("resume")
        mixin.action_toggle_pause = lambda: calls.append("toggle")

        mixin.on_btn_start(None)
        assert calls == ["start"]

        mixin._running = True
        mixin.on_btn_start(None)
        assert calls == ["start", "toggle"]

        mixin._paused = True
        mixin.on_btn_start(None)
        assert calls == ["start", "toggle", "resume"]


# ─── Тесты IntruderScreen — кнопки и их нажатия ──────────────────────────────


class TestIntruderButtons:
    """Проверка btn-start/btn-stop в compose и методов."""

    def test_intruder_has_start_stop_in_compose(self, mock_intruder_deps):
        from pentool.tui.screens.intruder.screen import IntruderScreen
        import inspect
        src = inspect.getsource(IntruderScreen.compose)
        assert '"▶ Start", "btn-start"' in src
        assert '"■ Stop"' in src and '"btn-stop"' in src

    def test_intruder_has_mixin_in_mro(self, mock_intruder_deps):
        from pentool.tui.screens.intruder.screen import IntruderScreen
        assert any(c.__name__ == "StartStopMixin"
                   for c in IntruderScreen.__mro__)

    def test_intruder_has_mixin_methods(self, mock_intruder_deps):
        from pentool.tui.screens.intruder.screen import IntruderScreen
        for name in ("action_start", "action_stop", "action_toggle_pause",
                     "action_resume", "_set_running_state"):
            assert hasattr(IntruderScreen, name)

    def test_intruder_action_start_sets_running(self, mock_intruder_deps):
        from pentool.tui.screens.intruder.screen import IntruderScreen
        screen = IntruderScreen()
        screen._api = MagicMock()
        screen._payloads = [["test"]]
        screen._attack_type = MagicMock()
        screen._get_processing_ops = MagicMock(return_value=[])
        screen._get_api = MagicMock(return_value=screen._api)
        screen._apply_license_limits = MagicMock()
        screen._clear_results = MagicMock()
        screen._payload_load_in_progress = False

        mock_textarea = MagicMock()
        mock_textarea.text = "GET /?§id§=1 HTTP/1.1\r\nHost: test.com\r\n\r\n"
        mock_input = MagicMock()
        mock_input.value = "10"
        mock_delay = MagicMock()
        mock_delay.value = "0"
        mock_chk = MagicMock()
        mock_chk.value = False

        def fake_query_one(selector, *args):
            m = {
                "#template-editor": mock_textarea,
                "#input-threads": mock_input,
                "#input-delay": mock_delay,
                "#chk-turbo": mock_chk,
            }
            if selector in m:
                return m[selector]
            raise NoMatches(selector)

        screen.query_one = fake_query_one
        _setup_screen(screen)

        try:
            screen.action_start()
            assert screen._running is True
        finally:
            _teardown_screen(screen)

    def test_intruder_action_stop_resets_running(self, mock_intruder_deps):
        from pentool.tui.screens.intruder.screen import IntruderScreen
        screen = IntruderScreen()
        mock_api = MagicMock()
        screen._api = mock_api
        screen._running = True
        screen._paused = True
        _setup_screen(screen)

        try:
            screen.action_stop()
            assert screen._running is False
            assert screen._paused is False
            mock_api.stop.assert_called_once()
        finally:
            _teardown_screen(screen)

    def test_intruder_action_toggle_pause_toggles_api(self, mock_intruder_deps):
        from pentool.tui.screens.intruder.screen import IntruderScreen
        screen = IntruderScreen()
        mock_api = MagicMock()
        screen._api = mock_api
        screen._running = True
        _setup_screen(screen)

        try:
            # Pause
            screen.action_toggle_pause()
            mock_api.pause.assert_called_once()
            assert screen._paused is True

            # Resume
            screen.action_toggle_pause()
            mock_api.resume.assert_called_once()
            assert screen._paused is False
        finally:
            _teardown_screen(screen)

    def test_intruder_action_resume_calls_action_start(self, mock_intruder_deps):
        from pentool.tui.screens.intruder.screen import IntruderScreen
        screen = IntruderScreen()
        called = [False]
        def track():
            called[0] = True
        screen.action_start = track
        _setup_screen(screen)

        try:
            screen.action_resume()
            assert called[0]
        finally:
            _teardown_screen(screen)

    def test_intruder_worker_state_changed_resets_running(self, mock_intruder_deps):
        from pentool.tui.screens.intruder.screen import IntruderScreen
        from textual.worker import WorkerState
        screen = IntruderScreen()
        screen._running = True
        _setup_screen(screen)

        try:
            set_called = [False]
            def track_set(running):
                set_called[0] = True
                screen._running = running
            screen._set_running_state = track_set

            ev = MagicMock()
            ev.worker.name = "intruder-attack"
            ev.state = WorkerState.SUCCESS

            screen.on_worker_state_changed(ev)
            assert set_called[0]
            assert screen._running is False
        finally:
            _teardown_screen(screen)

    def test_intruder_worker_state_changed_ignores_other(self, mock_intruder_deps):
        from pentool.tui.screens.intruder.screen import IntruderScreen
        from textual.worker import WorkerState
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


# ─── Тесты ActivityIndicator — Recon не должен ложно мигать ──────────────────


class TestActivityIndicatorRecon:
    """Проверка ActivityIndicator — Recon не должен мигать без запуска."""

    def test_recon_active_uses_runner(self):
        from pentool.tui.widgets.activity_indicator import ActivityIndicator
        import inspect
        src = inspect.getsource(ActivityIndicator._build_checkers)
        assert "_runner is not None" in src

    def test_activity_indicator_imports_ok(self):
        from pentool.tui.widgets.activity_indicator import ActivityIndicator
        assert hasattr(ActivityIndicator, "_build_checkers")
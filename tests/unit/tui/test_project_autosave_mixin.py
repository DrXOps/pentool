"""Unit tests for ProjectAutoSaveMixin (Этап 5.1)."""

from __future__ import annotations

import types

from pentool.tui.mixins.project_autosave import ProjectAutoSaveMixin


class _FakeTimer:
    def __init__(self):
        self.paused = False
        self.stopped = False

    def pause(self):
        self.paused = True

    def stop(self):
        self.stopped = True


class _FakeApp(ProjectAutoSaveMixin):
    def __init__(self):
        self._auto_save_timer = None
        self._project_loaded = True
        self._project_path = "/tmp/foo.db"
        self._cfg = types.SimpleNamespace(auto_save_enabled=True, auto_save_interval=5, db_path="/tmp/fallback.db")
        self.intervals = []
        self.notified = []

    def set_interval(self, seconds, callback):
        self.intervals.append((seconds, callback))
        return _FakeTimer()

    def notify(self, message, *, timeout=None, **kw):
        self.notified.append((message, timeout))


class TestSetupAutoSave:
    def test_disabled_stops_timer_and_clears(self):
        app = _FakeApp()
        t = _FakeTimer()
        app._auto_save_timer = t
        app._cfg.auto_save_enabled = False
        app._setup_auto_save()
        assert t.stopped is True
        assert app._auto_save_timer is None
        assert app.intervals == []

    def test_enabled_schedules_interval(self):
        app = _FakeApp()
        app._setup_auto_save()
        assert len(app.intervals) == 1
        seconds, cb = app.intervals[0]
        # 5 min → 300 s
        assert seconds == 300
        assert cb.__name__ == "_auto_save_tick"

    def test_interval_clamped_at_1_min(self):
        app = _FakeApp()
        app._cfg.auto_save_interval = 0
        app._setup_auto_save()
        assert app.intervals[0][0] == 60

    def test_reschedule_stops_old_timer(self):
        app = _FakeApp()
        t1 = _FakeTimer()
        app._auto_save_timer = t1
        app._setup_auto_save()
        assert t1.stopped is True
        assert app._auto_save_timer is not None


class TestAutoSaveTick:
    def test_not_loaded_is_noop(self):
        app = _FakeApp()
        app._project_loaded = False
        app._auto_save_tick()
        assert app.notified == []

    def test_no_path_is_noop(self):
        app = _FakeApp()
        app._project_path = None
        app._cfg.db_path = ""
        app._auto_save_tick()
        assert app.notified == []

    def test_tick_notifies(self):
        app = _FakeApp()
        app._auto_save_tick()
        assert len(app.notified) == 1
        msg, timeout = app.notified[0]
        assert "foo.db" in msg
        assert timeout == 2

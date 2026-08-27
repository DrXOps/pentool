"""Unit tests for NotificationsMixin (Этап 5.1)."""

from __future__ import annotations

import types

import pytest

from pentool.tui.mixins.notifications import NotificationsMixin


class _FakeBase:
    """Provides the `notify` the mixin calls via super()."""

    def __init__(self):
        self.super_notified = []

    def notify(self, message, **kwargs):
        self.super_notified.append((message, kwargs))


class _FakeApp(NotificationsMixin, _FakeBase):
    def __init__(self):
        super().__init__()
        self._cfg = types.SimpleNamespace(notifications_sound_enabled=False)
        self.timers = []

    def set_timer(self, delay, callback):
        self.timers.append((delay, callback))

    def query_one(self, selector, cls=None):
        raise Exception("unmounted")

    def _refresh_notifications(self):
        # Textual App provides this; fake exposes a no-op for the scheduled cb.
        return None


class TestNotificationsMixin:
    def test_notify_delegates_to_super(self):
        app = _FakeApp()
        app.notify("hello", severity="success", timeout=2.0)
        assert app.super_notified, "did not call super().notify"
        msg, kwargs = app.super_notified[0]
        assert msg == "hello"
        assert kwargs["severity"] == "success"
        assert kwargs["timeout"] == 2.0

    def test_notify_schedules_refresh(self):
        app = _FakeApp()
        app.notify("with timeout", timeout=3.0)
        # scheduled a refresh ~ timeout+0.5
        assert app.timers, "expected a _refresh_notifications timer"
        delay, cb = app.timers[0]
        assert delay == pytest.approx(3.5)

    def test_flash_swallows_unmounted(self):
        app = _FakeApp()
        # query_one raises (unmounted) -> flash no-ops, does not raise.
        app.flash("x")  # should not raise

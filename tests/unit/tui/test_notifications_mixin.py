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

    # ── "failed notification" regression guards ──────────────────────────────
    # notify() is called from many contexts (proxy threads, timers, near
    # teardown). It must NEVER raise — a raised notify surfaces to the user as
    # an error toast / "failed notification" and can take down the action that
    # triggered it.

    def test_notify_does_not_raise_when_set_timer_missing(self):
        """Host without set_timer (e.g. non-App, or winding down) -> no raise."""
        app = _FakeApp()
        app.set_timer = None  # type: ignore[assignment]
        app.notify("x", timeout=2.0)  # should not raise

    def test_notify_does_not_raise_when_refresh_missing(self):
        """Host without _refresh_notifications -> timer scheduling skipped, no raise."""
        # A host that does NOT define _refresh_notifications (e.g. a non-App
        # object, or a class that dropped it). notify must not blow up.
        class _NoRefresh(_FakeApp):
            _refresh_notifications = None  # unavailable

        app = _NoRefresh()
        app.notify("x", timeout=2.0)  # should not raise
        assert app.super_notified, "super().notify still called"

    def test_notify_does_not_raise_when_sound_missing(self):
        """_cfg without notifications_sound_enabled -> sound branch skipped."""
        app = _FakeApp()
        app._cfg = types.SimpleNamespace()  # no notifications_sound_enabled
        app.notify("x")  # should not raise
        assert app.super_notified

    def test_notify_sound_failure_is_swallowed(self):
        """play_notification_sound raising must not break notify."""
        import unittest.mock as mock

        app = _FakeApp()
        app._cfg = types.SimpleNamespace(notifications_sound_enabled=True)
        # notify imports play_notification_sound from pentool.core.notification_sound
        # at call time; patch it there so the sound branch raises.
        with mock.patch(
            "pentool.core.notification_sound.play_notification_sound",
            side_effect=RuntimeError("boom"),
        ):
            app.notify("x")  # should not raise
        assert app.super_notified

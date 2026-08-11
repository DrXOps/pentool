"""E2E: NotificationCenter — app.notify2() toast stack."""
from __future__ import annotations

import pytest

from pentool.tui.app import PentoolApp
from pentool.tui.widgets.notification_center import (
    MAX_VISIBLE_TOASTS,
    NotificationCenter,
    NotificationToast,
)


@pytest.mark.e2e
class TestNotificationCenter:

    async def test_notify2_shows_toast(self) -> None:
        """app.notify2(...) mounts a NotificationToast in the center."""
        app = PentoolApp()
        app._skip_project_guard = True
        async with app.run_test(size=(120, 30)) as pilot:
            await pilot.pause()
            app.notify2("Attack finished: 42 requests", severity="success", sound=False)
            await pilot.pause()

            toasts = app.query(NotificationToast)
            assert len(toasts) == 1
            assert "-success" in toasts[0].classes

    async def test_notify2_severities_style_correctly(self) -> None:
        """Each severity maps to its own CSS class on the toast."""
        app = PentoolApp()
        app._skip_project_guard = True
        async with app.run_test(size=(120, 30)) as pilot:
            await pilot.pause()
            for severity in ("information", "warning", "error", "critical"):
                center = app.query_one("#notification-center", NotificationCenter)
                for child in list(center.children):
                    child.remove()
                await pilot.pause()
                app.notify2(f"{severity} message", severity=severity, sound=False)
                await pilot.pause()
                toasts = app.query(NotificationToast)
                assert len(toasts) == 1
                assert f"-{severity}" in toasts[0].classes

    async def test_notify2_caps_visible_toasts(self) -> None:
        """Pushing more than MAX_VISIBLE_TOASTS drops the oldest."""
        app = PentoolApp()
        app._skip_project_guard = True
        async with app.run_test(size=(120, 30)) as pilot:
            await pilot.pause()
            for i in range(MAX_VISIBLE_TOASTS + 3):
                app.notify2(f"msg {i}", severity="information", timeout=None, sound=False)
                await pilot.pause()

            toasts = app.query(NotificationToast)
            assert len(toasts) <= MAX_VISIBLE_TOASTS

    async def test_toast_close_button_dismisses(self) -> None:
        """Clicking the close button removes the toast."""
        app = PentoolApp()
        app._skip_project_guard = True
        async with app.run_test(size=(120, 30)) as pilot:
            await pilot.pause()
            app.notify2("Dismiss me", severity="information", timeout=None, sound=False)
            await pilot.pause()

            toasts = app.query(NotificationToast)
            assert len(toasts) == 1
            toasts[0].remove()
            await pilot.pause()

            toasts = app.query(NotificationToast)
            assert len(toasts) == 0

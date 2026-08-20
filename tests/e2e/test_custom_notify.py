"""E2E: app.notify() uses Textual's built-in toast rack (no dark band).

Notifications route through Textual's own ToastRack (not a custom docked
widget), so they render bottom-right without reserving a zone — i.e. no dark
band. These tests assert the toast actually appears (mounted + laid out with
height) and carries the severity class.
"""
from __future__ import annotations

import pytest
from pytest import MonkeyPatch

from textual.widgets._toast import Toast

from pentool.tui.app import PentoolApp


def _no_terminal_warning(monkeypatch: MonkeyPatch) -> None:
    """Stop the app from firing an auto-notify on startup (headless terms
    can emit a warning that would route through notify() too, adding a
    spurious pre-existing toast to these checks)."""
    monkeypatch.setattr(
        "pentool.utils.terminal_check.get_terminal_warning", lambda: None
    )


async def _assert_toast_visible(pilot, toast: Toast) -> None:
    """Assert the toast is actually laid out (has height), not just in DOM."""
    await pilot.pause(0.2)
    assert toast.is_mounted
    assert toast.display
    # A laid-out toast has a non-zero region on screen.
    assert toast.region.height > 0, "toast has no layout height (not laid out)"


@pytest.mark.e2e
class TestBuiltinToast:

    async def test_notify_shows_toast(self, monkeypatch) -> None:
        """app.notify(...) mounts a Textual Toast."""
        _no_terminal_warning(monkeypatch)
        app = PentoolApp()
        app._skip_project_guard = True
        async with app.run_test(size=(120, 30), notifications=True) as pilot:
            await pilot.pause()
            app.notify("Attack finished: 42 requests", severity="success")
            await pilot.pause(0.2)

            toasts = app.query(Toast)
            assert len(toasts) >= 1
            assert "-success" in toasts[-1].classes
            await _assert_toast_visible(pilot, toasts[-1])

    async def test_notify_severities_style_correctly(self, monkeypatch) -> None:
        """Each severity maps to its own CSS class on the toast."""
        _no_terminal_warning(monkeypatch)
        app = PentoolApp()
        app._skip_project_guard = True
        async with app.run_test(size=(120, 30), notifications=True) as pilot:
            await pilot.pause()
            for severity in ("information", "warning", "error", "critical"):
                app.notify(f"{severity} message", severity=severity)
                await pilot.pause(0.2)
                toasts = app.query(Toast)
                assert len(toasts) >= 1
                assert f"-{severity}" in toasts[-1].classes
                await _assert_toast_visible(pilot, toasts[-1])

    async def test_app_notify_does_not_leave_dock_band(self, monkeypatch) -> None:
        """The rack reserves no zone: layout height is not stolen from the app.

        With the old docked rack the current screen lost rows at the bottom.
        Using Textual's built-in rack, notify() must not shrink the dashboard
        screen region. We assert the main content size stays full-height.
        """
        _no_terminal_warning(monkeypatch)
        app = PentoolApp()
        app._skip_project_guard = True
        async with app.run_test(size=(120, 30), notifications=True) as pilot:
            await pilot.pause()
            content_switcher = app.query_one("#screen-dashboard")
            before = content_switcher.region
            app.notify("Some status", severity="information")
            await pilot.pause(0.3)
            after = content_switcher.region
            # Dashboard must not be vertically squashed by the toast.
            assert after.height >= before.height

"""NotificationCenter — ICQ-style stacked toast notifications.

Independent of the existing `app.flash()` (single-line tooltip2 in the
module bar) and the standard Textual `app.notify()` toast system — this is
a purpose-built stack of up to a few cards in the corner of the screen,
each styled by severity, with an optional short sound (see
pentool.core.notification_sound) and a manual close button, on top of
per-severity auto-dismiss timers.

Usage:
    app.notify2("Attack finished: 120 requests", severity="success")
    app.notify2("Proxy disconnected", severity="error", title="Proxy")
"""

from __future__ import annotations

from pathlib import Path

from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.widget import Widget
from textual.widgets import Static

from pentool.core.logging import get_logger

_CSS = (Path(__file__).parent / "notification_center.tcss").read_text(encoding="utf-8")

logger = get_logger(__name__)

# Severity levels, ordered least → most urgent. Kept as plain strings (not
# an Enum) so callers can keep passing "information"/"warning"/etc. exactly
# like the existing app.flash()/app.notify() calls — no migration required
# for existing call sites, this is purely additive.
SEVERITIES = ("information", "success", "warning", "error", "critical")

# Auto-dismiss timeout per severity, in seconds. None = stays until closed
# manually (critical alerts shouldn't vanish on their own).
_DEFAULT_TIMEOUTS: dict[str, float | None] = {
    "information": 2.5,
    "success":     3.0,
    "warning":     4.0,
    "error":       6.0,
    "critical":    None,
}

_ICONS: dict[str, str] = {
    "information": "ℹ",
    "success":     "✓",
    "warning":     "⚠",
    "error":       "✖",
    "critical":    "‼",
}

# Cap on simultaneously visible toasts — oldest is dropped when exceeded,
# matching the "stack of a few cards" ICQ look rather than an unbounded list.
MAX_VISIBLE_TOASTS = 4


class NotificationToast(Widget):
    """A single dismissible notification card."""

    def __init__(self, message: str, severity: str, title: str | None = None, **kwargs) -> None:
        super().__init__(**kwargs)
        self._message = message
        self._severity = severity if severity in SEVERITIES else "information"
        self._title = title
        self.add_class(f"-{self._severity}")

    def compose(self) -> ComposeResult:
        icon = _ICONS.get(self._severity, "ℹ")
        title_text = self._title or self._severity.capitalize()
        with Horizontal():
            yield Static(f"{icon} {title_text}", id="toast-title", markup=False)
            yield Static("✕", id="toast-close")
        yield Static(self._message, id="toast-body", markup=False)

    def on_click(self, event) -> None:
        try:
            widget = event.widget if hasattr(event, "widget") else None
        except Exception:
            widget = None
        if widget is not None and getattr(widget, "id", None) == "toast-close":
            self.remove()
            return
        # Clicking anywhere else on the card also dismisses it — matches
        # the ICQ-style "click to acknowledge" toast behavior.
        self.remove()


class NotificationCenter(Widget):
    """Stack of NotificationToast cards, docked to the top-right corner."""

    DEFAULT_CSS = _CSS

    def push(
        self,
        message: str,
        severity: str = "information",
        title: str | None = None,
        timeout: float | None = None,
    ) -> None:
        """Show a new toast. Oldest toast is dropped if the stack is full."""
        try:
            existing = list(self.children)
            if len(existing) >= MAX_VISIBLE_TOASTS:
                existing[0].remove()

            toast = NotificationToast(message, severity, title=title)
            self.mount(toast)

            effective_timeout = timeout if timeout is not None else _DEFAULT_TIMEOUTS.get(severity, 2.5)
            if effective_timeout is not None:
                self.set_timer(effective_timeout, lambda: self._dismiss(toast))
        except Exception as exc:
            logger.debug("NotificationCenter.push: %s", exc)

    def _dismiss(self, toast: NotificationToast) -> None:
        try:
            if toast.is_mounted:
                toast.remove()
        except Exception:
            pass

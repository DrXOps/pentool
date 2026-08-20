"""CustomNotify — ICQ-style stacked toast notifications.

The single, standard notification system for the app. All user-facing
fire-and-forget messages (whether the old `app.notify()` toast or the
lightweight `flash()` tooltip) are routed through this so the whole app
shares one look: a stack of up to a few styled cards in the lower-right
corner above the Footer, each by severity, optional sound (see
pentool.core.notification_sound) and a manual close button, on top of
per-severity auto-dismiss timers.

Usage:
    app.customnotify("Attack finished: 120 requests", severity="success")
    app.customnotify("Proxy disconnected", severity="error", title="Proxy")
"""

from __future__ import annotations

from pathlib import Path

from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.widget import Widget
from textual.widgets import Static

from pentool.core.logging import get_logger

_CSS = (Path(__file__).parent / "custom_notify.tcss").read_text(encoding="utf-8")

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


class CustomNotifyCard(Widget):
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

    def on_mount(self) -> None:
        """Animate the card in so it doesn't just pop into the layout.

        The zone lives in the real layout (above the StatusBar), so we can
        animate it like any normal widget — fade in from transparent and
        slide up into place.

        The animation is cosmetic: a fallback timer forces the final styles
        even if the animation never runs (e.g. when mounted from a background
        call or on an overlay-adjacent frame), so a card is never left stuck
        at opacity:0 — invisible but still mounted, which is how it used to
        fail with e2e green but nothing visible at runtime.
        """
        try:
            self.styles.opacity = 0.0
            self.styles.offset_y = 2
            self.animate(
                "styles.opacity",
                1.0,
                duration=0.25,
            )
            self.animate(
                "styles.offset_y",
                0.0,
                duration=0.25,
            )
            # Force the final state in case the animations above never run.
            self.set_timer(0.4, self._force_visible)
        except Exception:
            # Animation is cosmetic — never break the notification itself.
            self._force_visible()

    def _force_visible(self) -> None:
        """Ensure the card reaches its visible final state, no matter what."""
        try:
            self.styles.opacity = 1.0
            self.styles.offset_y = 0.0
        except Exception:
            pass

    def on_click(self, event) -> None:
        try:
            widget = event.widget if hasattr(event, "widget") else None
        except Exception:
            widget = None
        if widget is not None and getattr(widget, "id", None) == "toast-close":
            self.remove()
            self._notify_parent_refresh()
            return
        # Clicking anywhere else on the card also dismisses it — matches
        # the ICQ-style "click to acknowledge" toast behavior.
        self.remove()
        self._notify_parent_refresh()

    def _notify_parent_refresh(self) -> None:
        """Tell the rack to re-evaluate visibility after a card self-removes."""
        parent = self.parent
        if isinstance(parent, CustomNotify):
            parent._refresh_display()


class CustomNotify(Widget):
    """Stack of CustomNotifyCard cards, shown above the Footer (right)."""

    DEFAULT_CSS = _CSS

    def show(
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
                self._refresh_display()

            toast = CustomNotifyCard(message, severity, title=title)
            self.mount(toast)
            self.display = True  # rack paints only while it holds a card

            effective_timeout = timeout if timeout is not None else _DEFAULT_TIMEOUTS.get(severity, 2.5)
            if effective_timeout is not None:
                self.set_timer(effective_timeout, lambda: self._dismiss(toast))
        except Exception as exc:
            logger.debug("CustomNotify.show: %s", exc)

    def _dismiss(self, toast: CustomNotifyCard) -> None:
        """Remove a toast and hide the rack when none are left."""
        try:
            if toast.is_mounted:
                toast.remove()
            self._refresh_display()
        except Exception:
            pass

    def _refresh_display(self) -> None:
        """Hide the rack once the last card is gone so an empty container
        paints and reserves nothing (mirrors Textual's ToastRack)."""
        try:
            self.display = bool(self.children)
        except Exception:
            pass

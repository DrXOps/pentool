"""One way for a screen to tell the user something.

Three mechanisms had grown side by side: `self.app.notify(...)` (used directly in screens),
`self._notify(...)` (a thin wrapper in one screen) and `ModuleScreen.notify_to_user(...)`.
They differ in defaults and in how they behave when the app is not attached (tests), so the same
message behaved differently depending on which copy the author reached for.
"""

from __future__ import annotations

from typing import Any

from pentool.core.logging import get_logger

logger = get_logger(__name__)


class NotifyMixin:
    """`notify_user()` — the only supported way to raise a toast from a screen."""

    def notify_user(
        self,
        message: str,
        *,
        severity: str = "information",
        timeout: float | None = 3,
        title: str | None = None,
    ) -> None:
        """Show a toast; never raise.

        A screen can be composed without an app (unit tests, previews), and a notification is
        never worth an exception in the middle of a handler.
        """
        app: Any = getattr(self, "app", None)
        notify = getattr(app, "notify", None)
        if notify is None:
            logger.debug("notify: no app attached, message dropped: %s", message)
            return
        try:
            notify(message, severity=severity, timeout=timeout, title=title)
        except Exception:
            # A broken toast must not break the action that produced it.
            logger.warning("notify: message not shown: %s", message, exc_info=True)

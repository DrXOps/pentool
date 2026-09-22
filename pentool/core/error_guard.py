"""Centralised error handling: log + notify in one call.

Usage::

    from pentool.core.error_guard import err
    err(exc, "Context message", self)  # logs + notify
"""

from __future__ import annotations

import logging
import traceback
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from textual.widget import Widget

logger = logging.getLogger("pentool.error")


def err(
    exception: Exception,
    context: str = "",
    widget: Any = None,
    severity: str = "error",
) -> None:
    """Log an exception and show an error notification.

    Args:
        exception: the caught exception.
        context: short human-readable description (e.g. "Save failed").
        widget: any Textual Widget that has ``self.app.notify`` — when passed,
            also shows a TUI notification.
        severity: notification severity (default "error").
    """
    logger.error(
        "%s: %s\n%s",
        context or type(exception).__name__,
        exception,
        "".join(traceback.format_exception(type(exception), exception, exception.__traceback__)),
    )
    if widget is not None:
        try:
            widget.app.notify(  # type: ignore[union-attr]
                f"{context}: {exception}" if context else f"Error: {exception}",
                severity=severity,
                timeout=4,
            )
        except Exception:
            pass  # silently ignore notify failures (during shutdown etc.)


__all__ = ["err"]
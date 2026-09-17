"""Safe query_one helper — убирает повторяющийся try/except/log.

Паттерн, повторяющийся ~40+ раз по коду::

    try:
        screen = self.query_one(SELECTOR, SomeScreen)
        screen.do_something()
    except Exception as e:
        logger.debug("... %s", e)

Заменяется на::

    safe_call(self, SELECTOR, SomeScreen, lambda s: s.do_something(), "context")
"""

from __future__ import annotations

from typing import Any, Callable, TypeVar

from pentool.core.logging import get_logger

logger = get_logger(__name__)

T = TypeVar("T")


def safe_query_one(
    container: Any,
    selector: str,
    cls: type[T],
    action: Callable[[T], Any] | None = None,
    context: str = "",
    default: Any = None,
) -> Any:
    """Query a widget and optionally call a method on it, with safe logging.

    Args:
        container: The widget/app to query_one() on.
        selector: CSS selector (e.g. "#screen-proxy").
        cls: Expected widget class.
        action: Optional callable to invoke on the found widget.
        context: Label for debug logging (e.g. "proxy_screen.update_label").
        default: Value to return on failure.

    Returns:
        The widget if found (and action result if action was given), else default.
    """
    try:
        widget = container.query_one(selector, cls)
        if action is not None:
            return action(widget)
        return widget
    except Exception as _e:
        if context:
            logger.debug("safe_query_one(%s): %s", context, _e)
        return default


def safe_notify(
    app: Any,
    msg: str,
    severity: str = "warning",
    timeout: int = 4,
) -> None:
    """Safe notify wrapper — catches errors silently."""
    try:
        app.notify(msg, severity=severity, timeout=timeout)
    except Exception:
        pass
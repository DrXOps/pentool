"""BaseService — shared async/thread-safe event emit + log helpers."""

from __future__ import annotations

import asyncio
import logging
from typing import Callable

from pentool.core.event_bus import EventBus, get_event_bus
from pentool.core.logging import get_logger

logger = get_logger(__name__)


class BaseService:
    """Mixin providing thread-safe EventBus emit and TUI log callback.

    Subclasses must NOT re-implement _emit or _log — use this directly.

    Attributes:
        _bus:      EventBus instance (injected or default singleton).
        _tui_loop: The TUI asyncio event loop, used for emit_threadsafe.
        _on_log:   Optional callback(str) for forwarding log lines to TUI.
    """

    def __init__(
        self,
        event_bus: EventBus | None = None,
        tui_loop: asyncio.AbstractEventLoop | None = None,
        on_log: Callable[[str], None] | None = None,
    ) -> None:
        self._bus: EventBus = event_bus or get_event_bus()
        self._tui_loop: asyncio.AbstractEventLoop | None = tui_loop
        self._on_log: Callable[[str], None] | None = on_log

    def _emit(self, event: object) -> None:
        """Emit an event: thread-safe if tui_loop is set, direct otherwise.

        Args:
            event: Any event object recognised by EventBus.
        """
        try:
            if self._tui_loop and not self._tui_loop.is_closed():
                self._bus.emit_threadsafe(event, self._tui_loop)
            else:
                self._bus.emit(event)
        except Exception as exc:
            logger.debug("%s._emit error: %s", type(self).__name__, exc)

    def _log(self, msg: str) -> None:
        """Forward a Rich-markup message to the TUI log callback if set.

        Args:
            msg: Rich-markup string (e.g. "[cyan]INFO[/cyan] …").
        """
        if self._on_log:
            try:
                self._on_log(msg)
            except Exception:
                pass

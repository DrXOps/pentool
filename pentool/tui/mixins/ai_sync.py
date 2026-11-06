"""AiModeSyncMixin — subscribe a screen to the global AI master switch.

Every screen that shows AI-specific UI listens for ``AiModeChanged`` on the
process-wide :class:`~pentool.core.event_bus.EventBus`. Before this mixin each
screen opened a local ``def _on_ai_mode(...)`` closure and dropped it on the
floor: the bus kept the closure, the closure kept the screen, and nothing ever
unsubscribed (REPORT F-002). The handler is now stored on the instance and
removed in ``on_unmount``.

Hosts implement ``_sync_ai_ui()`` — that part stays per-screen because it is a
UI detail — and call ``_init_ai_sync()`` once from ``on_mount``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from pentool.core.event_bus import get_event_bus
from pentool.core.events import AiModeChanged
from pentool.core.logging import get_logger

if TYPE_CHECKING:
    from typing import Callable

logger = get_logger(__name__)


class AiModeSyncMixin:
    """Keeps the widget in sync with ``Config.ai_enabled``."""

    _ai_handler: Callable[[AiModeChanged], None] | None = None

    def _init_ai_sync(self) -> None:
        """Subscribe to ``AiModeChanged`` (idempotent) and sync once."""
        if self._ai_handler is not None:
            return
        self._ai_handler = self._on_ai_mode_changed
        get_event_bus().subscribe(AiModeChanged, self._ai_handler)
        self._sync_ai_ui()

    def _on_ai_mode_changed(self, event: AiModeChanged) -> None:  # noqa: ARG002
        """Re-apply visibility on the UI thread, after the current refresh."""
        self.call_after_refresh(self._sync_ai_ui)

    def on_unmount(self) -> None:
        """Drop the subscription so a re-mounted screen does not double it."""
        handler = self._ai_handler
        if handler is None:
            return
        self._ai_handler = None
        get_event_bus().unsubscribe(AiModeChanged, handler)

    def _sync_ai_ui(self) -> None:  # pragma: no cover - overridden by hosts
        """Show/hide AI-specific widgets. Implemented by each host screen."""
        raise NotImplementedError

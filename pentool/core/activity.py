"""ActivityState — one place that knows what is running right now (T-030, part 1).

Background processes used to be discovered by polling: the status-bar strip re-read
`ProxyServer.is_running`, `ScannerScreen._tabs[*].scanning`, `IntruderScreen._attack_running`,
`ReconScreen._runner` and a Spider counter once a second, forever. That works, but it costs
a repaint every second, polls modules that are not mounted, and cannot tell "stopped" from
"could not read the state".

Here every producer reports the transition once (`activity.set("proxy", True)`) and
consumers subscribe. Polling stays as a slow fallback for state that has no event source
(AI-backend availability, config toggles).

The registry is deliberately framework-free: producers include plain classes, background
threads and the PRO package, none of which should import Textual to say "I am running".
"""

from __future__ import annotations

from pentool.core.event_bus import get_event_bus
from pentool.core.events import ActivityChanged
from pentool.core.logging import get_logger

logger = get_logger(__name__)

#: Modules tracked by the status strip. Kept as a tuple so a typo in `set()` is caught
#: instead of creating a phantom glyph nobody renders.
TRACKED_MODULES: tuple[str, ...] = ("proxy", "spider", "scanner", "intruder", "recon", "ai")


class ActivityState:
    """What is running now, fed by the modules themselves.

    A listener receives `(module, active)` only when a value actually changes, so a
    consumer can repaint without comparing state itself.
    """

    def __init__(self) -> None:
        self._active: dict[str, bool] = {module: False for module in TRACKED_MODULES}

    # ── producer API ──────────────────────────────────────────────────────

    def set(self, module: str, active: bool) -> None:
        """Record the state of *module* and emit `ActivityChanged` if it changed.

        Call it from the application's event-loop thread: the EventBus dispatches
        synchronously, and subscribers touch widgets. Producers on their own thread (the
        in-memory proxy loop) already hop over with `call_from_thread`.
        """
        if module not in self._active:
            logger.warning("activity: unknown module %r (tracked: %s)", module, ", ".join(TRACKED_MODULES))
            return
        active = bool(active)
        if self._active[module] == active:
            return
        self._active[module] = active
        try:
            get_event_bus().emit(ActivityChanged(source="activity", module=module, active=active))
        except Exception:  # noqa: BLE001 - a broken subscriber must not lose the state
            logger.exception("activity: publish failed for %s=%s", module, active)

    # ── consumer API ──────────────────────────────────────────────────────

    def snapshot(self) -> dict[str, bool]:
        """Copy of the whole state (safe to iterate while producers keep writing)."""
        return dict(self._active)

    def is_active(self, module: str) -> bool:
        return self._active.get(module, False)

    def any_active(self) -> bool:
        return any(self._active.values())

    def reset(self) -> None:
        """Back to "nothing runs" — used by tests and by a full app shutdown."""
        for module in TRACKED_MODULES:
            self.set(module, False)


_STATE = ActivityState()


def get_activity_state() -> ActivityState:
    """The process-wide registry."""
    return _STATE


def set_activity(module: str, active: bool) -> None:
    """Convenience wrapper for producers that only need the global instance."""
    _STATE.set(module, active)

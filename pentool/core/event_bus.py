"""Event Bus — internal application event bus."""

from __future__ import annotations

import asyncio
import threading
from collections import defaultdict, deque
from typing import Callable, TypeVar

from pentool.core.events import AppEvent
from pentool.core.logging import get_logger

logger = get_logger(__name__)

T = TypeVar("T", bound=AppEvent)


class EventBus:
    """Thread-safe event bus with history.

    Attributes:
        _subscribers:  Dict type -> list of handlers.
        _history:      Ring buffer of all emitted events.
        _lock:         RLock for thread-safe operations.
    """

    def __init__(self, max_history: int = 10_000) -> None:
        self._subscribers: dict[type, list[Callable]] = defaultdict(list)
        self._history: deque[AppEvent] = deque(maxlen=max_history)
        self._lock = threading.RLock()

    # ── subscribe / unsubscribe ────────────────────────────────────────────────

    def subscribe(self, event_type: type[T], handler: Callable[[T], None]) -> None:
        """Subscribe to events of the given type.

        Args:
            event_type: Event class (subclass of AppEvent).
            handler:    Handler function accepting an event instance.
        """
        with self._lock:
            if handler not in self._subscribers[event_type]:
                self._subscribers[event_type].append(handler)

    def unsubscribe(self, event_type: type, handler: Callable) -> None:
        """Unsubscribe from events.

        Safe on repeated calls — does not raise if the handler was not subscribed.
        """
        with self._lock:
            try:
                self._subscribers[event_type].remove(handler)
            except ValueError:
                pass

    def unsubscribe_all(self, handler: Callable) -> None:
        """Unsubscribe a handler from all event types at once."""
        with self._lock:
            for handlers in self._subscribers.values():
                try:
                    handlers.remove(handler)
                except ValueError:
                    pass

    # ── emit ──────────────────────────────────────────────────────────────────

    def emit(self, event: AppEvent) -> None:
        """Synchronous emit from the main thread.

        Calls all subscribers immediately (in the same thread).
        Saves the event to history.

        Args:
            event: Event instance (subclass of AppEvent).
        """
        with self._lock:
            self._history.append(event)
            handlers = list(self._subscribers.get(type(event), []))

        for handler in handlers:
            try:
                handler(event)
            except Exception as exc:
                logger.warning(
                    "EventBus: handler %s raised %s for event %s",
                    handler, exc, type(event).__name__,
                )

    def emit_threadsafe(
        self,
        event: AppEvent,
        loop: asyncio.AbstractEventLoop,
    ) -> None:
        """Thread-safe emit from a worker thread.

        Saves the event to history immediately (under lock),
        then schedules handler calls in the event loop via
        call_soon_threadsafe.

        Args:
            event: Event instance.
            loop:  Event loop of the main thread (app._loop).
        """
        with self._lock:
            self._history.append(event)
            handlers = list(self._subscribers.get(type(event), []))

        if not handlers:
            return

        def _dispatch() -> None:
            for handler in handlers:
                try:
                    handler(event)
                except Exception as exc:
                    logger.warning(
                        "EventBus: threadsafe handler %s raised %s for %s",
                        handler, exc, type(event).__name__,
                    )

        try:
            loop.call_soon_threadsafe(_dispatch)
        except RuntimeError:
            # loop is closed — application is shutting down
            pass

    # ── history / replay ──────────────────────────────────────────────────────

    def get_history(
        self,
        event_type: type | None = None,
        limit: int = 0,
    ) -> list[AppEvent]:
        with self._lock:
            events = list(self._history)

        if event_type is not None:
            events = [e for e in events if isinstance(e, event_type)]

        if limit > 0:
            events = events[-limit:]

        return events

    def replay(
        self,
        handler: Callable,
        event_type: type,
        limit: int = 0,
    ) -> None:
        """Replay event history for a new subscriber.

        Calls handler for each saved event of the given type.
        Useful when initializing a screen that connected late
        (e.g. Dashboard after a scan has started).

        Args:
            handler:    Handler function.
            event_type: Event type to replay.
            limit:      Max events (0 = all).
        """
        events = self.get_history(event_type=event_type, limit=limit)
        for event in events:
            try:
                handler(event)
            except Exception as exc:
                logger.warning(
                    "EventBus.replay: handler %s raised %s", handler, exc
                )

    def clear_history(self) -> None:
        with self._lock:
            self._history.clear()

    # ── stats ─────────────────────────────────────────────────────────────────

    def stats(self) -> dict[str, int]:
        """Stats for debugging."""
        with self._lock:
            return {
                "history_size":    len(self._history),
                "subscriber_types": len(self._subscribers),
                "total_handlers":  sum(len(v) for v in self._subscribers.values()),
            }


# ── Global singleton ────────────────────────────────────────────────────────────

_bus: EventBus | None = None
_bus_lock = threading.Lock()


def get_event_bus() -> EventBus:
    global _bus
    if _bus is None:
        with _bus_lock:
            if _bus is None:
                _bus = EventBus()
    return _bus


def reset_event_bus() -> None:
    """Reset global singleton (tests only)."""
    global _bus
    with _bus_lock:
        _bus = None

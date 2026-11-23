"""Integration tests: EventBus — pub/sub, history, threadsafe emit."""

from __future__ import annotations

import asyncio
import threading

import pytest

from pentool.core.event_bus import EventBus, get_event_bus, reset_event_bus
from pentool.core.events import (
    IntruderFinished,
    ProxyRequestCaptured,
    ScanFinished,
    ScanStarted,
)

# ── TestEventBus ──────────────────────────────────────────────────────────────


@pytest.mark.integration
class TestEventBus:
    def test_subscribe_and_emit(self) -> None:
        """subscribe + emit → handler called once."""
        bus = EventBus()
        calls = []
        bus.subscribe(ScanStarted, lambda e: calls.append(e))
        bus.emit(ScanStarted())
        assert len(calls) == 1

    def test_emit_passes_event_instance(self) -> None:
        """handler receives the same event object."""
        bus = EventBus()
        received = []
        bus.subscribe(ScanStarted, lambda e: received.append(e))
        event = ScanStarted(targets=["http://example.com"])
        bus.emit(event)
        assert received[0] is event

    def test_unsubscribe_stops_calls(self) -> None:
        """unsubscribe → emit → handler NOT called."""
        bus = EventBus()
        calls = []

        def handler(e):
            calls.append(e)

        bus.subscribe(ScanStarted, handler)
        bus.unsubscribe(ScanStarted, handler)
        bus.emit(ScanStarted())
        assert len(calls) == 0

    def test_unsubscribe_all(self) -> None:
        """subscribe to 2 event types → unsubscribe_all → emit both → 0 calls."""
        bus = EventBus()
        calls = []

        def handler(e):
            calls.append(e)

        bus.subscribe(ScanStarted, handler)
        bus.subscribe(ScanFinished, handler)
        bus.unsubscribe_all(handler)
        bus.emit(ScanStarted())
        bus.emit(ScanFinished())
        assert len(calls) == 0

    def test_multiple_subscribers_same_type(self) -> None:
        """2 handlers for one event type → both called."""
        bus = EventBus()
        calls_a = []
        calls_b = []
        bus.subscribe(ScanStarted, lambda e: calls_a.append(e))
        bus.subscribe(ScanStarted, lambda e: calls_b.append(e))
        bus.emit(ScanStarted())
        assert len(calls_a) == 1
        assert len(calls_b) == 1

    def test_get_history_returns_emitted(self) -> None:
        """emit 3 events → get_history() len == 3."""
        bus = EventBus()
        bus.emit(ScanStarted())
        bus.emit(ScanFinished())
        bus.emit(ProxyRequestCaptured())
        history = bus.get_history()
        assert len(history) == 3

    def test_get_history_filter_by_type(self) -> None:
        """emit ScanStarted + ScanFinished → get_history(ScanStarted) len == 1."""
        bus = EventBus()
        bus.emit(ScanStarted())
        bus.emit(ScanFinished())
        filtered = bus.get_history(ScanStarted)
        assert len(filtered) == 1
        assert isinstance(filtered[0], ScanStarted)

    def test_replay_calls_handler_for_history(self) -> None:
        """emit 2 events → replay → handler called twice."""
        bus = EventBus()
        bus.emit(ScanStarted())
        bus.emit(ScanStarted())
        calls = []
        bus.replay(lambda e: calls.append(e), ScanStarted)
        assert len(calls) == 2

    def test_clear_history(self) -> None:
        """emit 3 → clear_history() → get_history() is empty."""
        bus = EventBus()
        bus.emit(ScanStarted())
        bus.emit(ScanFinished())
        bus.emit(IntruderFinished())
        bus.clear_history()
        assert bus.get_history() == []

    def test_stats_returns_dict(self) -> None:
        """stats() → dict with keys history_size, subscriber_types, total_handlers."""
        bus = EventBus()
        bus.subscribe(ScanStarted, lambda e: None)
        bus.emit(ScanStarted())
        s = bus.stats()
        assert isinstance(s, dict)
        assert "history_size" in s
        assert "subscriber_types" in s
        assert "total_handlers" in s
        assert s["history_size"] == 1
        assert s["total_handlers"] >= 1

    def test_emit_threadsafe_from_thread(self) -> None:
        """emit_threadsafe(event, loop) from a threading.Thread → event in history."""
        bus = EventBus()
        loop = asyncio.new_event_loop()

        event = ScanStarted(targets=["http://example.com"])

        def worker():
            bus.emit_threadsafe(event, loop)

        t = threading.Thread(target=worker)
        t.start()
        t.join(timeout=2)

        # emit_threadsafe stores the event in history immediately (under lock)
        history = bus.get_history()
        assert len(history) == 1
        assert history[0] is event

        loop.close()


# ── TestEventBusGlobal ────────────────────────────────────────────────────────


@pytest.mark.integration
class TestEventBusGlobal:
    def setup_method(self):
        """Reset the global singleton before each test."""
        reset_event_bus()

    def teardown_method(self):
        """Reset the global singleton after each test."""
        reset_event_bus()

    def test_singleton_same_object(self) -> None:
        """get_event_bus() is get_event_bus() — the same object."""
        bus1 = get_event_bus()
        bus2 = get_event_bus()
        assert bus1 is bus2

    def test_reset_creates_new(self) -> None:
        """reset_event_bus() → get_event_bus() returns a new object."""
        bus1 = get_event_bus()
        reset_event_bus()
        bus2 = get_event_bus()
        assert bus1 is not bus2

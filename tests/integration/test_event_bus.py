"""Integration tests: EventBus — pub/sub, history, threadsafe emit."""
from __future__ import annotations

import asyncio
import threading
import pytest

from pentool.core.event_bus import EventBus, get_event_bus, reset_event_bus
from pentool.core.events import (
    ScanStarted, ScanFinished, FindingDiscovered,
    ProxyRequestCaptured, IntruderFinished,
)


# ── TestEventBus ──────────────────────────────────────────────────────────────

@pytest.mark.integration
class TestEventBus:

    def test_subscribe_and_emit(self) -> None:
        """subscribe + emit → handler вызван 1 раз."""
        bus = EventBus()
        calls = []
        bus.subscribe(ScanStarted, lambda e: calls.append(e))
        bus.emit(ScanStarted())
        assert len(calls) == 1

    def test_emit_passes_event_instance(self) -> None:
        """handler получает тот же объект события."""
        bus = EventBus()
        received = []
        bus.subscribe(ScanStarted, lambda e: received.append(e))
        event = ScanStarted(targets=["http://example.com"])
        bus.emit(event)
        assert received[0] is event

    def test_unsubscribe_stops_calls(self) -> None:
        """unsubscribe → emit → handler НЕ вызван."""
        bus = EventBus()
        calls = []
        handler = lambda e: calls.append(e)
        bus.subscribe(ScanStarted, handler)
        bus.unsubscribe(ScanStarted, handler)
        bus.emit(ScanStarted())
        assert len(calls) == 0

    def test_unsubscribe_all(self) -> None:
        """подписаться на 2 типа → unsubscribe_all → emit оба → 0 вызовов."""
        bus = EventBus()
        calls = []
        handler = lambda e: calls.append(e)
        bus.subscribe(ScanStarted, handler)
        bus.subscribe(ScanFinished, handler)
        bus.unsubscribe_all(handler)
        bus.emit(ScanStarted())
        bus.emit(ScanFinished())
        assert len(calls) == 0

    def test_multiple_subscribers_same_type(self) -> None:
        """2 handler-а для одного типа → оба вызваны."""
        bus = EventBus()
        calls_a = []
        calls_b = []
        bus.subscribe(ScanStarted, lambda e: calls_a.append(e))
        bus.subscribe(ScanStarted, lambda e: calls_b.append(e))
        bus.emit(ScanStarted())
        assert len(calls_a) == 1
        assert len(calls_b) == 1

    def test_get_history_returns_emitted(self) -> None:
        """emit 3 события → get_history() len == 3."""
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
        """emit 2 события → replay → handler вызван 2 раза."""
        bus = EventBus()
        bus.emit(ScanStarted())
        bus.emit(ScanStarted())
        calls = []
        bus.replay(lambda e: calls.append(e), ScanStarted)
        assert len(calls) == 2

    def test_clear_history(self) -> None:
        """emit 3 → clear_history() → get_history() пуст."""
        bus = EventBus()
        bus.emit(ScanStarted())
        bus.emit(ScanFinished())
        bus.emit(IntruderFinished())
        bus.clear_history()
        assert bus.get_history() == []

    def test_stats_returns_dict(self) -> None:
        """stats() → dict с ключами history_size, subscriber_types, total_handlers."""
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
        """из threading.Thread emit_threadsafe(event, loop) → event в history."""
        bus = EventBus()
        loop = asyncio.new_event_loop()

        event = ScanStarted(targets=["http://example.com"])

        def worker():
            bus.emit_threadsafe(event, loop)

        t = threading.Thread(target=worker)
        t.start()
        t.join(timeout=2)

        # emit_threadsafe сохраняет событие в history немедленно (под lock)
        history = bus.get_history()
        assert len(history) == 1
        assert history[0] is event

        loop.close()


# ── TestEventBusGlobal ────────────────────────────────────────────────────────

@pytest.mark.integration
class TestEventBusGlobal:

    def setup_method(self):
        """Сбрасываем глобальный синглтон перед каждым тестом."""
        reset_event_bus()

    def teardown_method(self):
        """Сбрасываем глобальный синглтон после каждого теста."""
        reset_event_bus()

    def test_singleton_same_object(self) -> None:
        """get_event_bus() is get_event_bus() — один и тот же объект."""
        bus1 = get_event_bus()
        bus2 = get_event_bus()
        assert bus1 is bus2

    def test_reset_creates_new(self) -> None:
        """reset_event_bus() → get_event_bus() возвращает новый объект."""
        bus1 = get_event_bus()
        reset_event_bus()
        bus2 = get_event_bus()
        assert bus1 is not bus2

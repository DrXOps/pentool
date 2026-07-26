"""Unit tests for core/event_bus.py and core/events.py."""

from __future__ import annotations

import asyncio
import threading
import time

import pytest

from pentool.core.event_bus import EventBus, get_event_bus, reset_event_bus
from pentool.core.events import (
    AppEvent,
    FindingDiscovered,
    IntruderFinished,
    IntruderResultAdded,
    ProjectLoaded,
    ProjectSaved,
    ProxyRequestCaptured,
    ProxyRequestCompleted,
    ScanFinished,
    ScanProgressEvent,
    ScanStarted,
    SpiderFinished,
    TargetUrlAdded,
    UrlCrawled,
)


# ── Fixtures ───────────────────────────────────────────────────────────────────

@pytest.fixture
def bus() -> EventBus:
    return EventBus(max_history=100)


@pytest.fixture(autouse=True)
def reset_global_bus():
    """Resets the global singleton after each test."""
    yield
    reset_event_bus()


# ── AppEvent base ──────────────────────────────────────────────────────────────

class TestAppEvent:
    def test_timestamp_auto_set(self):
        before = time.time()
        e = AppEvent()
        after = time.time()
        assert before <= e.timestamp <= after

    def test_source_default_empty(self):
        assert AppEvent().source == ""

    def test_source_can_be_set(self):
        e = AppEvent(source="scanner")
        assert e.source == "scanner"


# ── Events dataclasses ────────────────────────────────────────────────────────

class TestEventDataclasses:
    def test_scan_started_defaults(self):
        e = ScanStarted()
        assert e.targets == []
        assert e.checks == []

    def test_scan_finished(self):
        e = ScanFinished(total_findings=5, stopped_early=True)
        assert e.total_findings == 5
        assert e.stopped_early is True

    def test_scan_progress(self):
        e = ScanProgressEvent(done=3, total=10, scanning=True)
        assert e.done == 3
        assert e.total == 10

    def test_finding_discovered(self):
        class FakeFinding:
            pass
        f = FakeFinding()
        e = FindingDiscovered(finding=f, scan_source="passive")
        assert e.finding is f
        assert e.scan_source == "passive"

    def test_url_crawled(self):
        e = UrlCrawled(url="https://example.com/path", base_target="https://example.com")
        assert e.url == "https://example.com/path"

    def test_spider_finished(self):
        e = SpiderFinished(base_url="https://x.com", pages_count=10, forms_count=2, endpoints_count=5)
        assert e.pages_count == 10

    def test_intruder_result_added(self):
        e = IntruderResultAdded(result={"status": 200})
        assert e.result == {"status": 200}

    def test_intruder_finished(self):
        e = IntruderFinished(total_results=42, stopped_early=False)
        assert e.total_results == 42

    def test_proxy_request_captured(self):
        e = ProxyRequestCaptured(request_id="abc", method="GET", url="https://x.com", host="x.com")
        assert e.method == "GET"

    def test_proxy_request_completed(self):
        e = ProxyRequestCompleted(request_id="abc", status_code=200)
        assert e.status_code == 200

    def test_target_url_added(self):
        e = TargetUrlAdded(url="https://x.com/api", host="x.com")
        assert e.host == "x.com"

    def test_project_saved(self):
        e = ProjectSaved(path="/tmp/proj.json")
        assert e.path == "/tmp/proj.json"

    def test_project_loaded(self):
        e = ProjectLoaded(path="/tmp/proj.json", findings_count=3, history_count=10)
        assert e.findings_count == 3


# ── EventBus.subscribe / unsubscribe ──────────────────────────────────────────

class TestSubscribeUnsubscribe:
    def test_subscribe_adds_handler(self, bus):
        handler = lambda e: None
        bus.subscribe(ScanStarted, handler)
        assert handler in bus._subscribers[ScanStarted]

    def test_subscribe_same_handler_twice_no_duplicate(self, bus):
        handler = lambda e: None
        bus.subscribe(ScanStarted, handler)
        bus.subscribe(ScanStarted, handler)
        assert bus._subscribers[ScanStarted].count(handler) == 1

    def test_subscribe_multiple_handlers(self, bus):
        h1 = lambda e: None
        h2 = lambda e: None
        bus.subscribe(ScanStarted, h1)
        bus.subscribe(ScanStarted, h2)
        assert len(bus._subscribers[ScanStarted]) == 2

    def test_unsubscribe_removes_handler(self, bus):
        handler = lambda e: None
        bus.subscribe(ScanStarted, handler)
        bus.unsubscribe(ScanStarted, handler)
        assert handler not in bus._subscribers[ScanStarted]

    def test_unsubscribe_not_subscribed_no_error(self, bus):
        handler = lambda e: None
        bus.unsubscribe(ScanStarted, handler)  # should not raise

    def test_unsubscribe_all(self, bus):
        handler = lambda e: None
        bus.subscribe(ScanStarted, handler)
        bus.subscribe(ScanFinished, handler)
        bus.unsubscribe_all(handler)
        assert handler not in bus._subscribers[ScanStarted]
        assert handler not in bus._subscribers[ScanFinished]

    def test_different_types_independent(self, bus):
        calls_a = []
        calls_b = []
        bus.subscribe(ScanStarted, lambda e: calls_a.append(e))
        bus.subscribe(ScanFinished, lambda e: calls_b.append(e))
        bus.emit(ScanStarted())
        assert len(calls_a) == 1
        assert len(calls_b) == 0


# ── EventBus.emit ─────────────────────────────────────────────────────────────

class TestEmit:
    def test_emit_calls_handler(self, bus):
        received = []
        bus.subscribe(ScanStarted, received.append)
        bus.emit(ScanStarted(targets=["https://x.com"]))
        assert len(received) == 1
        assert received[0].targets == ["https://x.com"]

    def test_emit_calls_all_handlers(self, bus):
        received = []
        h1 = lambda e: received.append(("h1", e))
        h2 = lambda e: received.append(("h2", e))
        bus.subscribe(ScanStarted, h1)
        bus.subscribe(ScanStarted, h2)
        bus.emit(ScanStarted())
        assert len(received) == 2
        assert received[0][0] == "h1"
        assert received[1][0] == "h2"

    def test_emit_saves_to_history(self, bus):
        bus.emit(ScanStarted())
        assert len(bus._history) == 1

    def test_emit_handler_exception_does_not_stop_others(self, bus):
        received = []
        def bad_handler(e):
            raise RuntimeError("boom")
        bus.subscribe(ScanStarted, bad_handler)
        bus.subscribe(ScanStarted, received.append)
        bus.emit(ScanStarted())  # should not raise
        assert len(received) == 1

    def test_emit_no_subscribers_no_error(self, bus):
        bus.emit(ScanStarted())  # just saves to history

    def test_emit_correct_event_type_routing(self, bus):
        scan_calls = []
        find_calls = []
        bus.subscribe(ScanStarted, scan_calls.append)
        bus.subscribe(FindingDiscovered, find_calls.append)
        bus.emit(FindingDiscovered(finding={"type": "sqli"}))
        assert len(scan_calls) == 0
        assert len(find_calls) == 1

    def test_emit_multiple_events_order_preserved(self, bus):
        received = []
        bus.subscribe(ScanProgressEvent, received.append)
        for i in range(5):
            bus.emit(ScanProgressEvent(done=i, total=10))
        assert [e.done for e in received] == [0, 1, 2, 3, 4]


# ── EventBus.emit_threadsafe ──────────────────────────────────────────────────

class TestEmitThreadsafe:
    def test_emit_from_thread_reaches_handler(self, bus):
        received = []
        loop = asyncio.new_event_loop()
        bus.subscribe(FindingDiscovered, received.append)

        def worker():
            bus.emit_threadsafe(FindingDiscovered(finding="x"), loop)

        t = threading.Thread(target=worker)
        t.start()
        t.join()

        # Run one event loop tick to deliver
        loop.run_until_complete(asyncio.sleep(0))
        loop.close()

        assert len(received) == 1
        assert received[0].finding == "x"

    def test_emit_threadsafe_saves_to_history_immediately(self, bus):
        loop = asyncio.new_event_loop()

        def worker():
            bus.emit_threadsafe(ScanStarted(), loop)

        t = threading.Thread(target=worker)
        t.start()
        t.join()

        # History is saved immediately (under lock), before dispatch
        assert len(bus._history) == 1
        loop.close()

    def test_emit_threadsafe_closed_loop_no_crash(self, bus):
        received = []
        bus.subscribe(ScanStarted, received.append)
        loop = asyncio.new_event_loop()
        loop.close()  # closed loop

        # Should not raise RuntimeError
        bus.emit_threadsafe(ScanStarted(), loop)

    def test_emit_threadsafe_concurrent_from_multiple_threads(self, bus):
        received = []
        lock = threading.Lock()
        loop = asyncio.new_event_loop()

        def handler(e):
            with lock:
                received.append(e)

        bus.subscribe(UrlCrawled, handler)

        threads = []
        for i in range(10):
            t = threading.Thread(
                target=bus.emit_threadsafe,
                args=(UrlCrawled(url=f"https://x.com/{i}"), loop),
            )
            threads.append(t)

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        loop.run_until_complete(asyncio.sleep(0))
        loop.close()

        assert len(received) == 10


# ── EventBus.get_history ──────────────────────────────────────────────────────

class TestGetHistory:
    def test_empty_history(self, bus):
        assert bus.get_history() == []

    def test_history_contains_emitted_events(self, bus):
        bus.emit(ScanStarted())
        bus.emit(ScanFinished())
        h = bus.get_history()
        assert len(h) == 2

    def test_history_filter_by_type(self, bus):
        bus.emit(ScanStarted())
        bus.emit(ScanFinished())
        bus.emit(ScanStarted())
        h = bus.get_history(event_type=ScanStarted)
        assert len(h) == 2
        assert all(isinstance(e, ScanStarted) for e in h)

    def test_history_limit(self, bus):
        for _ in range(10):
            bus.emit(ScanProgressEvent())
        h = bus.get_history(limit=3)
        assert len(h) == 3

    def test_history_limit_and_type(self, bus):
        for i in range(5):
            bus.emit(UrlCrawled(url=f"https://x.com/{i}"))
        bus.emit(ScanFinished())
        h = bus.get_history(event_type=UrlCrawled, limit=2)
        assert len(h) == 2
        assert all(isinstance(e, UrlCrawled) for e in h)

    def test_history_order_chronological(self, bus):
        bus.emit(ScanStarted())
        time.sleep(0.01)
        bus.emit(ScanFinished())
        h = bus.get_history()
        assert h[0].timestamp <= h[1].timestamp

    def test_history_max_size_respected(self):
        small_bus = EventBus(max_history=5)
        for i in range(10):
            small_bus.emit(ScanProgressEvent(done=i))
        h = small_bus.get_history()
        assert len(h) == 5
        # Should be the last 5
        assert h[0].done == 5

    def test_get_history_returns_copy(self, bus):
        bus.emit(ScanStarted())
        h = bus.get_history()
        h.clear()
        assert len(bus.get_history()) == 1


# ── EventBus.replay ───────────────────────────────────────────────────────────

class TestReplay:
    def test_replay_calls_handler_for_existing_events(self, bus):
        bus.emit(FindingDiscovered(finding="a"))
        bus.emit(FindingDiscovered(finding="b"))
        bus.emit(ScanFinished())

        received = []
        bus.replay(received.append, FindingDiscovered)
        assert len(received) == 2

    def test_replay_respects_limit(self, bus):
        for i in range(10):
            bus.emit(FindingDiscovered(finding=i))
        received = []
        bus.replay(received.append, FindingDiscovered, limit=3)
        assert len(received) == 3

    def test_replay_handler_exception_no_crash(self, bus):
        bus.emit(ScanStarted())
        def bad(e):
            raise ValueError("oops")
        bus.replay(bad, ScanStarted)  # should not raise

    def test_replay_empty_history_no_calls(self, bus):
        received = []
        bus.replay(received.append, ScanStarted)
        assert received == []


# ── EventBus.clear_history ────────────────────────────────────────────────────

class TestClearHistory:
    def test_clear_removes_all(self, bus):
        bus.emit(ScanStarted())
        bus.emit(ScanFinished())
        bus.clear_history()
        assert bus.get_history() == []

    def test_clear_does_not_remove_subscribers(self, bus):
        received = []
        bus.subscribe(ScanStarted, received.append)
        bus.clear_history()
        bus.emit(ScanStarted())
        assert len(received) == 1


# ── EventBus.stats ────────────────────────────────────────────────────────────

class TestStats:
    def test_stats_empty(self, bus):
        s = bus.stats()
        assert s["history_size"] == 0
        assert s["subscriber_types"] == 0
        assert s["total_handlers"] == 0

    def test_stats_after_subscribe_and_emit(self, bus):
        bus.subscribe(ScanStarted, lambda e: None)
        bus.subscribe(ScanFinished, lambda e: None)
        bus.emit(ScanStarted())
        s = bus.stats()
        assert s["history_size"] == 1
        assert s["total_handlers"] == 2


# ── Global singleton ───────────────────────────────────────────────────────────

class TestGlobalSingleton:
    def test_get_event_bus_returns_same_instance(self):
        b1 = get_event_bus()
        b2 = get_event_bus()
        assert b1 is b2

    def test_reset_event_bus_creates_new_instance(self):
        b1 = get_event_bus()
        reset_event_bus()
        b2 = get_event_bus()
        assert b1 is not b2

    def test_singleton_thread_safe(self):
        buses = []
        lock = threading.Lock()

        def get():
            b = get_event_bus()
            with lock:
                buses.append(b)

        threads = [threading.Thread(target=get) for _ in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert all(b is buses[0] for b in buses)

    def test_global_bus_functional(self):
        bus = get_event_bus()
        received = []
        bus.subscribe(ProjectSaved, received.append)
        bus.emit(ProjectSaved(path="/tmp/x.json"))
        assert len(received) == 1

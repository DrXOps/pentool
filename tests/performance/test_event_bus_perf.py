"""Performance: EventBus throughput."""
from __future__ import annotations

import time

import pytest

from pentool.core.event_bus import EventBus
from pentool.core.events import ScanStarted, ScanFinished, FindingDiscovered


@pytest.mark.performance
def test_emit_10000_events():
    bus = EventBus()
    start = time.monotonic()
    for _ in range(10_000):
        bus.emit(ScanStarted())
    elapsed = time.monotonic() - start
    assert elapsed < 1.0, f"10000 emit took {elapsed:.3f}s (limit 1.0s)"


@pytest.mark.performance
def test_1000_subscribers():
    bus = EventBus()
    received = []

    # Subscribe 100 handlers
    handlers = []
    for _ in range(100):
        def make_handler(lst):
            def h(e):
                lst.append(1)
            return h
        h = make_handler(received)
        handlers.append(h)
        bus.subscribe(ScanStarted, h)

    start = time.monotonic()
    for _ in range(1000):
        bus.emit(ScanStarted())
    elapsed = time.monotonic() - start
    assert elapsed < 2.0, f"100 handlers x 1000 emit took {elapsed:.3f}s (limit 2.0s)"
    assert len(received) == 100 * 1000


@pytest.mark.performance
def test_get_history_perf():
    bus = EventBus(max_history=10_000)
    for _ in range(5000):
        bus.emit(ScanFinished())

    start = time.monotonic()
    for _ in range(100):
        bus.get_history()
    elapsed = time.monotonic() - start
    assert elapsed < 1.0, f"get_history() x100 took {elapsed:.3f}s (limit 1.0s)"


@pytest.mark.performance
def test_emit_no_subscribers_perf():
    bus = EventBus()
    start = time.monotonic()
    for _ in range(10_000):
        bus.emit(FindingDiscovered())
    elapsed = time.monotonic() - start
    assert elapsed < 0.5, f"10000 emit (no subs) took {elapsed:.3f}s (limit 0.5s)"

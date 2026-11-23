"""ActivityState is the single source of truth for "what is running" (T-030, part 1).

Producers (proxy, spider, scanner, intruder, recon, ai) call `set_activity()` once per
transition; consumers subscribe through the EventBus. The tests pin the three properties
the status strip relies on:

* a state change publishes exactly one `ActivityChanged`;
* an unchanged state publishes nothing (otherwise every repaint would churn the layout);
* an unknown module is reported, not invented.
"""

from __future__ import annotations

import pytest

from pentool.core.activity import TRACKED_MODULES, ActivityState, get_activity_state, set_activity
from pentool.core.event_bus import get_event_bus
from pentool.core.events import ActivityChanged


@pytest.fixture()
def state() -> ActivityState:
    fresh = ActivityState()
    fresh.reset()
    return fresh


def test_each_module_starts_idle(state: ActivityState) -> None:
    for module in TRACKED_MODULES:
        assert state.is_active(module) is False
    assert state.any_active() is False


def test_set_publishes_one_event_per_transition(state: ActivityState) -> None:
    received: list[tuple[str, bool]] = []

    def handler(event: ActivityChanged) -> None:
        received.append((event.module, event.active))

    bus = get_event_bus()
    bus.subscribe(ActivityChanged, handler)
    try:
        state.set("proxy", True)
        state.set("proxy", True)  # unchanged: no second event
        state.set("proxy", False)
    finally:
        bus.unsubscribe(ActivityChanged, handler)

    assert received == [("proxy", True), ("proxy", False)]
    assert state.is_active("proxy") is False


def test_unknown_module_is_ignored_not_invented(state: ActivityState) -> None:
    received: list[str] = []

    def handler(event: ActivityChanged) -> None:
        received.append(event.module)

    bus = get_event_bus()
    bus.subscribe(ActivityChanged, handler)
    try:
        state.set("nonsense", True)
    finally:
        bus.unsubscribe(ActivityChanged, handler)

    assert received == []
    assert state.is_active("nonsense") is False


def test_snapshot_is_a_copy(state: ActivityState) -> None:
    state.set("spider", True)
    snapshot = state.snapshot()
    snapshot["spider"] = False
    assert state.is_active("spider") is True, "snapshot must not expose the live dict"


def test_reset_returns_everything_to_idle(state: ActivityState) -> None:
    state.set("scanner", True)
    state.set("intruder", True)
    state.reset()
    assert state.any_active() is False


def test_global_helper_reaches_the_process_registry() -> None:
    registry = get_activity_state()
    set_activity("recon", True)
    try:
        assert registry.is_active("recon") is True
    finally:
        set_activity("recon", False)


def test_broken_subscriber_does_not_lose_the_state(state: ActivityState) -> None:
    def exploding(event: ActivityChanged) -> None:
        raise RuntimeError("subscriber is broken")

    bus = get_event_bus()
    bus.subscribe(ActivityChanged, exploding)
    try:
        state.set("ai", True)
    finally:
        bus.unsubscribe(ActivityChanged, exploding)

    assert state.is_active("ai") is True, "the registry must keep the value even if a subscriber raised"

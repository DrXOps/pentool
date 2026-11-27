"""Background activity is reported by events, not by polling (item 5)."""

from __future__ import annotations

from pathlib import Path

from pentool.core.activity import ActivityState
from pentool.core.event_bus import get_event_bus
from pentool.core.events import ActivityChanged


def test_state_change_emits_one_event() -> None:
    received: list[tuple[str, bool]] = []
    bus = get_event_bus()

    def handler(event: ActivityChanged) -> None:
        received.append((event.module, event.active))

    bus.subscribe(ActivityChanged, handler)
    try:
        state = ActivityState()
        state.set("proxy", True)
        state.set("proxy", True)  # no change — must not emit twice
        state.set("proxy", False)
    finally:
        bus.unsubscribe(ActivityChanged, handler)

    assert received == [("proxy", True), ("proxy", False)]


def test_unknown_module_is_ignored() -> None:
    state = ActivityState()
    state.set("no-such-module", True)  # logs a warning, must not raise
    assert "no-such-module" not in state.snapshot()


def test_indicator_subscribes_and_releases() -> None:
    """The widget listens to the bus and unsubscribes on unmount (ADR-12)."""
    indicator_path = Path(__file__).resolve().parents[3] / "pentool/tui/widgets/activity_indicator.py"
    indicator = indicator_path.read_text(encoding="utf-8")

    assert "subscribe(ActivityChanged" in indicator, "индикатор должен слушать событие активности"
    assert "unsubscribe(ActivityChanged" in indicator, "подписка обязана сниматься при unmount"

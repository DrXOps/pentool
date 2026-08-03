"""Unit tests for EventBus Subscription context manager."""

import pytest

from pentool.core.event_bus import EventBus, Subscription
from pentool.core.events import ScanFinished


class TestSubscriptionContextManager:
    """Test Subscription context manager for auto-unsubscribe."""

    def test_subscription_subscribes_on_enter(self):
        """Subscription subscribes on __enter__."""
        bus = EventBus()
        events = []

        def handler(event):
            events.append(event)

        with bus.subscription(ScanFinished, handler):
            event = ScanFinished(total_findings=5, stopped_early=False, source="test")
            bus.emit(event)

        assert len(events) == 1

    def test_subscription_unsubscribes_on_exit(self):
        """Subscription unsubscribes on __exit__."""
        bus = EventBus()
        events = []

        def handler(event):
            events.append(event)

        with bus.subscription(ScanFinished, handler):
            pass

        # After exit, handler should be unsubscribed
        event = ScanFinished(total_findings=5, stopped_early=False, source="test")
        bus.emit(event)

        assert len(events) == 0

    def test_subscription_unsubscribes_on_exception(self):
        """Subscription unsubscribes even if exception occurs."""
        bus = EventBus()
        events = []

        def handler(event):
            events.append(event)

        try:
            with bus.subscription(ScanFinished, handler):
                raise RuntimeError("Test error")
        except RuntimeError:
            pass

        # Handler should still be unsubscribed
        event = ScanFinished(total_findings=5, stopped_early=False, source="test")
        bus.emit(event)

        assert len(events) == 0

    def test_subscription_multiple_handlers(self):
        """Multiple subscriptions work independently."""
        bus = EventBus()
        events1 = []
        events2 = []

        def handler1(event):
            events1.append(event)

        def handler2(event):
            events2.append(event)

        with bus.subscription(ScanFinished, handler1):
            with bus.subscription(ScanFinished, handler2):
                event = ScanFinished(total_findings=5, stopped_early=False, source="test")
                bus.emit(event)

                # Both should receive
                assert len(events1) == 1
                assert len(events2) == 1

            # After handler2 exits, only handler1 should receive
            event2 = ScanFinished(total_findings=3, stopped_early=False, source="test")
            bus.emit(event2)

            assert len(events1) == 2
            assert len(events2) == 1

        # After both exit, neither should receive
        event3 = ScanFinished(total_findings=1, stopped_early=False, source="test")
        bus.emit(event3)

        assert len(events1) == 2
        assert len(events2) == 1

    def test_subscription_reusable(self):
        """Subscription instance can be reused."""
        bus = EventBus()
        events = []

        def handler(event):
            events.append(event)

        sub = Subscription(bus, ScanFinished, handler)

        with sub:
            event = ScanFinished(total_findings=1, stopped_early=False, source="test")
            bus.emit(event)

        assert len(events) == 1

        # Reuse the same subscription
        with sub:
            event2 = ScanFinished(total_findings=2, stopped_early=False, source="test")
            bus.emit(event2)

        assert len(events) == 2

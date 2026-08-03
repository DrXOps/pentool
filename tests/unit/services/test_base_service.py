"""Unit tests for pentool/services/base_service.py."""

from __future__ import annotations

import asyncio
from unittest.mock import Mock

import pytest

from pentool.core.event_bus import EventBus
from pentool.services.base_service import BaseService


class TestBaseServiceInit:
    """Test BaseService initialization."""

    def test_init_with_defaults(self):
        """Initialize with default singleton EventBus."""
        service = BaseService()

        assert service._bus is not None
        assert service._tui_loop is None
        assert service._on_log is None

    def test_init_with_custom_event_bus(self):
        """Initialize with custom EventBus."""
        custom_bus = EventBus()
        service = BaseService(event_bus=custom_bus)

        assert service._bus is custom_bus

    def test_init_with_tui_loop(self):
        """Initialize with TUI event loop."""
        loop = asyncio.new_event_loop()
        service = BaseService(tui_loop=loop)

        assert service._tui_loop is loop
        loop.close()

    def test_init_with_on_log_callback(self):
        """Initialize with log callback."""
        callback = Mock()
        service = BaseService(on_log=callback)

        assert service._on_log is callback


class TestBaseServiceEmit:
    """Test _emit method."""

    def test_emit_without_tui_loop(self):
        """Emit calls bus.emit when no tui_loop."""
        bus = EventBus()
        service = BaseService(event_bus=bus)

        events = []
        def capture(event):
            events.append(event)

        bus.subscribe("test_event", capture)

        from pentool.core.events import ProxyRequestStart
        event = ProxyRequestStart(request_id=1, method="GET", url="http://example.com")

        service._emit(event)

        # Should have been emitted
        assert len(events) == 1
        assert events[0] is event

    @pytest.mark.asyncio
    async def test_emit_with_tui_loop(self):
        """Emit calls bus.emit_threadsafe when tui_loop is set."""
        bus = EventBus()
        loop = asyncio.get_event_loop()
        service = BaseService(event_bus=bus, tui_loop=loop)

        events = []
        def capture(event):
            events.append(event)

        bus.subscribe("test_event", capture)

        from pentool.core.events import ProxyRequestStart
        event = ProxyRequestStart(request_id=1, method="GET", url="http://example.com")

        service._emit(event)

        # Give emit_threadsafe time to schedule
        await asyncio.sleep(0.01)

        assert len(events) == 1
        assert events[0] is event

    def test_emit_with_closed_loop_falls_back(self):
        """Emit falls back to direct emit if tui_loop is closed."""
        bus = EventBus()
        loop = asyncio.new_event_loop()

        service = BaseService(event_bus=bus, tui_loop=loop)

        # Close loop after service creation
        loop.close()

        events = []
        def capture(event):
            events.append(event)

        bus.subscribe("test_event", capture)

        from pentool.core.events import ScanStarted
        event = ScanStarted(targets=["http://example.com"], checks=[], source="test")

        service._emit(event)

        # Should have fallen back to direct emit
        assert len(events) == 1

    def test_emit_handles_exception_gracefully(self):
        """Emit handles exceptions without crashing."""
        bus = EventBus()
        service = BaseService(event_bus=bus)

        # Mock emit to raise exception
        def raise_error(event):
            raise RuntimeError("Test error")

        original_emit = bus.emit
        bus.emit = raise_error

        from pentool.core.events import ScanStarted
        event = ScanStarted(targets=["http://example.com"], checks=[], source="test")

        # Should not raise
        service._emit(event)

        # Restore
        bus.emit = original_emit


class TestBaseServiceLog:
    """Test _log method."""

    def test_log_with_callback(self):
        """Log calls callback when set."""
        logs = []
        def capture_log(msg):
            logs.append(msg)

        service = BaseService(on_log=capture_log)

        service._log("[cyan]TEST[/cyan] message")

        assert len(logs) == 1
        assert logs[0] == "[cyan]TEST[/cyan] message"

    def test_log_without_callback(self):
        """Log does nothing when callback is None."""
        service = BaseService()

        # Should not raise
        service._log("test message")

    def test_log_handles_callback_exception(self):
        """Log handles callback exceptions gracefully."""
        def raise_error(msg):
            raise RuntimeError("Test error")

        service = BaseService(on_log=raise_error)

        # Should not raise
        service._log("test message")

    def test_log_multiple_messages(self):
        """Log handles multiple messages."""
        logs = []
        def capture_log(msg):
            logs.append(msg)

        service = BaseService(on_log=capture_log)

        service._log("message 1")
        service._log("message 2")
        service._log("message 3")

        assert len(logs) == 3
        assert logs == ["message 1", "message 2", "message 3"]


class TestBaseServiceIntegration:
    """Test BaseService in integration scenarios."""

    @pytest.mark.asyncio
    async def test_emit_and_log_together(self):
        """Test emit and log work together."""
        bus = EventBus()
        logs = []
        events = []

        def capture_log(msg):
            logs.append(msg)

        def capture_event(event):
            events.append(event)

        bus.subscribe("test_event", capture_event)

        service = BaseService(event_bus=bus, on_log=capture_log)

        from pentool.core.events import ScanStarted
        event = ScanStarted(targets=["http://example.com"], checks=[], source="test")

        service._emit(event)
        service._log("[info]Request completed")

        await asyncio.sleep(0.01)

        assert len(events) == 1
        assert len(logs) == 1

    def test_subclass_can_use_base_methods(self):
        """Subclasses can use _emit and _log directly."""
        class MyService(BaseService):
            def do_work(self):
                self._log("Starting work")
                from pentool.core.events import ScanStarted
                self._emit(ScanStarted(targets=["http://example.com"], checks=[], source="test"))

        logs = []
        events = []

        bus = EventBus()
        bus.subscribe("test_event", lambda e: events.append(e))

        service = MyService(event_bus=bus, on_log=lambda m: logs.append(m))
        service.do_work()

        assert len(logs) == 1
        assert len(events) == 1

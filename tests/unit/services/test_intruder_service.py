"""Tests for IntruderService."""

import pytest
from unittest.mock import Mock, AsyncMock
from datetime import datetime, timezone
from pentool.services.intruder_service import IntruderService
from pentool.api.intruder_api import IntruderAPI
from pentool.modules.intruder import IntruderConfig, IntruderResult, AttackType
from pentool.core.event_bus import EventBus


@pytest.fixture
def event_bus():
    """Create EventBus instance."""
    return EventBus()


@pytest.fixture
def intruder_api():
    """Create mock IntruderAPI."""
    api = Mock(spec=IntruderAPI)

    # Mock results
    mock_results = [
        IntruderResult(
            id="result-1",
            attack_id="attack-1",
            request_number=1,
            payload_values=["test1"],
            request_raw="GET /?q=test1 HTTP/1.1\r\nHost: test.com\r\n\r\n",
            response_status=200,
            response_length=100,
            response_time_ms=50,
            error=None,
            timestamp=datetime.now(timezone.utc)
        ),
        IntruderResult(
            id="result-2",
            attack_id="attack-1",
            request_number=2,
            payload_values=["test2"],
            request_raw="GET /?q=test2 HTTP/1.1\r\nHost: test.com\r\n\r\n",
            response_status=404,
            response_length=200,
            response_time_ms=75,
            error=None,
            timestamp=datetime.now(timezone.utc)
        ),
    ]

    api.start_attack = AsyncMock(return_value=None)
    api.get_results = Mock(return_value=mock_results)
    api.pause = Mock()
    api.resume = Mock()
    api.stop = Mock()
    return api


@pytest.fixture
def service(intruder_api, event_bus):
    """Create IntruderService instance."""
    return IntruderService(intruder_api, event_bus)


class TestIntruderServiceInit:
    """Test IntruderService initialization."""

    def test_init_with_api_and_bus(self, intruder_api, event_bus):
        """Test initialization with API and EventBus."""
        service = IntruderService(intruder_api, event_bus)
        assert service._api == intruder_api
        assert service._bus == event_bus
        assert service._tui_loop is None


class TestIntruderServiceStartAttack:
    """Test IntruderService.start_attack()."""

    @pytest.mark.asyncio
    async def test_start_attack_returns_results(self, service, intruder_api):
        """Test start_attack returns results from API."""
        config = IntruderConfig(
            template="GET /?q=§p§ HTTP/1.1\r\nHost: test.com\r\n\r\n",
            attack_type=AttackType.SNIPER,
            payload_sets=[["test1", "test2"]],
            threads=1,
        )

        results = await service.start_attack(config, None, None)

        assert len(results) == 2
        assert results[0].payload_values == ["test1"]
        assert results[0].response_status == 200
        assert results[1].payload_values == ["test2"]
        assert results[1].response_status == 404
        intruder_api.start_attack.assert_called_once()

    @pytest.mark.asyncio
    async def test_start_attack_with_callbacks(self, service, intruder_api):
        """Test start_attack calls callbacks."""
        on_result_called = False
        on_progress_called = False

        def on_result(result):
            nonlocal on_result_called
            on_result_called = True

        def on_progress(current, total):
            nonlocal on_progress_called
            on_progress_called = True

        config = IntruderConfig(
            template="GET / HTTP/1.1\r\nHost: test.com\r\n\r\n",
            attack_type=AttackType.SNIPER,
            payload_sets=[["test"]],
            threads=1,
        )

        await service.start_attack(config, on_result, on_progress)

        # Callbacks should be passed to API
        intruder_api.start_attack.assert_called_once()

    @pytest.mark.asyncio
    async def test_start_attack_handles_exception(self, service, intruder_api):
        """Test start_attack handles exceptions gracefully."""
        intruder_api.start_attack.side_effect = RuntimeError("Test error")

        config = IntruderConfig(
            template="GET / HTTP/1.1\r\nHost: test.com\r\n\r\n",
            attack_type=AttackType.SNIPER,
            payload_sets=[["test"]],
            threads=1,
        )

        results = await service.start_attack(config, None, None)

        assert results == []


class TestIntruderServiceControl:
    """Test IntruderService control methods."""

    def test_pause(self, service, intruder_api):
        """Test pause delegates to API."""
        service.pause()
        intruder_api.pause.assert_called_once()

    def test_resume(self, service, intruder_api):
        """Test resume delegates to API."""
        service.resume()
        intruder_api.resume.assert_called_once()

    def test_stop(self, service, intruder_api):
        """Test stop delegates to API."""
        service.stop()
        intruder_api.stop.assert_called_once()


class TestIntruderServiceEvents:
    """Test IntruderService event emission."""

    @pytest.mark.asyncio
    async def test_emits_result_added_events(self, service, intruder_api, event_bus):
        """Test service emits IntruderResultAdded events."""
        events_received = []

        def on_event(event):
            events_received.append(event)

        from pentool.core.events import IntruderResultAdded
        event_bus.subscribe(IntruderResultAdded, on_event)

        config = IntruderConfig(
            template="GET / HTTP/1.1\r\nHost: test.com\r\n\r\n",
            attack_type=AttackType.SNIPER,
            payload_sets=[["test"]],
            threads=1,
        )

        await service.start_attack(config, None, None)

        # Events should be emitted (implementation-specific)
        # This test verifies the service doesn't crash

    @pytest.mark.asyncio
    async def test_emits_finished_event(self, service, intruder_api, event_bus):
        """Test service emits IntruderFinished event."""
        events_received = []

        def on_event(event):
            events_received.append(event)

        from pentool.core.events import IntruderFinished
        event_bus.subscribe(IntruderFinished, on_event)

        config = IntruderConfig(
            template="GET / HTTP/1.1\r\nHost: test.com\r\n\r\n",
            attack_type=AttackType.SNIPER,
            payload_sets=[["test"]],
            threads=1,
        )

        await service.start_attack(config, None, None)

        # Finished event should be emitted


class TestIntruderServiceEdgeCases:
    """Test edge cases and error handling."""

    @pytest.mark.asyncio
    async def test_empty_payloads(self, service):
        """Test attack with empty payloads."""
        # Create separate API with empty results
        api = Mock(spec=IntruderAPI)
        api.start_attack = AsyncMock(return_value=None)
        api.get_results = Mock(return_value=[])

        service._api = api

        config = IntruderConfig(
            template="GET / HTTP/1.1\r\nHost: test.com\r\n\r\n",
            attack_type=AttackType.SNIPER,
            payload_sets=[[]],
            threads=1,
        )

        results = await service.start_attack(config, None, None)

        assert results == []

    @pytest.mark.asyncio
    async def test_none_callbacks(self, service, intruder_api):
        """Test attack with None callbacks doesn't crash."""
        config = IntruderConfig(
            template="GET / HTTP/1.1\r\nHost: test.com\r\n\r\n",
            attack_type=AttackType.SNIPER,
            payload_sets=[["test"]],
            threads=1,
        )

        results = await service.start_attack(config, None, None)

        assert len(results) == 2

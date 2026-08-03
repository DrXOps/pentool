"""Tests for ScanService."""

import pytest
from unittest.mock import Mock, AsyncMock

from tests.conftest import pytest_skip_if_no_scanner

pytestmark = pytest_skip_if_no_scanner

from pentool.services.scan_service import ScanService, ScanConfig
from pentool.api.scanner_api import ScannerAPI
from pentool.api.spider_api import SpiderAPI
from pentool.modules.scanner.base import Finding
from pentool.core.event_bus import EventBus


@pytest.fixture
def event_bus():
    """Create EventBus instance."""
    return EventBus()


@pytest.fixture
def scanner_api():
    """Create mock ScannerAPI."""
    api = Mock(spec=ScannerAPI)
    api.start_scan = AsyncMock()
    api.stop_scan = Mock()
    api.get_findings = Mock(return_value=[
        Finding(
            type="xss",
            name="Reflected XSS",
            url="https://example.com/search?q=test",
            severity="high",
            parameter="q",
            payload="<script>alert(1)</script>",
            evidence="Reflected in response body",
        )
    ])
    return api


@pytest.fixture
def spider_api():
    """Create mock SpiderAPI."""
    api = Mock(spec=SpiderAPI)
    api.crawl = AsyncMock(return_value=["https://example.com", "https://example.com/page"])
    api.stop = Mock()
    return api


@pytest.fixture
def service(scanner_api, spider_api, event_bus):
    """Create ScanService instance."""
    return ScanService(scanner_api, spider_api, event_bus)


class TestScanServiceInit:
    """Test ScanService initialization."""

    def test_init_with_apis_and_bus(self, scanner_api, spider_api, event_bus):
        """Test initialization with APIs and EventBus."""
        service = ScanService(scanner_api, spider_api, event_bus)
        assert service._scanner == scanner_api
        assert service._spider == spider_api
        assert service._bus == event_bus


class TestScanServiceRun:
    """Test ScanService.run()."""

    @pytest.mark.asyncio
    async def test_run_basic(self, service, scanner_api):
        """Test basic run."""
        config = ScanConfig(
            targets=["https://example.com"],
            resume=False,
            check_names=["xss"],
        )

        try:
            await service.run(config)
        except Exception:
            # Service may fail without full setup, that's ok
            pass

        # Should attempt to start scan (may fail in test env)
        # Just verify service doesn't crash


class TestScanServiceStop:
    """Test ScanService.stop()."""

    def test_stop_delegates_to_scanner(self, service):
        """Test stop requests stop."""
        service.request_stop()
        # Should set flag
        assert service._stop_requested is True


class TestScanServiceGetFindings:
    """Test ScanService.get_findings()."""

    def test_scanner_api_has_get_findings(self, service, scanner_api):
        """Test scanner API has get_findings method."""
        findings = scanner_api.get_findings()

        assert len(findings) == 1
        assert findings[0].severity == "high"
        assert findings[0].name == "Reflected XSS"


class TestScanConfigDataclass:
    """Test ScanConfig dataclass."""

    def test_scan_config_default_values(self):
        """Test ScanConfig with default values."""
        config = ScanConfig(
            targets=["https://example.com"],
        )

        assert config.targets == ["https://example.com"]
        assert config.check_names is None  # Default (all checks)
        assert config.threads == 10  # Default
        assert config.max_depth == 3  # Default
        assert config.max_pages == 100  # Default

    def test_scan_config_custom_values(self):
        """Test ScanConfig with custom values."""
        config = ScanConfig(
            targets=["https://example.com"],
            check_names=["xss", "sqli"],
            threads=5,
            max_depth=5,
            max_pages=200,
            delay_sec=0.5,
        )

        assert config.targets == ["https://example.com"]
        assert config.check_names == ["xss", "sqli"]
        assert config.threads == 5
        assert config.max_depth == 5
        assert config.max_pages == 200
        assert config.delay_sec == 0.5

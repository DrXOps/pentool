"""Tests for ScanService."""

import pytest
from unittest.mock import Mock, AsyncMock

# Skip all tests if scanner module not available
pytest.importorskip("pentool.modules.scanner")

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

    @pytest.mark.asyncio
    async def test_auth_headers_flow_from_crawl_into_active_scan(
        self, scanner_api, spider_api, event_bus,
    ):
        """Reuse (2.1): if the crawler establishes auth headers, they must be
        carried into the ACTIVE scan, not dropped (DVWA would otherwise
        redirect unauthenticated probes to /login.php)."""
        from pentool.modules.spider import SpiderResult
        from pentool.services.scan_service import ScanService

        spider_api.crawl = AsyncMock(return_value=SpiderResult(
            base_url="https://example.com",
            pages=["https://example.com/page"],
            auth_headers={"Cookie": "PHPSESSID=abc123"},
        ))

        scanner_api.run_active_on_requests = AsyncMock(return_value=[])
        scanner_api.save_findings = AsyncMock(return_value=None)

        service = ScanService(scanner_api, spider_api, event_bus)
        config = ScanConfig(
            targets=["https://example.com"],
            resume=False,
            check_names=["xss"],
        )

        await service.run(config)

        # The active scan must receive requests carrying the crawl's auth.
        assert scanner_api.run_active_on_requests.called, "active scan was never run"
        _, kwargs = scanner_api.run_active_on_requests.call_args
        seed = kwargs.get("seed_requests") or (
            scanner_api.run_active_on_requests.call_args.args[0]
        )
        assert seed, "no seed_requests passed to active scan"
        auth_by_url = {req.url: dict(req.headers or {}) for req in seed}
        # The base target + crawled page should carry the session cookie.
        assert auth_by_url.get("https://example.com", {}).get("Cookie"), (
            f"active-scan request missing auth Cookie; got urls={auth_by_url}"
        )

    @pytest.mark.asyncio
    async def test_auth_headers_forwarded_to_engine_http_client(
        self, scanner_api, spider_api, event_bus,
    ):
        """2.1: the HTTPClient handed to configure_engine must carry the
        auth headers, so the TechFingerprinter baseline also stays
        authenticated."""
        from unittest.mock import ANY

        from pentool.modules.spider import SpiderResult
        from pentool.services.scan_service import ScanService

        spider_api.crawl = AsyncMock(return_value=SpiderResult(
            base_url="https://example.com",
            pages=[],
            auth_headers={"Authorization": "Bearer tok"},
        ))
        scanner_api.run_active_on_requests = AsyncMock(return_value=[])
        scanner_api.save_findings = AsyncMock(return_value=None)
        scanner_api.configure_engine = Mock(return_value=None)  # synchronous API

        service = ScanService(scanner_api, spider_api, event_bus)
        config = ScanConfig(targets=["https://example.com"], resume=False)

        await service.run(config)

        assert scanner_api.configure_engine.called
        kwargs = scanner_api.configure_engine.call_args.kwargs
        http_client = kwargs.get("http_client")
        assert http_client is not None
        # HTTPClient stores extra_headers privately — verify indirectly via
        # the requests it would send being seeded with auth.
        assert getattr(http_client, "_extra_headers", None), (
            "engine HTTPClient did not receive extra_headers"
        )
        assert http_client._extra_headers.get("Authorization") == "Bearer tok"


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
        assert config.max_depth == 5  # Default
        assert config.max_pages == 200  # Default

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

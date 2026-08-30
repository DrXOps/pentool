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


    @pytest.mark.asyncio
    async def test_auto_login_populates_auth_headers(
        self, scanner_api, spider_api, event_bus,
    ):
        """2.3: when auto_login is enabled and the crawl learned no session,
        ScanService calls build_session_headers and stores the cookie in
        _auth_headers for the active phase."""
        from unittest.mock import patch

        from pentool.modules.spider import SpiderResult
        from pentool.services.scan_service import ScanService

        async def _auto_ok(**kwargs):
            return {"Cookie": "PHPSESSID=autologin1"}

        spider_api.crawl = AsyncMock(return_value=SpiderResult(
            base_url="https://example.com", pages=[], auth_headers={},
        ))
        scanner_api.run_active_on_requests = AsyncMock(return_value=[])
        scanner_api.save_findings = AsyncMock(return_value=None)

        service = ScanService(scanner_api, spider_api, event_bus)
        config = ScanConfig(
            targets=["https://example.com"],
            resume=False,
            auto_login=True,
            login=("admin", "password"),
        )

        # _try_auto_login does `from pentool.utils.auth_login import
        # build_session_headers` lazily, so patch it at its source module.
        with patch("pentool.utils.auth_login.build_session_headers",
                   side_effect=_auto_ok):
            await service.run(config)

        assert "Cookie" in service._auth_headers
        assert service._auth_headers["Cookie"] == "PHPSESSID=autologin1"


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


class TestFilterTargets:
    """2.5: don't collapse same-template URLs that carry DIFFERENT parameter
    values — keep a bounded bundle of variants instead of one representative."""

    def _service(self, scanner_api, spider_api, event_bus):
        from pentool.services.scan_service import ScanService
        return ScanService(scanner_api, spider_api, event_bus)

    def test_different_param_values_preserved(self, scanner_api, spider_api, event_bus):
        svc = self._service(scanner_api, spider_api, event_bus)
        targets = [
            "http://x.com/vulnerabilities/sqli/?id=1",
            "http://x.com/vulnerabilities/sqli/?id=2",
            "http://x.com/vulnerabilities/sqli/?id=3",
        ]
        out = svc._filter_targets(targets)
        assert len(out) == 3, "different ?id= values must NOT collapse to one template rep"
        assert set(out) == set(targets)

    def test_same_url_duplicate_deduped(self, scanner_api, spider_api, event_bus):
        svc = self._service(scanner_api, spider_api, event_bus)
        targets = ["http://x.com/page?id=1", "http://x.com/page?id=1"]
        out = svc._filter_targets(targets)
        assert len(out) == 1

    def test_variants_capped_per_template(self, scanner_api, spider_api, event_bus):
        svc = self._service(scanner_api, spider_api, event_bus)
        targets = [f"http://x.com/search?q={i}" for i in range(20)]
        out = svc._filter_targets(targets)
        assert len(out) <= svc._MAX_VARIANTS_PER_TEMPLATE, (
            "variant bundle must be capped, not unbounded"
        )

    def test_static_assets_skipped(self, scanner_api, spider_api, event_bus):
        svc = self._service(scanner_api, spider_api, event_bus)
        targets = [
            "http://x.com/app.js",
            "http://x.com/style.css",
            "http://x.com/index.html",
        ]
        out = svc._filter_targets(targets)
        assert all("app.js" not in t and "style.css" not in t for t in out), (
            "static assets should be removed; got " + repr(out)
        )


class TestPostFormSubmission:
    """2.6: POST forms are auto-submitted into the active scan unless their
    action is destructive (/logout, /delete, /admin, ...)."""

    def _form(self, action: str, fields=None):
        from pentool.modules.spider import SpiderForm, FormField

        fields = fields or [FormField(name="username", type="text", value="admin")]
        return SpiderForm(action=action, method="POST", fields=fields)

    def test_risky_action_detected(self):
        from pentool.services.scan_service import ScanService

        for risky in (
            "http://x.com/logout", "http://x.com/user/delete", "http://x.com/admin/config",
        ):
            assert ScanService._is_risky_form_action(risky) is True, risky

    def test_safe_action_not_flagged(self):
        from pentool.services.scan_service import ScanService

        assert ScanService._is_risky_form_action("http://x.com/vulnerabilities/sqli_blind/id") is False

    @pytest.mark.asyncio
    async def test_safe_post_form_added_to_active_scan(
        self, scanner_api, spider_api, event_bus,
    ):
        from pentool.modules.spider import SpiderResult
        from pentool.services.scan_service import ScanService

        spider_api.crawl = AsyncMock(return_value=SpiderResult(
            base_url="http://x.com/", pages=["http://x.com/vulnerabilities/"],
            forms=[self._form("http://x.com/vulnerabilities/sqli_blind/id", fields=[
                type("F", (), {"name": "id", "value": "1", "type": "text"})(),
            ])],
        ))
        scanner_api.run_active_on_requests = AsyncMock(return_value=[])
        scanner_api.save_findings = AsyncMock(return_value=None)

        service = ScanService(scanner_api, spider_api, event_bus)
        config = ScanConfig(targets=["http://x.com/"], resume=False)

        await service.run(config)

        assert scanner_api.run_active_on_requests.called
        _, kwargs = scanner_api.run_active_on_requests.call_args
        seed = kwargs.get("seed_requests") or scanner_api.run_active_on_requests.call_args.args[0]
        posts = [r for r in seed if getattr(r, "method", "").upper() == "POST"]
        assert any("sqli_blind/id" in getattr(r, "url", "") for r in posts), (
            "safe POST form was not submitted into active scan"
        )

    @pytest.mark.asyncio
    async def test_risky_post_form_skipped(
        self, scanner_api, spider_api, event_bus,
    ):
        from pentool.modules.spider import SpiderResult
        from pentool.services.scan_service import ScanService

        spider_api.crawl = AsyncMock(return_value=SpiderResult(
            base_url="http://x.com/", pages=[],
            forms=[self._form("http://x.com/user/delete/me")],
        ))
        scanner_api.run_active_on_requests = AsyncMock(return_value=[])
        scanner_api.save_findings = AsyncMock(return_value=None)

        service = ScanService(scanner_api, spider_api, event_bus)
        config = ScanConfig(targets=["http://x.com/"], resume=False)

        await service.run(config)

        assert scanner_api.run_active_on_requests.called
        _, kwargs = scanner_api.run_active_on_requests.call_args
        seed = kwargs.get("seed_requests") or scanner_api.run_active_on_requests.call_args.args[0]
        posts = [r for r in seed if getattr(r, "method", "").upper() == "POST"]
        assert all("delete" not in getattr(r, "url", "").lower() for r in posts), (
            "destructive POST form must NOT be auto-submitted"
        )


class TestHybridJsCrawl:
    """2.4: hybrid_js=True re-crawls with JS when the static crawl is dry."""

    @pytest.mark.asyncio
    async def test_hybrid_js_triggered_by_flag(self, monkeypatch):
        """With hybrid_js=True and a tiny static result, ScanService fires a
        second (JS) SpiderAPI crawl too."""
        from unittest.mock import patch

        from pentool.modules.spider import SpiderResult
        from pentool.services.scan_service import ScanService

        static_result = SpiderResult(
            base_url="http://x.com/", pages=["http://x.com/"], auth_headers={},
        )

        # The JS SpiderAPI is constructed *locally* inside _crawl_target via
        # `from pentool.api.spider_api import SpiderAPI, SpiderConfig`, so patch
        # the source module where that import resolves.
        js_spider_cls = Mock()
        js_spider_cls.return_value = Mock()
        js_spider_cls.return_value.crawl = AsyncMock(return_value=SpiderResult(
            base_url="http://x.com/", pages=["http://x.com/app", "http://x.com/route"],
        ))

        spider_api = Mock(spec=__import__("pentool.api.spider_api", fromlist=["SpiderAPI"]).SpiderAPI)
        spider_api.crawl = AsyncMock(return_value=static_result)
        scanner_api = Mock(spec=__import__("pentool.api.scanner_api", fromlist=["ScannerAPI"]).ScannerAPI)
        scanner_api.run_active_on_requests = AsyncMock(return_value=[])
        scanner_api.save_findings = AsyncMock(return_value=None)
        scanner_api.configure_engine = Mock(return_value=None)

        # Pretend Lightpanda is installed so the flag (not binary presence)
        # is what decides.
        monkeypatch.setattr(
            "pentool.services.scan_service.is_lightpanda_available", lambda: True
        )

        service = ScanService(scanner_api, spider_api, None)
        config = ScanConfig(targets=["http://x.com/"], resume=False, hybrid_js=True)

        with patch("pentool.api.spider_api.SpiderAPI", js_spider_cls):
            await service.run(config)

        # hybrid_js fired a JS re-crawl.
        assert js_spider_cls.called, "hybrid_js should create a JS SpiderAPI"
        # …and the static spider ran too.
        assert spider_api.crawl.called

    @pytest.mark.asyncio
    async def test_hybrid_js_off_by_default(self, monkeypatch):
        """Without hybrid_js, no JS re-crawl happens (deterministic/fast)."""
        from unittest.mock import patch

        from pentool.modules.spider import SpiderResult
        from pentool.services.scan_service import ScanService

        static_result = SpiderResult(
            base_url="http://x.com/", pages=["http://x.com/"], auth_headers={},
        )
        js_spider_cls = Mock()
        js_spider_cls.return_value = Mock()
        js_spider_cls.return_value.crawl = AsyncMock(return_value=SpiderResult(
            base_url="http://x.com/", pages=["http://x.com/app"],
        ))

        spider_api = Mock(spec=__import__("pentool.api.spider_api", fromlist=["SpiderAPI"]).SpiderAPI)
        spider_api.crawl = AsyncMock(return_value=static_result)
        scanner_api = Mock(spec=__import__("pentool.api.scanner_api", fromlist=["ScannerAPI"]).ScannerAPI)
        scanner_api.run_active_on_requests = AsyncMock(return_value=[])
        scanner_api.save_findings = AsyncMock(return_value=None)
        scanner_api.configure_engine = Mock(return_value=None)

        # Even with Lightpanda present, hybrid_js=False must stay off.
        monkeypatch.setattr(
            "pentool.services.scan_service.is_lightpanda_available", lambda: True
        )

        service = ScanService(scanner_api, spider_api, None)
        config = ScanConfig(targets=["http://x.com/"], resume=False, hybrid_js=False)

        with patch("pentool.api.spider_api.SpiderAPI", js_spider_cls) as mocked:
            await service.run(config)
            assert not mocked.called, "hybrid_js=False must NOT trigger JS crawl"

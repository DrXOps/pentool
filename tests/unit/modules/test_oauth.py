"""Unit tests for pentool/modules/scanner/checks/oauth.py.

Part of plan-2026-08-09 section 2.5 coverage (step 1: capture existing
behavior with unit tests, no check code changes yet): OAuthCheck is a
global scan()-pipeline check (uses_scan_pipeline=False) with two passive
findings (missing state, implicit flow) and one active probe (open
redirect in redirect_uri, sent via http_client.send). We pin the current
behavior before any structural migration.
"""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock

pytest.importorskip("pentool.modules.scanner")

from pentool.modules.scanner.checks.oauth import OAuthCheck, _EVIL_REDIRECT, _is_oauth
from pentool.utils.parser import ParsedRequest, ParsedResponse


def _req(url: str) -> ParsedRequest:
    return ParsedRequest(method="GET", url=url, headers={}, body="")


class TestMeta:
    def test_name(self):
        assert OAuthCheck.name == "oauth"

    def test_uses_scan_pipeline_false(self):
        assert OAuthCheck.uses_scan_pipeline is False


class TestIsOauth:
    def test_oauth_path(self):
        assert _is_oauth(_req("http://target/oauth/authorize"))

    def test_oauth_param(self):
        assert _is_oauth(_req("http://target/redirect?client_id=abc"))

    def test_not_oauth(self):
        assert not _is_oauth(_req("http://target/health"))


class TestScanMissingState:
    @pytest.mark.asyncio
    async def test_missing_state_detected(self):
        check = OAuthCheck()
        req = _req("http://target/authorize?client_id=id&response_type=code")
        client = MagicMock()  # no network expected
        findings = await check.scan(req, None, client)
        assert any(f.type == "oauth" for f in findings)
        assert any("State" in f.name for f in findings)


class TestScanImplicitFlow:
    @pytest.mark.asyncio
    async def test_implicit_flow_detected(self):
        check = OAuthCheck()
        req = _req("http://target/authorize?client_id=id&response_type=token&redirect_uri=https://cb")
        # No state + implicit both fire; open-redirect path also runs send()
        # but we return a clean response, so only passive findings survive.
        client = MagicMock()
        client.send = AsyncMock(return_value=ParsedResponse(200, "OK", {}, "ok"))
        findings = await check.scan(req, None, client)
        assert any("Implicit Flow" in f.name for f in findings)


class TestScanOpenRedirect:
    @pytest.mark.asyncio
    async def test_open_redirect_detected_via_location(self):
        check = OAuthCheck()
        req = _req("http://target/authorize?client_id=id&redirect_uri=https://cb")
        client = MagicMock()
        client.send = AsyncMock(
            return_value=ParsedResponse(302, "Found", {"Location": _EVIL_REDIRECT}, "")
        )
        findings = await check.scan(req, None, client)
        assert any("Open Redirect" in f.name for f in findings)

    @pytest.mark.asyncio
    async def test_open_redirect_no_finding_on_clean_redirect(self):
        check = OAuthCheck()
        req = _req("http://target/authorize?client_id=id&redirect_uri=https://cb")
        client = MagicMock()
        client.send = AsyncMock(
            return_value=ParsedResponse(302, "Found", {"Location": "https://cb"}, "")
        )
        findings = await check.scan(req, None, client)
        assert not any("Open Redirect" in f.name for f in findings)


class TestScanNoOauth:
    @pytest.mark.asyncio
    async def test_non_oauth_returns_empty(self):
        check = OAuthCheck()
        req = _req("http://target/health")
        client = MagicMock()
        findings = await check.scan(req, None, client)
        assert findings == []


class TestEngineIntegration:
    """End-to-end through ScanEngine — passive missing-state finding surfaced."""

    @pytest.fixture(autouse=True)
    def _reset_session_license(self):
        import pentool.core.license as lic_mod
        saved = lic_mod._session_license
        lic_mod._session_license = None
        yield
        lic_mod._session_license = saved

    @pytest.mark.asyncio
    async def test_engine_detects_missing_state(self):
        from pentool.modules.scanner.engine import ScanEngine

        class FakeClient:
            async def send(self, request):
                return ParsedResponse(200, "OK", {}, "ok")

            async def get(self, url, headers=None):
                return ParsedResponse(200, "OK", {}, "ok")

        engine = ScanEngine(db_path=":memory:", http_client=FakeClient())
        engine.register_check(OAuthCheck())
        req = _req("http://target/authorize?client_id=id&response_type=code")
        findings = await engine.run_active_on_requests([req])
        assert any(f.type == "oauth" for f in findings)

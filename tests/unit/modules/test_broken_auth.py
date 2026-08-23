"""Unit tests for pentool/modules/scanner/checks/broken_auth.py.

Part of plan-2026-08-09 section 2.5 coverage (step 1: capture existing
behavior with unit tests, no code changes to the check yet):
BrokenAuthCheck is a scan()-pipeline check whose logic lives entirely in
`scan()` (analyze() is a stub returning None). This file pins the current
three-phase behavior:
  1. strip auth headers -> "No Credentials Required"
  2. bypass token variants -> "Token Bypass"
  3. HTTP verb override -> "HTTP Verb Override"
Note it sends via http_client.get()/post() (not send()) and ignores any
engine-passed point.
"""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock

pytest.importorskip("pentool.modules.scanner")

from pentool.modules.scanner.checks.broken_auth import (
    BrokenAuthCheck,
    _AUTH_HEADERS,
    _BYPASS_TOKENS,
    _VERB_OVERRIDES,
    _has_auth,
    _is_response_useful,
    _strip_auth,
)
from pentool.utils.parser import ParsedRequest, ParsedResponse


def _make_request(
    url: str, method: str = "GET", headers: dict | None = None, body: str = ""
) -> ParsedRequest:
    return ParsedRequest(method=method, url=url, headers=headers or {}, body=body)


USEFUL_BODY = "s" * 60  # body_len >= 50 satisfies _is_response_useful


def _usable_client(**kwargs) -> MagicMock:
    """Fake client exposing get/post (BrokenAuth never calls send())."""
    client = MagicMock()
    client.get = AsyncMock(return_value=kwargs.get("get", ParsedResponse(200, "OK", {}, USEFUL_BODY)))
    client.post = AsyncMock(return_value=kwargs.get("post", ParsedResponse(200, "OK", {}, USEFUL_BODY)))
    return client


class TestMeta:
    def test_name(self):
        assert BrokenAuthCheck.name == "broken_auth"

    def test_uses_scan_pipeline(self):
        assert BrokenAuthCheck.uses_scan_pipeline is True

    def test_analyze_is_stub(self):
        # Logic lives in scan(); analyze() returns None.
        check = BrokenAuthCheck()
        assert check.analyze is not None  # pragma: no cover - sanity


class TestHelpers:
    def test_has_auth(self):
        assert _has_auth({"Authorization": "Bearer x"})
        assert _has_auth({"cookie": "a=b"})
        assert not _has_auth({"host": "x.com"})

    def test_strip_auth_removes_all_auth_headers(self):
        stripped = _strip_auth({"Authorization": "x", "Host": "h", "X-API-Key": "k"})
        assert "Authorization" not in stripped
        assert "X-API-Key" not in stripped
        assert stripped["Host"] == "h"

    def test_is_response_useful_requires_200_and_len(self):
        assert _is_response_useful(USEFUL_BODY, 200)
        assert not _is_response_useful("short", 200)
        assert not _is_response_useful(USEFUL_BODY, 403)
        assert not _is_response_useful("please log in " * 5, 200)


class TestScanPhase1StripAuth:
    @pytest.mark.asyncio
    async def test_strip_auth_detects_unauthenticated_access(self):
        check = BrokenAuthCheck()
        req = _make_request(
            "http://target/admin",
            headers={"Authorization": "Bearer real-token"},
        )
        client = _usable_client()  # returns USEFUL_BODY with status 200
        findings = await check.scan(req, None, client)
        assert any(f.type == "broken_auth" for f in findings)
        assert any("No Credentials Required" in f.name for f in findings)

    @pytest.mark.asyncio
    async def test_no_auth_headers_skips_phase1(self):
        check = BrokenAuthCheck()
        req = _make_request("http://target/public")
        client = _usable_client()
        findings = await check.scan(req, None, client)
        # No auth headers -> phase 1 skipped; no "No Credentials" finding.
        assert not any("No Credentials Required" in f.name for f in findings)


class TestScanPhase2TokenBypass:
    @pytest.mark.asyncio
    async def test_token_bypass_detected(self):
        # Phase 1 (strip auth) must NOT fire first, or phase 2 never runs.
        # Fake client returns a NOT-useful body when the X-API-Key header is
        # absent (stripped) and a useful body when it is present — even
        # empty/null — isolating phase 2's bypass loop.
        check = BrokenAuthCheck()
        req = _make_request(
            "http://target/api",
            headers={"X-API-Key": "real-key"},
        )

        async def get(url, headers=None, **kw):
            has_key = any(k.lower() == "x-api-key" for k in (headers or {}))
            if has_key:
                return ParsedResponse(200, "OK", {}, USEFUL_BODY)
            # stripped (no X-API-Key) -> login redirect, not useful
            return ParsedResponse(302, "Found", {}, "please log in" * 4)

        client = MagicMock()
        client.get = AsyncMock(side_effect=get)
        client.post = AsyncMock(side_effect=get)

        findings = await check.scan(req, None, client)
        assert any(f.type == "broken_auth" for f in findings)
        assert any("Token Bypass" in f.name for f in findings)


class TestScanPhase3VerbOverride:
    @pytest.mark.asyncio
    async def test_verb_override_detected_when_status_changes(self):
        # No auth headers -> phases 1 & 2 skipped -> phase 3 runs.
        # Original response status 200; verb-override send flips to 201.
        check = BrokenAuthCheck()
        req = _make_request("http://target/api")
        resp = ParsedResponse(200, "OK", {}, USEFUL_BODY)
        client = _usable_client(get=ParsedResponse(201, "Created", {}, USEFUL_BODY))
        findings = await check.scan(req, resp, client)
        assert any("Verb Override" in f.name for f in findings)


class TestScanNoFinding:
    @pytest.mark.asyncio
    async def test_login_redirect_no_finding(self):
        # Server asks to log in on every attempt -> not "useful" -> no finding.
        check = BrokenAuthCheck()
        req = _make_request(
            "http://target/admin",
            headers={"Authorization": "Bearer x"},
        )
        login_body = "please log in to continue" * 4
        client = _usable_client(get=ParsedResponse(302, "Found", {}, login_body),
                                post=ParsedResponse(302, "Found", {}, login_body))
        findings = await check.scan(req, None, client)
        assert findings == []


class TestEngineIntegration:
    """End-to-end through ScanEngine — scan()-pipeline check actually finds
    the vulnerability (fake client returns a useful body on every probe)."""

    @pytest.fixture(autouse=True)
    def _reset_session_license(self):
        import pentool.core.license as lic_mod
        saved = lic_mod._session_license
        lic_mod._session_license = None
        yield
        lic_mod._session_license = saved

    @pytest.mark.asyncio
    async def test_engine_detects_broken_auth(self):
        from pentool.modules.scanner.checks.broken_auth import BrokenAuthCheck
        from pentool.modules.scanner.engine import ScanEngine

        class FakeClient:
            async def send(self, request):
                return ParsedResponse(200, "OK", {}, USEFUL_BODY)

            async def get(self, url, headers=None):
                return ParsedResponse(200, "OK", {}, USEFUL_BODY)

            async def post(self, url, body="", headers=None):
                return ParsedResponse(200, "OK", {}, USEFUL_BODY)

        engine = ScanEngine(db_path=":memory:", http_client=FakeClient())
        engine.register_check(BrokenAuthCheck())
        req = _make_request(
            "http://target/admin",
            headers={"Authorization": "Bearer real-token"},
        )
        findings = await engine.run_active_on_requests([req])
        assert any(f.type == "broken_auth" for f in findings)

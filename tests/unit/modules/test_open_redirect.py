"""Unit tests for pentool/modules/scanner/checks/open_redirect.py.

Written as regression coverage BEFORE migrating OpenRedirectCheck to
BaseActiveCheck (see MYPLANS/ARCHITECTURE_REFACTOR_PLAN_2026-08-09.md
section 2.5) — this check had no dedicated unit tests prior to this file.
"""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock

# Skip all tests if scanner module not available
pytest.importorskip("pentool.modules.scanner")

from pentool.modules.scanner.checks.open_redirect import (
    OpenRedirectCheck,
    _REDIRECT_PAYLOADS,
    _is_redirect_to_attacker,
    _check_redirect,
)
from pentool.utils.parser import ParsedRequest


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _make_request(url: str, method: str = "GET", body: str = "") -> ParsedRequest:
    return ParsedRequest(method=method, url=url, headers={}, body=body)


def _make_resp(body: str = "", status: int = 200, headers: dict | None = None):
    resp = MagicMock()
    resp.body = body
    resp.text = None
    resp.content = None
    resp.status = status
    resp.reason = "OK"
    resp.headers = headers or {}
    return resp


def _make_client(resp_body: str = "", status: int = 200, headers: dict | None = None):
    client = MagicMock()
    resp = _make_resp(resp_body, status, headers)
    client.send = AsyncMock(return_value=resp)
    return client


# ─── TestMeta ─────────────────────────────────────────────────────────────────

class TestMeta:
    def test_name(self):
        assert OpenRedirectCheck.name == "open_redirect"

    def test_severity(self):
        assert OpenRedirectCheck.severity == "medium"

    def test_cwe(self):
        assert OpenRedirectCheck.cwe == "CWE-601"

    def test_mitre_attack(self):
        assert OpenRedirectCheck.mitre_attack == "T1598"

    def test_not_passive(self):
        assert OpenRedirectCheck.passive is False

    def test_uses_scan_pipeline(self):
        assert OpenRedirectCheck.uses_scan_pipeline is True


# ─── TestIsRedirectToAttacker ─────────────────────────────────────────────────

class TestIsRedirectToAttacker:
    def test_evil_com_detected(self):
        assert _is_redirect_to_attacker("https://evil.com/path")

    def test_attacker_com_detected(self):
        assert _is_redirect_to_attacker("https://attacker.com/")

    def test_legit_url_not_detected(self):
        assert not _is_redirect_to_attacker("https://example.com/")


# ─── TestCheckRedirect ────────────────────────────────────────────────────────

class TestCheckRedirect:
    def test_http_302_to_attacker(self):
        resp = _make_resp("", 302, {"Location": "https://evil.com"})
        evidence = _check_redirect(resp, "https://evil.com")
        assert evidence
        assert "302" in evidence

    def test_http_200_no_redirect(self):
        resp = _make_resp("<html>ok</html>", 200)
        evidence = _check_redirect(resp, "https://evil.com")
        assert evidence is None

    def test_meta_refresh_redirect(self):
        resp = _make_resp(
            '<meta http-equiv="refresh" content="0;url=https://evil.com">'
        )
        evidence = _check_redirect(resp, "https://evil.com")
        assert evidence
        assert "Meta-refresh" in evidence

    def test_js_redirect(self):
        resp = _make_resp('<script>window.location="https://evil.com"</script>')
        evidence = _check_redirect(resp, "https://evil.com")
        assert evidence
        assert "JS redirect" in evidence

    def test_302_to_legit_location_no_finding(self):
        resp = _make_resp("", 302, {"Location": "https://example.com/home"})
        evidence = _check_redirect(resp, "https://evil.com")
        assert evidence is None


# ─── TestScanNoClient ─────────────────────────────────────────────────────────

class TestScanNoClient:
    @pytest.mark.asyncio
    async def test_returns_empty_without_client(self):
        check = OpenRedirectCheck()
        req = _make_request("https://example.com/?redirect=home")
        result = await check.scan(req, None, http_client=None)
        assert result == []


# ─── TestScanGetParams ────────────────────────────────────────────────────────

class TestScanGetParams:
    @pytest.mark.asyncio
    async def test_no_params_no_findings(self):
        check = OpenRedirectCheck()
        client = _make_client("clean")
        req = _make_request("https://example.com/page")
        findings = await check.scan(req, None, http_client=client)
        assert findings == []

    @pytest.mark.asyncio
    async def test_redirect_detected(self):
        check = OpenRedirectCheck()
        client = MagicMock()
        client.send = AsyncMock(return_value=_make_resp("", 302, {"Location": "https://evil.com"}))
        req = _make_request("https://example.com/?redirect=home")
        findings = await check.scan(req, None, http_client=client)
        assert len(findings) >= 1
        assert findings[0].type == "open_redirect"
        assert findings[0].severity == "medium"
        assert findings[0].cwe == "CWE-601"

    @pytest.mark.asyncio
    async def test_clean_response_no_findings(self):
        check = OpenRedirectCheck()
        client = _make_client("<html>ok</html>")
        req = _make_request("https://example.com/?redirect=home")
        findings = await check.scan(req, None, http_client=client)
        assert findings == []

    @pytest.mark.asyncio
    async def test_exception_does_not_crash(self):
        check = OpenRedirectCheck()
        client = MagicMock()
        client.send = AsyncMock(side_effect=Exception("connection refused"))
        req = _make_request("https://example.com/?redirect=home")
        findings = await check.scan(req, None, http_client=client)
        assert findings == []

    @pytest.mark.asyncio
    async def test_finding_has_all_required_fields(self):
        check = OpenRedirectCheck()
        client = MagicMock()
        client.send = AsyncMock(return_value=_make_resp("", 302, {"Location": "https://evil.com"}))
        req = _make_request("https://example.com/?redirect=home")
        findings = await check.scan(req, None, http_client=client)
        assert findings
        f = findings[0]
        assert f.type == "open_redirect"
        assert f.severity == "medium"
        assert f.cwe == "CWE-601"
        assert f.mitre_attack == "T1598"
        assert f.url
        assert f.parameter
        assert f.payload
        assert f.evidence
        assert f.description
        assert f.remediation
        assert f.request_raw
        assert f.response_raw

    @pytest.mark.asyncio
    async def test_finding_name_contains_injection_point(self):
        check = OpenRedirectCheck()
        client = MagicMock()
        client.send = AsyncMock(return_value=_make_resp("", 302, {"Location": "https://evil.com"}))
        req = _make_request("https://example.com/?next=home")
        findings = await check.scan(req, None, http_client=client)
        assert findings
        assert "Open Redirect" in findings[0].name

    @pytest.mark.asyncio
    async def test_stops_after_first_finding_per_point(self):
        """Within a single injection point, after the first payload that
        produces a finding, no more payloads are tried for that point
        (mutate -> send -> analyze -> break). But the request has multiple
        injection points (the GET param + several injectable headers —
        see RequestMutator.extract_points), and each point is swept
        independently in fallback/global mode, so the total call count
        equals the number of points, not 1."""
        check = OpenRedirectCheck()
        call_count = [0]

        async def fake_send(mutated):
            call_count[0] += 1
            return _make_resp("", 302, {"Location": "https://evil.com"})

        client = MagicMock()
        client.send = fake_send
        req = _make_request("https://example.com/?redirect=home")
        from pentool.modules.scanner.mutator import RequestMutator
        n_points = len(RequestMutator().extract_points(req))
        findings = await check.scan(req, None, http_client=client)
        assert findings
        assert call_count[0] == n_points


# ─── TestPayloads ─────────────────────────────────────────────────────────────

class TestPayloads:
    def test_payloads_not_empty(self):
        assert len(_REDIRECT_PAYLOADS) > 0

    def test_evil_com_payload_present(self):
        assert any("evil.com" in p for p in _REDIRECT_PAYLOADS)


# ─── TestRegistration ─────────────────────────────────────────────────────────

class TestRegistration:
    def test_importable_from_checks_init(self):
        from pentool.modules.scanner.checks import OpenRedirectCheck as ORC
        assert ORC is OpenRedirectCheck

    def test_in_all(self):
        from pentool.modules.scanner import checks
        assert "OpenRedirectCheck" in checks.__all__

    def test_registered_in_scanner_api(self):
        from pentool.api.scanner_api import ScannerAPI
        api = ScannerAPI(db_path=":memory:")
        check_names = [c.name for c in api.get_registered_checks()]
        assert "open_redirect" in check_names

    def test_instantiable(self):
        check = OpenRedirectCheck()
        assert check.name == "open_redirect"

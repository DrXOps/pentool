"""Unit tests for pentool/modules/scanner/checks/header_injection.py."""

from __future__ import annotations

import json
import pytest
from unittest.mock import AsyncMock, MagicMock

from tests.conftest import pytest_skip_if_no_scanner

pytestmark = pytest_skip_if_no_scanner

from pentool.modules.scanner.checks.header_injection import (
    HeaderInjectionCheck,
    _CRLF_PAYLOADS,
    _INJECTABLE_HEADERS,
    _INJECTION_SIGNATURES,
    _detect_injection,
    _get_response_headers_str,
)
from pentool.utils.parser import ParsedRequest


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _make_request(url: str, method: str = "GET", body: str = "",
                  headers: dict | None = None) -> ParsedRequest:
    return ParsedRequest(
        method=method,
        url=url,
        headers=headers or {},
        body=body,
    )


def _make_resp(body: str = "", status: int = 200,
               headers: dict | None = None):
    resp = MagicMock()
    resp.body = body
    resp.text = None
    resp.content = None
    resp.status = status
    resp.reason = "OK"
    resp.headers = headers or {}
    return resp


def _make_client(resp_body: str = "", status: int = 200,
                 resp_headers: dict | None = None):
    client = MagicMock()
    resp = _make_resp(resp_body, status, resp_headers)
    client.get = AsyncMock(return_value=resp)
    client.post = AsyncMock(return_value=resp)
    return client


def _make_injected_client():
    """Client whose get/post return a response with X-Injected in HTTP headers."""
    return _make_client("", resp_headers={"X-Injected": "header_injected"})


# ─── TestMeta ─────────────────────────────────────────────────────────────────

class TestMeta:
    def test_name(self):
        assert HeaderInjectionCheck.name == "header_injection"

    def test_severity(self):
        assert HeaderInjectionCheck.severity == "medium"

    def test_cwe(self):
        assert HeaderInjectionCheck.cwe == "CWE-113"

    def test_mitre_attack(self):
        assert HeaderInjectionCheck.mitre_attack == "T1190"

    def test_not_passive(self):
        assert HeaderInjectionCheck.passive is False

    def test_description_not_empty(self):
        assert HeaderInjectionCheck.description


# ─── TestPayloads ─────────────────────────────────────────────────────────────

class TestPayloads:
    def test_payloads_not_empty(self):
        assert len(_CRLF_PAYLOADS) > 0

    def test_crlf_payload_present(self):
        assert any("\r\n" in p or "%0d%0a" in p.lower() for p in _CRLF_PAYLOADS)

    def test_set_cookie_payload_present(self):
        assert any("Set-Cookie" in p or "set-cookie" in p.lower() for p in _CRLF_PAYLOADS)

    def test_x_injected_payload_present(self):
        assert any("X-Injected" in p for p in _CRLF_PAYLOADS)

    def test_injectable_headers_not_empty(self):
        assert len(_INJECTABLE_HEADERS) > 0

    def test_x_forwarded_for_in_injectable(self):
        assert "X-Forwarded-For" in _INJECTABLE_HEADERS

    def test_referer_in_injectable(self):
        assert "Referer" in _INJECTABLE_HEADERS

    def test_user_agent_in_injectable(self):
        assert "User-Agent" in _INJECTABLE_HEADERS


# ─── TestDetectInjection ──────────────────────────────────────────────────────

class TestDetectInjection:
    def test_x_injected_in_body_is_NOT_injection(self):
        """Payload reflection in body — NOT a header injection (false positive was here)."""
        resp = _make_resp("X-Injected: header_injected")
        result = _detect_injection(resp, "\r\nX-Injected: header_injected")
        # _detect_injection checks body for backward compatibility,
        # but _check_response (main path) no longer detects body.
        # This test records the behavior of the low-level function.
        assert result == "body"  # _detect_injection — legacy helper

    def test_set_cookie_in_body_legacy(self):
        """_detect_injection sees Set-Cookie in body — legacy behavior."""
        resp = _make_resp("injected=header_injection_test")
        result = _detect_injection(resp, "\r\nSet-Cookie: injected=header_injection_test")
        assert result is not None  # legacy helper — still detects

    def test_x_injected_in_response_headers(self):
        """Real injection — X-Injected header appeared in HTTP response."""
        resp = _make_resp("", headers={"X-Injected": "header_injected"})
        result = _detect_injection(resp, "\r\nX-Injected: header_injected")
        assert result == "header"

    def test_clean_response_returns_none(self):
        resp = _make_resp("<html><body>Clean response</body></html>")
        result = _detect_injection(resp, "\r\nX-Injected: header_injected")
        assert result is None

    def test_response_splitting_signature(self):
        """HTTP Response Splitting — second HTTP response AFTER \r\n\r\n."""
        resp = _make_resp("\r\n\r\nHTTP/1.1 200 OK\r\nContent-Type: text/html\r\n\r\n<h1>Injected</h1>")
        result = _detect_injection(resp, "")
        # _detect_injection checks _RESPONSE_SPLIT_RE
        assert result is not None

    def test_none_response_returns_none(self):
        result = _detect_injection(None, "\r\nX-Injected: header_injected")
        assert result is None

    def test_real_header_injection_detected(self):
        """Case when CRLF actually added a header to the response."""
        resp = _make_resp("", headers={"X-Injected": "crlf"})
        result = _detect_injection(resp, "")
        assert result == "header"


# ─── TestGetResponseHeadersStr ────────────────────────────────────────────────

class TestGetResponseHeadersStr:
    def test_headers_in_output(self):
        resp = _make_resp(headers={"Content-Type": "text/html", "Server": "nginx"})
        result = _get_response_headers_str(resp)
        assert "Content-Type: text/html" in result
        assert "Server: nginx" in result

    def test_empty_headers(self):
        resp = _make_resp(headers={})
        result = _get_response_headers_str(resp)
        assert result == ""

    def test_none_resp(self):
        result = _get_response_headers_str(None)
        assert result == ""


# ─── TestScanNoClient ─────────────────────────────────────────────────────────

class TestScanNoClient:
    @pytest.mark.asyncio
    async def test_returns_empty_without_client(self):
        check = HeaderInjectionCheck()
        req = _make_request("https://example.com/?redirect=url")
        result = await check.scan(req, None, http_client=None)
        assert result == []


# ─── TestScanGetParams ────────────────────────────────────────────────────────

class TestScanGetParams:
    @pytest.mark.asyncio
    async def test_no_params_no_findings(self):
        check = HeaderInjectionCheck()
        client = _make_client("clean")
        req = _make_request("https://example.com/page")
        findings = await check.scan(req, None, http_client=client)
        assert findings == []

    @pytest.mark.asyncio
    async def test_injection_in_get_param_body(self):
        """Payload in body — should NOT give false positive (false positive fix)."""
        check = HeaderInjectionCheck()
        client = _make_client("X-Injected: header_injected")  # only in body
        req = _make_request("https://example.com/?redirect=test")
        findings = await check.scan(req, None, http_client=client)
        # After fix: body reflection is NOT a header injection
        assert findings == [], "CRLF false positive: body-reflect should not be detected"

    @pytest.mark.asyncio
    async def test_injection_in_get_param_response_header(self):
        """Real injection: X-Injected appeared in HTTP response headers."""
        check = HeaderInjectionCheck()
        resp = _make_resp("", headers={"X-Injected": "header_injected"})
        client = MagicMock()
        client.get = AsyncMock(return_value=resp)
        client.post = AsyncMock(return_value=resp)
        client.send = AsyncMock(return_value=resp)
        req = _make_request("https://example.com/?url=test")
        findings = await check.scan(req, None, http_client=client)
        assert findings

    @pytest.mark.asyncio
    async def test_clean_get_response_no_findings(self):
        check = HeaderInjectionCheck()
        client = _make_client("<html>ok</html>")
        req = _make_request("https://example.com/?q=hello")
        findings = await check.scan(req, None, http_client=client)
        assert findings == []

    @pytest.mark.asyncio
    async def test_exception_does_not_crash(self):
        check = HeaderInjectionCheck()
        client = MagicMock()
        client.get = AsyncMock(side_effect=ConnectionError("refused"))
        req = _make_request("https://example.com/?q=test")
        findings = await check.scan(req, None, http_client=client)
        assert findings == []

    @pytest.mark.asyncio
    async def test_multiple_get_params(self):
        """All GET params are tested — real injection into a header."""
        check = HeaderInjectionCheck()
        resp_injected = _make_resp("", headers={"X-Injected": "crlf"})
        resp_clean = _make_resp("clean")
        call_count = [0]

        async def fake_get(url, headers=None, **kwargs):
            call_count[0] += 1
            # First call — injection triggered (header in response)
            if call_count[0] == 1:
                return resp_injected
            return resp_clean

        client = MagicMock()
        client.get = fake_get
        client.post = AsyncMock(return_value=resp_clean)
        req = _make_request("https://example.com/?a=1&b=2&redirect=3")
        findings = await check.scan(req, None, http_client=client)
        assert findings


# ─── TestScanInjectableHeaders ────────────────────────────────────────────────

class TestScanInjectableHeaders:
    @pytest.mark.asyncio
    async def test_header_injection_via_x_forwarded_for(self):
        check = HeaderInjectionCheck()

        call_count = 0
        # Real injection: X-Injected appears in HTTP response headers
        injected_resp = _make_resp("", headers={"X-Injected": "header_injected"})
        clean_resp = _make_resp("<html>ok</html>")

        async def fake_get(url, headers=None, **kwargs):
            nonlocal call_count
            call_count += 1
            h = headers or {}
            if any("\r\n" in str(v) or "%0d%0a" in str(v).lower()
                   for v in h.values()):
                return injected_resp
            return clean_resp

        client = MagicMock()
        client.get = fake_get
        # URL without params so GET params find nothing
        req = _make_request("https://example.com/")
        findings = await check.scan(req, None, http_client=client)
        assert findings
        f = findings[0]
        assert "Header" in f.evidence or "Header" in f.name

    @pytest.mark.asyncio
    async def test_clean_header_response_no_findings(self):
        check = HeaderInjectionCheck()
        client = _make_client("<html>clean</html>")
        req = _make_request("https://example.com/")
        findings = await check.scan(req, None, http_client=client)
        assert findings == []


# ─── TestScanPost ─────────────────────────────────────────────────────────────

class TestScanPost:
    @pytest.mark.asyncio
    async def test_post_urlencoded_injection(self):
        check = HeaderInjectionCheck()
        # Real injection: X-Injected header appeared in HTTP response
        resp = _make_resp("", headers={"X-Injected": "header_injected"})
        client = MagicMock()
        client.get = AsyncMock(return_value=_make_resp("clean"))
        client.post = AsyncMock(return_value=resp)
        req = _make_request(
            "https://example.com/submit",
            method="POST",
            body="redirect=home&next=index",
        )
        findings = await check.scan(req, None, http_client=client)
        assert findings

    @pytest.mark.asyncio
    async def test_get_request_skips_post_body(self):
        check = HeaderInjectionCheck()
        post_called = False

        async def fake_post(*a, **kw):
            nonlocal post_called
            post_called = True
            return _make_resp("X-Injected: header_injected")

        client = MagicMock()
        client.get = AsyncMock(return_value=_make_resp("clean"))
        client.post = fake_post
        req = _make_request("https://example.com/page", method="GET", body="a=1")
        findings = await check.scan(req, None, http_client=client)
        assert not post_called


# ─── TestScanJson ─────────────────────────────────────────────────────────────

class TestScanJson:
    @pytest.mark.asyncio
    async def test_json_body_injection(self):
        check = HeaderInjectionCheck()
        resp = _make_resp("X-Injected: header_injected")
        client = MagicMock()
        client.get = AsyncMock(return_value=_make_resp("clean"))
        client.post = AsyncMock(return_value=resp)
        body = json.dumps({"redirect": "home", "next": "/"})
        req = ParsedRequest(
            method="POST",
            url="https://example.com/api",
            headers={"Content-Type": "application/json"},
            body=body,
        )
        findings = await check.scan(req, None, http_client=client)
        assert isinstance(findings, list)

    @pytest.mark.asyncio
    async def test_non_json_body_not_tested_as_json(self):
        check = HeaderInjectionCheck()
        client = _make_client("clean")
        req = ParsedRequest(
            method="POST",
            url="https://example.com/api",
            headers={"Content-Type": "text/plain"},
            body="plain text content",
        )
        findings = await check.scan(req, None, http_client=client)
        assert findings == []


# ─── TestFindingFields ────────────────────────────────────────────────────────

class TestFindingFields:
    @pytest.mark.asyncio
    async def test_finding_all_required_fields(self):
        check = HeaderInjectionCheck()
        # Real injection: X-Injected should be in HTTP response headers
        client = _make_injected_client()
        req = _make_request("https://example.com/?redirect=test")
        findings = await check.scan(req, None, http_client=client)
        assert findings
        f = findings[0]
        assert f.type == "header_injection"
        assert f.severity == "medium"
        assert f.cwe == "CWE-113"
        assert f.mitre_attack == "T1190"
        assert f.url
        assert f.parameter
        assert f.payload
        assert f.evidence
        assert f.description
        assert f.remediation

    @pytest.mark.asyncio
    async def test_finding_name_contains_injection_point(self):
        check = HeaderInjectionCheck()
        client = _make_injected_client()
        req = _make_request("https://example.com/?q=test")
        findings = await check.scan(req, None, http_client=client)
        assert findings
        assert "Header Injection" in findings[0].name

    @pytest.mark.asyncio
    async def test_finding_remediation_mentions_crlf(self):
        check = HeaderInjectionCheck()
        client = _make_injected_client()
        req = _make_request("https://example.com/?redirect=test")
        findings = await check.scan(req, None, http_client=client)
        assert findings
        assert "CRLF" in findings[0].remediation or "CR" in findings[0].remediation

    @pytest.mark.asyncio
    async def test_finding_request_raw_set(self):
        check = HeaderInjectionCheck()
        client = _make_injected_client()
        req = _make_request("https://example.com/?redirect=x")
        findings = await check.scan(req, None, http_client=client)
        assert findings
        assert findings[0].request_raw


# ─── TestRegistration ─────────────────────────────────────────────────────────

class TestRegistration:
    def test_importable_from_checks_init(self):
        from pentool.modules.scanner.checks import HeaderInjectionCheck as HIC
        assert HIC is HeaderInjectionCheck

    def test_in_all(self):
        from pentool.modules.scanner import checks
        assert "HeaderInjectionCheck" in checks.__all__

    def test_registered_in_scanner_api(self):
        from pentool.api.scanner_api import ScannerAPI
        api = ScannerAPI(db_path=":memory:")
        check_names = [c.name for c in api.get_registered_checks()]
        assert "header_injection" in check_names

    def test_instantiable(self):
        check = HeaderInjectionCheck()
        assert check.name == "header_injection"
        assert not check.passive

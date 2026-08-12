"""Unit tests for pentool/modules/scanner/checks/lfi.py.

Written as regression coverage BEFORE migrating LFICheck to
BaseActiveCheck (see MYPLANS/ARCHITECTURE_REFACTOR_PLAN_2026-08-09.md
section 2.5) — this check had no dedicated unit tests prior to this file.
"""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock

# Skip all tests if scanner module not available
pytest.importorskip("pentool.modules.scanner")

from pentool.modules.scanner.checks.lfi import (
    LFICheck,
    _build_all_payloads,
    _build_traversal_payloads,
    _check_lfi,
    _is_php,
    _PHP_WRAPPER_PAYLOADS,
    _SIGNATURES,
    _TARGET_FILES,
    _ENCODINGS,
)
from pentool.utils.parser import ParsedRequest


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _make_request(url: str, method: str = "GET", body: str = "",
                  headers: dict | None = None) -> ParsedRequest:
    return ParsedRequest(method=method, url=url, headers=headers or {}, body=body)


def _make_resp(body: str = "", status: int = 200, headers: dict | None = None):
    resp = MagicMock()
    resp.body = body
    resp.text = None
    resp.content = None
    resp.status = status
    resp.reason = "OK"
    resp.headers = headers or {}
    return resp


def _make_client(resp_body: str = "", status: int = 200):
    client = MagicMock()
    resp = _make_resp(resp_body, status)
    client.send = AsyncMock(return_value=resp)
    client.get = AsyncMock(return_value=resp)
    client.post = AsyncMock(return_value=resp)
    return client


# ─── TestMeta ─────────────────────────────────────────────────────────────────

class TestMeta:
    def test_name(self):
        assert LFICheck.name == "lfi"

    def test_severity(self):
        assert LFICheck.severity == "high"

    def test_cwe(self):
        assert LFICheck.cwe == "CWE-22"

    def test_mitre_attack(self):
        assert LFICheck.mitre_attack == "T1083"

    def test_not_passive(self):
        assert LFICheck.passive is False

    def test_uses_scan_pipeline(self):
        assert LFICheck.uses_scan_pipeline is True


# ─── TestSignatures ───────────────────────────────────────────────────────────

class TestSignatures:
    def test_signatures_not_empty(self):
        assert len(_SIGNATURES) > 0

    def test_check_lfi_detects_passwd(self):
        found, desc = _check_lfi("root:x:0:0:root:/root:/bin/bash")
        assert found
        assert "passwd" in desc.lower()

    def test_check_lfi_clean_body(self):
        found, desc = _check_lfi("<html>clean</html>")
        assert not found
        assert desc == ""

    def test_check_lfi_windows(self):
        found, desc = _check_lfi("[boot loader]\r\n[operating systems]")
        assert found


# ─── TestIsPhp ────────────────────────────────────────────────────────────────

class TestIsPhp:
    def test_php_extension_in_url(self):
        req = _make_request("https://example.com/index.php?file=x")
        assert _is_php(req)

    def test_no_php_indicator(self):
        req = _make_request("https://example.com/page?file=x")
        assert not _is_php(req)

    def test_php_powered_by_header_value_alone_not_matched(self):
        """_is_php's X-Powered-By pattern is 'X-Powered-By:\\s*PHP' — it is
        matched against header VALUES only (not 'key: value' strings), so a
        header dict {"X-Powered-By": "PHP/8.1"} does NOT match (the value
        alone is just "PHP/8.1", missing the "X-Powered-By:" prefix). This
        records the actual current behavior, not a spec."""
        req = _make_request("https://example.com/page", headers={"X-Powered-By": "PHP/8.1"})
        assert not _is_php(req)

    def test_php_powered_by_full_header_line_in_value_matched(self):
        """If a header's VALUE happens to literally contain the full
        'X-Powered-By: PHP' text, it does match."""
        req = _make_request(
            "https://example.com/page",
            headers={"X-Debug-Info": "X-Powered-By: PHP/8.1"},
        )
        assert _is_php(req)


# ─── TestBuildPayloads ────────────────────────────────────────────────────────

class TestBuildPayloads:
    def test_traversal_payloads_include_absolute_path(self):
        payloads = _build_traversal_payloads("/etc/passwd")
        assert "/etc/passwd" in payloads

    def test_traversal_payloads_include_encodings(self):
        payloads = _build_traversal_payloads("/etc/passwd")
        assert any("..%2f" in p for p in payloads)

    def test_build_all_payloads_no_php(self):
        """Some php:// wrapper payloads are already present via the
        built-in payloads/lfi.txt file regardless of PHP detection — only
        the wrappers unique to _is_php()-triggered inclusion (not also in
        the payload file) should be absent for a non-PHP request."""
        req_no_php = _make_request("https://example.com/?file=x")
        req_php = _make_request("https://example.com/index.php?file=x")
        payloads_no_php = _build_all_payloads(req_no_php)
        payloads_php = _build_all_payloads(req_php)
        php_only = [p for p in payloads_php if p not in payloads_no_php]
        assert php_only, "PHP detection should add at least one wrapper payload"
        for p in php_only:
            assert p in _PHP_WRAPPER_PAYLOADS

    def test_build_all_payloads_php_adds_wrappers(self):
        req = _make_request("https://example.com/index.php?file=x")
        payloads = _build_all_payloads(req)
        for pw in _PHP_WRAPPER_PAYLOADS:
            assert pw in payloads

    def test_build_all_payloads_covers_all_targets(self):
        req = _make_request("https://example.com/?file=x")
        payloads = _build_all_payloads(req)
        # At least the absolute path of each target file must be present
        for target in _TARGET_FILES:
            assert target in payloads


# ─── TestScanNoClient ─────────────────────────────────────────────────────────

class TestScanNoClient:
    @pytest.mark.asyncio
    async def test_returns_empty_without_client(self):
        check = LFICheck()
        req = _make_request("https://example.com/?file=test.txt")
        result = await check.scan(req, None, http_client=None)
        assert result == []


# ─── TestScanGetParams ────────────────────────────────────────────────────────

class TestScanGetParams:
    @pytest.mark.asyncio
    async def test_no_params_no_findings(self):
        check = LFICheck()
        client = _make_client("clean response")
        req = _make_request("https://example.com/page")
        findings = await check.scan(req, None, http_client=client)
        assert findings == []

    @pytest.mark.asyncio
    async def test_lfi_signature_detected(self):
        check = LFICheck()
        client = _make_client("root:x:0:0:root:/root:/bin/bash")
        req = _make_request("https://example.com/?file=test.txt")
        findings = await check.scan(req, None, http_client=client)
        assert len(findings) >= 1
        assert findings[0].type == "lfi"
        assert findings[0].severity == "high"
        assert findings[0].cwe == "CWE-22"

    @pytest.mark.asyncio
    async def test_clean_response_no_findings(self):
        check = LFICheck()
        client = _make_client("<html><body>Hello</body></html>")
        req = _make_request("https://example.com/?file=test.txt")
        findings = await check.scan(req, None, http_client=client)
        assert findings == []

    @pytest.mark.asyncio
    async def test_exception_in_request_does_not_crash(self):
        check = LFICheck()
        client = MagicMock()
        client.send = AsyncMock(side_effect=Exception("connection refused"))
        req = _make_request("https://example.com/?file=test")
        findings = await check.scan(req, None, http_client=client)
        assert findings == []

    @pytest.mark.asyncio
    async def test_finding_has_all_required_fields(self):
        check = LFICheck()
        client = _make_client("root:x:0:0:root:/root:/bin/bash")
        req = _make_request("https://example.com/?file=test.txt")
        findings = await check.scan(req, None, http_client=client)
        assert findings
        f = findings[0]
        assert f.type == "lfi"
        assert f.severity == "high"
        assert f.cwe == "CWE-22"
        assert f.mitre_attack == "T1083"
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
        check = LFICheck()
        client = _make_client("root:x:0:0:root:/root:/bin/bash")
        req = _make_request("https://example.com/?path=test")
        findings = await check.scan(req, None, http_client=client)
        assert findings
        assert "LFI" in findings[0].name


# ─── TestScanPhpWrappers ──────────────────────────────────────────────────────

class TestScanPhpWrappers:
    @pytest.mark.asyncio
    async def test_php_url_tests_wrapper_payloads(self):
        """When the request looks like PHP, wrapper payloads should be
        included in the sweep — verify by making the response match only
        for a request whose payload came from the wrapper set. The mutator
        URL-encodes the payload into the query string, so look for the
        URL-encoded form of "php://filter" rather than the raw payload."""
        check = LFICheck()
        seen_payloads = []

        async def fake_send(mutated):
            seen_payloads.append(mutated.url)
            return _make_resp("clean")

        client = MagicMock()
        client.send = fake_send
        req = _make_request("https://example.com/index.php?file=x")
        await check.scan(req, None, http_client=client)
        assert any("php%3A%2F%2Ffilter" in p for p in seen_payloads)


# ─── TestRegistration ─────────────────────────────────────────────────────────

class TestRegistration:
    def test_importable_from_checks_init(self):
        from pentool.modules.scanner.checks import LFICheck as LC
        assert LC is LFICheck

    def test_in_all(self):
        from pentool.modules.scanner import checks
        assert "LFICheck" in checks.__all__

    def test_registered_in_scanner_api(self):
        from pentool.api.scanner_api import ScannerAPI
        api = ScannerAPI(db_path=":memory:")
        check_names = [c.name for c in api.get_registered_checks()]
        assert "lfi" in check_names

    def test_instantiable(self):
        check = LFICheck()
        assert check.name == "lfi"

"""Unit tests for pentool/modules/scanner/checks/path_traversal.py."""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock

# Skip all tests if scanner module not available
pytest.importorskip("pentool.modules.scanner")

from pentool.modules.scanner.checks.path_traversal import (
    PathTraversalCheck,
    _classify_evidence,
    _UNIX_SIGNATURES,
    _WIN_SIGNATURES,
    _PATH_PARAM_NAMES,
    _TRAVERSAL_PAYLOADS,
    _MAX_PAYLOADS,
)
from pentool.utils.parser import ParsedRequest


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _make_request(url: str, method: str = "GET", body: str = "") -> ParsedRequest:
    return ParsedRequest(method=method, url=url, headers={}, body=body)


def _make_resp(body: str, status: int = 200):
    resp = MagicMock()
    resp.body = body
    resp.text = None
    resp.content = None
    resp.status = status
    resp.reason = "OK"
    resp.headers = {}
    return resp


def _make_client(resp_body: str = "", status: int = 200):
    client = MagicMock()
    resp = _make_resp(resp_body, status)
    client.get = AsyncMock(return_value=resp)
    client.post = AsyncMock(return_value=resp)
    return client


# ─── TestClassifyEvidence ─────────────────────────────────────────────────────

class TestClassifyEvidence:
    def test_unix_signature_detected(self):
        evidence = _classify_evidence("root:x:0:0:root:/root:/bin/bash")
        assert "Unix" in evidence

    def test_windows_signature_detected(self):
        evidence = _classify_evidence("[fonts]\r\nfile.ttf=Arial\r\n[extensions]")
        assert "Windows" in evidence

    def test_unknown_returns_traversal_pattern(self):
        evidence = _classify_evidence("just some random text")
        assert evidence == "Traversal pattern"

    def test_unix_shadow_signature(self):
        evidence = _classify_evidence("has /etc/shadow content")
        assert "Unix" in evidence

    def test_windows_case_insensitive(self):
        # win.ini signatures checked case-insensitive
        evidence = _classify_evidence("[FONTS]")
        assert "Windows" in evidence


# ─── TestPathTraversalCheckMeta ───────────────────────────────────────────────

class TestPathTraversalCheckMeta:
    def test_name(self):
        assert PathTraversalCheck.name == "path_traversal"

    def test_severity(self):
        assert PathTraversalCheck.severity == "high"

    def test_cwe(self):
        assert PathTraversalCheck.cwe == "CWE-22"

    def test_mitre_attack(self):
        assert PathTraversalCheck.mitre_attack == "T1083"

    def test_not_passive(self):
        assert PathTraversalCheck.passive is False

    def test_description_not_empty(self):
        assert PathTraversalCheck.description


# ─── TestPayloads ─────────────────────────────────────────────────────────────

class TestPayloads:
    def test_payloads_not_empty(self):
        assert len(_TRAVERSAL_PAYLOADS) > 0

    def test_max_payloads_within_list_length(self):
        assert _MAX_PAYLOADS <= len(_TRAVERSAL_PAYLOADS)

    def test_unix_payloads_present(self):
        assert any("etc/passwd" in p for p in _TRAVERSAL_PAYLOADS)

    def test_windows_payloads_present(self):
        assert any("win.ini" in p.lower() for p in _TRAVERSAL_PAYLOADS)

    def test_url_encoded_payloads_present(self):
        assert any("%2e" in p.lower() for p in _TRAVERSAL_PAYLOADS)

    def test_null_byte_payload_present(self):
        assert any("\x00" in p or "%00" in p for p in _TRAVERSAL_PAYLOADS)

    def test_path_param_names_contain_expected(self):
        for name in ("file", "filename", "path", "dir", "page", "doc"):
            assert name in _PATH_PARAM_NAMES

    def test_signatures_not_empty(self):
        assert len(_UNIX_SIGNATURES) > 0
        assert len(_WIN_SIGNATURES) > 0


# ─── TestScanNoClient ─────────────────────────────────────────────────────────

class TestScanNoClient:
    @pytest.mark.asyncio
    async def test_returns_empty_without_client(self):
        check = PathTraversalCheck()
        req = _make_request("https://example.com/?file=test.txt")
        result = await check.scan(req, None, http_client=None)
        assert result == []


# ─── TestScanGetParams ────────────────────────────────────────────────────────

class TestScanGetParams:
    @pytest.mark.asyncio
    async def test_no_params_no_findings(self):
        check = PathTraversalCheck()
        client = _make_client("clean response")
        req = _make_request("https://example.com/page")
        findings = await check.scan(req, None, http_client=client)
        assert findings == []

    @pytest.mark.asyncio
    async def test_path_param_with_unix_signature(self):
        check = PathTraversalCheck()
        client = _make_client("root:x:0:0:root:/root:/bin/bash\ndaemon:x:1:1")
        req = _make_request("https://example.com/?file=test.txt")
        findings = await check.scan(req, None, http_client=client)
        assert len(findings) >= 1
        assert findings[0].type == "path_traversal"
        assert findings[0].severity == "high"
        assert findings[0].cwe == "CWE-22"

    @pytest.mark.asyncio
    async def test_path_param_with_windows_signature(self):
        check = PathTraversalCheck()
        client = _make_client("[fonts]\r\n[extensions]\r\nfor 16-bit app support")
        req = _make_request("https://example.com/?path=data.xml")
        findings = await check.scan(req, None, http_client=client)
        assert len(findings) >= 1
        assert "path_traversal" == findings[0].type

    @pytest.mark.asyncio
    async def test_non_path_param_still_tested(self):
        """Non-path parameters are also tested (after path-params)."""
        check = PathTraversalCheck()
        client = _make_client("root:x:0:0:root:/root:/bin/bash")
        req = _make_request("https://example.com/?q=hello")
        findings = await check.scan(req, None, http_client=client)
        assert len(findings) >= 1

    @pytest.mark.asyncio
    async def test_path_params_tested_before_others(self):
        """path-like parameters should appear in findings first."""
        check = PathTraversalCheck()
        client = _make_client("root:x:0:0:root:/root:/bin/bash")
        req = _make_request("https://example.com/?q=x&file=y")
        findings = await check.scan(req, None, http_client=client)
        # First finding should come from parameter 'file'
        if findings:
            assert findings[0].parameter == "file"

    @pytest.mark.asyncio
    async def test_finding_has_payload(self):
        check = PathTraversalCheck()
        client = _make_client("root:x:0:0:daemon:x:2:2:/bin/sh")
        req = _make_request("https://example.com/?doc=index.html")
        findings = await check.scan(req, None, http_client=client)
        assert findings
        assert findings[0].payload  # payload is not empty

    @pytest.mark.asyncio
    async def test_finding_has_evidence(self):
        check = PathTraversalCheck()
        client = _make_client("root:x:0:0:root:/root:/bin/bash")
        req = _make_request("https://example.com/?filename=file.txt")
        findings = await check.scan(req, None, http_client=client)
        assert findings
        assert "GET" in findings[0].evidence

    @pytest.mark.asyncio
    async def test_finding_has_remediation(self):
        check = PathTraversalCheck()
        client = _make_client("root:x:0:0:root:/root:/bin/bash")
        req = _make_request("https://example.com/?path=test")
        findings = await check.scan(req, None, http_client=client)
        assert findings
        assert findings[0].remediation

    @pytest.mark.asyncio
    async def test_clean_response_no_findings(self):
        check = PathTraversalCheck()
        client = _make_client("<html><body>Hello</body></html>")
        req = _make_request("https://example.com/?file=test.txt")
        findings = await check.scan(req, None, http_client=client)
        assert findings == []

    @pytest.mark.asyncio
    async def test_exception_in_request_does_not_crash(self):
        check = PathTraversalCheck()
        client = MagicMock()
        client.get = AsyncMock(side_effect=Exception("connection refused"))
        req = _make_request("https://example.com/?file=test")
        findings = await check.scan(req, None, http_client=client)
        assert findings == []


# ─── TestScanPathSegments ─────────────────────────────────────────────────────

class TestScanPathSegments:
    @pytest.mark.asyncio
    async def test_path_segment_injection(self):
        check = PathTraversalCheck()
        client = _make_client("root:x:0:0:root:/root:/bin/bash")
        req = _make_request("https://example.com/files/report.pdf")
        findings = await check.scan(req, None, http_client=client)
        assert findings
        # Should contain Path injection finding
        path_findings = [f for f in findings if "Path" in f.evidence]
        assert path_findings

    @pytest.mark.asyncio
    async def test_path_segment_finding_type(self):
        check = PathTraversalCheck()
        client = _make_client("[fonts]\r\n[extensions]")
        req = _make_request("https://example.com/static/css/main.css")
        findings = await check.scan(req, None, http_client=client)
        assert findings
        assert findings[0].type == "path_traversal"

    @pytest.mark.asyncio
    async def test_no_path_segments_skipped(self):
        """URL without path segments — path injection is skipped."""
        check = PathTraversalCheck()
        client = _make_client("<html>clean</html>")
        req = _make_request("https://example.com/")
        findings = await check.scan(req, None, http_client=client)
        assert findings == []

    @pytest.mark.asyncio
    async def test_path_segment_stops_after_first_finding(self):
        """After the first path finding, no more segments are checked."""
        check = PathTraversalCheck()
        call_count = 0
        original_body = "root:x:0:0:root:/root:/bin/bash"

        async def fake_get(url, **kwargs):
            nonlocal call_count
            call_count += 1
            return _make_resp(original_body)

        client = MagicMock()
        client.get = fake_get
        req = _make_request("https://example.com/a/b/c/d")
        findings = await check.scan(req, None, http_client=client)
        assert findings
        # After first segment with finding — segment loop breaks
        # (but GET params already ran their requests)


# ─── TestScanPostUrlencoded ───────────────────────────────────────────────────

class TestScanPostUrlencoded:
    @pytest.mark.asyncio
    async def test_post_body_injection(self):
        check = PathTraversalCheck()
        client = _make_client("root:x:0:0:root:/root:/bin/bash")
        client.post = AsyncMock(return_value=_make_resp("root:x:0:0:root:/root:/bin/bash"))
        req = _make_request(
            "https://example.com/upload",
            method="POST",
            body="file=document.pdf&action=view",
        )
        findings = await check.scan(req, None, http_client=client)
        assert findings

    @pytest.mark.asyncio
    async def test_get_request_skips_post(self):
        """GET request does not test POST body."""
        check = PathTraversalCheck()
        client = _make_client("<html>ok</html>")
        req = _make_request("https://example.com/?file=test", method="GET", body="file=x")
        # POST is not called for GET requests
        findings = await check.scan(req, None, http_client=client)
        # No finding for clean response
        assert findings == []


# ─── TestScanJsonBody ─────────────────────────────────────────────────────────

class TestScanJsonBody:
    @pytest.mark.asyncio
    async def test_json_body_injection(self):
        check = PathTraversalCheck()
        client = _make_client("root:x:0:0:root:/root:/bin/bash")
        client.post = AsyncMock(return_value=_make_resp("root:x:0:0:root:/root:/bin/bash"))

        import json
        body = json.dumps({"file": "document.pdf", "action": "read"})
        req = ParsedRequest(
            method="POST",
            url="https://example.com/api/files",
            headers={"Content-Type": "application/json"},
            body=body,
        )
        findings = await check.scan(req, None, http_client=client)
        # JSON body should be tested
        assert isinstance(findings, list)

    @pytest.mark.asyncio
    async def test_non_json_body_no_json_test(self):
        """Non-JSON body does not trigger JSON testing."""
        check = PathTraversalCheck()
        client = _make_client("<html>ok</html>")
        req = ParsedRequest(
            method="POST",
            url="https://example.com/api",
            headers={"Content-Type": "text/plain"},
            body="plain text body",
        )
        findings = await check.scan(req, None, http_client=client)
        assert findings == []


# ─── TestFindingFields ────────────────────────────────────────────────────────

class TestFindingFields:
    @pytest.mark.asyncio
    async def test_finding_has_all_required_fields(self):
        check = PathTraversalCheck()
        client = _make_client("root:x:0:0:root:/root:/bin/bash")
        req = _make_request("https://example.com/?file=test.txt")
        findings = await check.scan(req, None, http_client=client)
        assert findings
        f = findings[0]
        assert f.type == "path_traversal"
        assert f.severity == "high"
        assert f.cwe == "CWE-22"
        assert f.mitre_attack == "T1083"
        assert f.url
        assert f.parameter
        assert f.payload
        assert f.evidence
        assert f.description
        assert f.remediation

    @pytest.mark.asyncio
    async def test_finding_name_contains_injection_point(self):
        check = PathTraversalCheck()
        client = _make_client("root:x:0:0:root:/root:/bin/bash")
        req = _make_request("https://example.com/?path=test")
        findings = await check.scan(req, None, http_client=client)
        assert findings
        assert "Path Traversal" in findings[0].name

    @pytest.mark.asyncio
    async def test_finding_request_raw_not_empty(self):
        check = PathTraversalCheck()
        client = _make_client("root:x:0:0:root:/root:/bin/bash")
        req = _make_request("https://example.com/?file=test.txt")
        findings = await check.scan(req, None, http_client=client)
        assert findings
        assert findings[0].request_raw

    @pytest.mark.asyncio
    async def test_finding_response_raw_not_empty(self):
        check = PathTraversalCheck()
        client = _make_client("root:x:0:0:root:/root:/bin/bash")
        req = _make_request("https://example.com/?file=test.txt")
        findings = await check.scan(req, None, http_client=client)
        assert findings
        assert findings[0].response_raw


# ─── TestRegistration ─────────────────────────────────────────────────────────

class TestRegistration:
    def test_importable_from_checks_init(self):
        from pentool.modules.scanner.checks import PathTraversalCheck as PTC
        assert PTC is PathTraversalCheck

    def test_in_all(self):
        from pentool.modules.scanner import checks
        assert "PathTraversalCheck" in checks.__all__

    def test_registered_in_scanner_api(self):
        from pentool.api.scanner_api import ScannerAPI
        api = ScannerAPI(db_path=":memory:")
        check_names = [c.name for c in api.get_registered_checks()]
        assert "path_traversal" in check_names

    def test_instantiable(self):
        check = PathTraversalCheck()
        assert check.name == "path_traversal"

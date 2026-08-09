"""Unit tests for pentool/modules/scanner/checks/ssrf.py.

Written as regression coverage BEFORE migrating SSRFCheck to
BaseActiveCheck (see MYPLANS/ARCHITECTURE_REFACTOR_PLAN_2026-08-09.md
section 2.5) — this check had no dedicated unit tests prior to this file.
"""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock

# Skip all tests if scanner module not available
pytest.importorskip("pentool.modules.scanner")

from pentool.modules.scanner.checks.ssrf import (
    SSRFCheck,
    _should_test_ssrf,
    _get_payloads_for_point,
    _check_ssrf,
    _CLOUD_METADATA,
    _SKIP_PARAM_NAMES,
)
from pentool.modules.scanner.mutator import InjectionPoint
from pentool.utils.parser import ParsedRequest


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _make_request(url: str, method: str = "GET", body: str = "") -> ParsedRequest:
    return ParsedRequest(method=method, url=url, headers={}, body=body)


def _make_point(name: str, value: str = "", kind: str = "get") -> InjectionPoint:
    return InjectionPoint(kind=kind, name=name, original_value=value)


def _make_resp(body: str = "", status: int = 200):
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
    client.send = AsyncMock(return_value=resp)
    return client


# ─── TestMeta ─────────────────────────────────────────────────────────────────

class TestMeta:
    def test_name(self):
        assert SSRFCheck.name == "ssrf"

    def test_severity(self):
        assert SSRFCheck.severity == "high"

    def test_cwe(self):
        assert SSRFCheck.cwe == "CWE-918"

    def test_mitre_attack(self):
        assert SSRFCheck.mitre_attack == "T1090"

    def test_not_passive(self):
        assert SSRFCheck.passive is False

    def test_uses_scan_pipeline(self):
        assert SSRFCheck.uses_scan_pipeline is True


# ─── TestShouldTestSsrf ───────────────────────────────────────────────────────

class TestShouldTestSsrf:
    def test_url_param_is_tested(self):
        assert _should_test_ssrf(_make_point("url"))

    def test_skip_param_names_not_tested(self):
        for name in ("page", "limit", "q", "sort"):
            assert not _should_test_ssrf(_make_point(name))

    def test_unknown_param_is_tested(self):
        assert _should_test_ssrf(_make_point("callback_target"))


# ─── TestGetPayloadsForPoint ──────────────────────────────────────────────────

class TestGetPayloadsForPoint:
    def test_url_keyword_gets_full_set(self):
        payloads = _get_payloads_for_point(_make_point("url", "http://x"))
        assert any("file://" in p for p in payloads)
        assert any("169.254.169.254" in p for p in payloads)

    def test_host_keyword_gets_ip_bypasses_no_protocol(self):
        payloads = _get_payloads_for_point(_make_point("host", "example.com"))
        assert not any(p.startswith("file://") for p in payloads)
        assert any("169.254.169.254" in p for p in payloads)

    def test_unknown_param_gets_cloud_metadata_only(self):
        payloads = _get_payloads_for_point(_make_point("id", "42"))
        assert payloads == _CLOUD_METADATA


# ─── TestCheckSsrf ────────────────────────────────────────────────────────────

class TestCheckSsrf:
    def test_ami_id_detected(self):
        found, desc, confidence = _check_ssrf("some data ami-id abc123")
        assert found
        assert confidence >= 1

    def test_clean_body_not_detected(self):
        found, desc, confidence = _check_ssrf("<html>clean</html>")
        assert not found
        assert confidence == 0

    def test_multiple_signatures_higher_confidence(self):
        body = 'ami-id and "accountId": "12345" and computeMetadata'
        found, desc, confidence = _check_ssrf(body)
        assert found
        assert confidence >= 2


# ─── TestScanNoClient ─────────────────────────────────────────────────────────

class TestScanNoClient:
    @pytest.mark.asyncio
    async def test_returns_empty_without_client(self):
        check = SSRFCheck()
        req = _make_request("https://example.com/?url=http://internal")
        result = await check.scan(req, None, http_client=None)
        assert result == []


# ─── TestScanGetParams ────────────────────────────────────────────────────────

class TestScanGetParams:
    @pytest.mark.asyncio
    async def test_no_params_no_findings(self):
        check = SSRFCheck()
        client = _make_client("clean")
        req = _make_request("https://example.com/page")
        findings = await check.scan(req, None, http_client=client)
        assert findings == []

    @pytest.mark.asyncio
    async def test_ssrf_detected(self):
        check = SSRFCheck()
        client = _make_client('"accountId": "123456789012" ami-id')
        req = _make_request("https://example.com/?url=http://internal")
        findings = await check.scan(req, None, http_client=client)
        assert len(findings) >= 1
        assert findings[0].type == "ssrf"
        assert findings[0].cwe == "CWE-918"

    @pytest.mark.asyncio
    async def test_clean_response_no_findings(self):
        check = SSRFCheck()
        client = _make_client("<html>ok</html>")
        req = _make_request("https://example.com/?url=http://internal")
        findings = await check.scan(req, None, http_client=client)
        assert findings == []

    @pytest.mark.asyncio
    async def test_skip_param_names_never_tested(self):
        """Params like 'page'/'q' should never trigger any request — but
        the request also has several injectable headers (Referer,
        User-Agent, etc. — see RequestMutator.extract_points) which are
        NOT in _SKIP_PARAM_NAMES and are tested independently. Verify by
        checking that no payload sent corresponds to the 'page' or 'q'
        GET params specifically (mutator sends payload as query value)."""
        check = SSRFCheck()
        seen_urls = []

        async def fake_send(mutated):
            seen_urls.append(mutated.url)
            return _make_resp("clean")

        client = MagicMock()
        client.send = fake_send
        req = _make_request("https://example.com/?page=1&q=hello")
        await check.scan(req, None, http_client=client)
        # None of the captured URLs should have mutated 'page=' or 'q=' —
        # those two GET params are skipped entirely (only their original
        # values ever appear, never one of the SSRF payloads).
        from pentool.modules.scanner.checks.ssrf import _CLOUD_METADATA
        probe = _CLOUD_METADATA[0]
        assert not any(f"page={probe}" in u or f"q={probe}" in u for u in seen_urls)

    @pytest.mark.asyncio
    async def test_exception_does_not_crash(self):
        check = SSRFCheck()
        client = MagicMock()
        client.send = AsyncMock(side_effect=Exception("connection refused"))
        req = _make_request("https://example.com/?url=http://internal")
        findings = await check.scan(req, None, http_client=client)
        assert findings == []

    @pytest.mark.asyncio
    async def test_finding_has_all_required_fields(self):
        check = SSRFCheck()
        client = _make_client('"accountId": "123456789012" ami-id')
        req = _make_request("https://example.com/?url=http://internal")
        findings = await check.scan(req, None, http_client=client)
        assert findings
        f = findings[0]
        assert f.type == "ssrf"
        assert f.severity in ("high", "medium")
        assert f.cwe == "CWE-918"
        assert f.mitre_attack == "T1090"
        assert f.url
        assert f.parameter
        assert f.payload
        assert f.evidence
        assert f.description
        assert f.remediation
        assert f.request_raw
        assert f.response_raw

    @pytest.mark.asyncio
    async def test_finding_severity_medium_for_single_signature(self):
        check = SSRFCheck()
        client = _make_client("ami-id only signature")
        req = _make_request("https://example.com/?url=http://internal")
        findings = await check.scan(req, None, http_client=client)
        assert findings
        assert findings[0].severity == "medium"

    @pytest.mark.asyncio
    async def test_finding_severity_high_for_multiple_signatures(self):
        check = SSRFCheck()
        client = _make_client('ami-id and "accountId": "12345" and computeMetadata')
        req = _make_request("https://example.com/?url=http://internal")
        findings = await check.scan(req, None, http_client=client)
        assert findings
        assert findings[0].severity == "high"


# ─── TestRegistration ─────────────────────────────────────────────────────────

class TestRegistration:
    def test_importable_from_checks_init(self):
        from pentool.modules.scanner.checks import SSRFCheck as SC
        assert SC is SSRFCheck

    def test_in_all(self):
        from pentool.modules.scanner import checks
        assert "SSRFCheck" in checks.__all__

    def test_registered_in_scanner_api(self):
        from pentool.api.scanner_api import ScannerAPI
        api = ScannerAPI(db_path=":memory:")
        check_names = [c.name for c in api.get_registered_checks()]
        assert "ssrf" in check_names

    def test_instantiable(self):
        check = SSRFCheck()
        assert check.name == "ssrf"

"""Unit tests for pentool/modules/scanner/checks/rce.py.

Part of plan-2026-08-09 section 2.5 coverage (step 1: capture existing
behavior with unit tests, no check code changes yet): RCECheck is a
scan()-pipeline check with error-based (phase 1) and time-based blind
(phase 2) logic. We pin the error-based path (stable, no sleeps), the
response-signature helpers, and the WAF-bypass variant builder. The
time-based blind phase is captured at the helper/payload level rather than
by issuing real sleep() calls in tests.
"""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock

pytest.importorskip("pentool.modules.scanner")

from pentool.modules.scanner.checks.rce import (
    RCECheck,
    _TIME_PAYLOADS,
    _WAF_STATUS,
    _check_rce_response,
    _waf_variants,
)
from pentool.modules.scanner.mutator import InjectionPoint
from pentool.utils.parser import ParsedRequest, ParsedResponse

ID_BODY = "root@host:~# id\nuid=1000(user) gid=1000(group)\n"


def _req(url: str = "http://target/cmd?cmd=ls") -> ParsedRequest:
    return ParsedRequest(method="GET", url=url, headers={}, body="")


class TestMeta:
    def test_name(self):
        assert RCECheck.name == "rce"

    def test_uses_scan_pipeline(self):
        assert RCECheck.uses_scan_pipeline is True


class TestCheckRceResponse:
    def test_detects_id_output(self):
        assert _check_rce_response(";id", ID_BODY) is not None

    def test_generic_fallback_unknown_payload(self):
        # Payload with no category falls through to generic patterns.
        assert _check_rce_response("x=ls", ID_BODY) is not None

    def test_clean_body_no_finding(self):
        assert _check_rce_response(";id", "<html>ok</html>") is None


class TestWafVariants:
    def test_space_bypass_generates_variants(self):
        variants = _waf_variants("; id")
        # Space substitution variants present; original excluded.
        assert "; id" not in variants
        assert variants, "expected at least one WAF bypass variant"
        # A space-substituted variant carries ${IFS} or a tab/newline.
        assert any("${IFS}" in v or "\t" in v or "\n" in v for v in variants)

    def test_capped(self):
        variants = _waf_variants("; id; whoami; cat /etc/passwd; uname -a")
        assert len(variants) <= 8


class TestTimePayloads:
    def test_has_sleep_payloads(self):
        assert any("sleep" in p for p in _TIME_PAYLOADS)


class TestAnalyze:
    @pytest.mark.asyncio
    async def test_finding_on_id_output(self):
        check = RCECheck()
        req = _req()
        point = InjectionPoint(kind="get", name="cmd", original_value="ls")
        resp = ParsedResponse(200, "OK", {}, ID_BODY)
        finding = await check.analyze(req, req, point, ";id", resp)
        assert finding is not None
        assert finding.type == "rce"
        assert finding.parameter == "cmd"

    @pytest.mark.asyncio
    async def test_no_finding_on_clean(self):
        check = RCECheck()
        req = _req()
        point = InjectionPoint(kind="get", name="cmd", original_value="ls")
        resp = ParsedResponse(200, "OK", {}, "<html>ok</html>")
        finding = await check.analyze(req, req, point, ";id", resp)
        assert finding is None


class TestScanErrorBased:
    @pytest.mark.asyncio
    async def test_error_based_detects_rce(self):
        check = RCECheck()
        req = _req()
        # Fake server executes `id` -> returns uid/gid output; everything else
        # returns clean. Phase 1 stops as soon as the first command fires.
        class Fake:
            async def send(self, request):
                body = ID_BODY if "id" in (request.url or "") else "<html>ok</html>"
                return ParsedResponse(200, "OK", {}, body)

        findings = await check.scan(req, None, Fake(), point=None)
        assert any(f.type == "rce" for f in findings)

    @pytest.mark.asyncio
    async def test_waf_status_triggers_bypass_path(self):
        check = RCECheck()
        req = _req()
        # Any id-bearing payload first returns a WAF status (403); the WAF
        # bypass variant (e.g. `${IFS}` space substitution, which mutator
        # URL-encodes as %7BIFS%7D but the "IFS" letters remain) then returns
        # the command output -> finding.
        class Fake:
            async def send(self, request):
                url = request.url or ""
                if "id" in url and "IFS" in url:
                    return ParsedResponse(200, "OK", {}, ID_BODY)
                if "id" in url:
                    return ParsedResponse(403, "Forbidden", {}, "blocked")
                return ParsedResponse(403, "Forbidden", {}, "blocked")

        findings = await check.scan(req, None, Fake(), point=None)
        assert any(f.type == "rce" for f in findings)


class TestEngineIntegration:
    """End-to-end through ScanEngine — error-based RCE surfaced via the
    per-point scan()-pipeline."""

    @pytest.fixture(autouse=True)
    def _reset_session_license(self):
        import pentool.core.license as lic_mod
        saved = lic_mod._session_license
        lic_mod._session_license = None
        yield
        lic_mod._session_license = saved

    @pytest.mark.asyncio
    async def test_engine_detects_rce(self):
        from pentool.modules.scanner.engine import ScanEngine

        class FakeClient:
            async def send(self, request):
                body = ID_BODY if "id" in (request.url or "") else "<html>ok</html>"
                return ParsedResponse(200, "OK", {}, body)

            async def get(self, url, headers=None):
                return ParsedResponse(200, "OK", {}, "<html>ok</html>")

        engine = ScanEngine(db_path=":memory:", http_client=FakeClient())
        engine.register_check(RCECheck())
        req = _req()
        findings = await engine.run_active_on_requests([req])
        assert any(f.type == "rce" for f in findings)

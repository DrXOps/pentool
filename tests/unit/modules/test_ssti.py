"""Unit tests for pentool/modules/scanner/checks/ssti.py.

Part of plan-2026-08-09 section 2.5 coverage (step 1: capture existing
behavior with unit tests, no check code changes yet): SSTICheck is a
scan()-pipeline check whose math-probe payloads are randomly generated per
instance (`__init__` -> `_make_ssti_probe()`). analyze() validates against
that instance's `_probe_map`. We use the instance's own payloads/expectations
so the tests are stable regardless of the random draw, and we pin the
math-probe detection path (phase 2) in isolation.
"""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock

pytest.importorskip("pentool.modules.scanner")

from pentool.modules.scanner.checks.ssti import (
    SSTICheck,
    _ENGINE_RCE_PROBES,
    _ERROR_PROBE,
    _fingerprint_engine,
    _make_ssti_probe,
)
from pentool.modules.scanner.mutator import InjectionPoint
from pentool.utils.parser import ParsedRequest, ParsedResponse


def _req(url: str = "http://target/page?q=1") -> ParsedRequest:
    return ParsedRequest(method="GET", url=url, headers={}, body="")


class TestMeta:
    def test_name(self):
        assert SSTICheck.name == "ssti"

    def test_uses_scan_pipeline(self):
        assert SSTICheck.uses_scan_pipeline is True

    def test_generates_probe_map(self):
        check = SSTICheck()
        assert check._probe_map
        assert check.get_payloads()


class TestFingerprintEngine:
    def test_detects_jinja2(self):
        assert _fingerprint_engine("jinja2.exceptions.UndefinedError") == "jinja2"

    def test_detects_smarty(self):
        assert _fingerprint_engine("Smarty error: syntax") == "smarty"

    def test_clean_body_no_engine(self):
        assert _fingerprint_engine("<html>ok</html>") is None


class TestMakeSstiProbe:
    def test_payloads_and_expected_have_same_length(self):
        probe_map, payloads = _make_ssti_probe()
        assert len(probe_map) == len(payloads)
        assert len(payloads) > 0
        # every payload maps to exactly one expected value
        for p, e in probe_map:
            assert p in payloads


class TestAnalyze:
    @pytest.mark.asyncio
    async def test_finding_when_expected_reflected(self):
        check = SSTICheck()
        # Use the instance's own first (payload, expected) pair — stable for
        # any random draw.
        payload, expected = check._probe_map[0]
        req = _req()
        point = InjectionPoint(kind="get", name="q", original_value="1")
        resp = ParsedResponse(200, "OK", {}, f"page contains {expected}")
        finding = await check.analyze(req, req, point, payload, resp)
        assert finding is not None
        assert finding.type == "ssti"

    @pytest.mark.asyncio
    async def test_no_finding_when_not_reflected(self):
        check = SSTICheck()
        payload, _ = check._probe_map[0]
        req = _req()
        point = InjectionPoint(kind="get", name="q", original_value="1")
        resp = ParsedResponse(200, "OK", {}, "<html>nothing here</html>")
        finding = await check.analyze(req, req, point, payload, resp)
        assert finding is None

    @pytest.mark.asyncio
    async def test_unknown_payload_returns_none(self):
        check = SSTICheck()
        req = _req()
        point = InjectionPoint(kind="get", name="q", original_value="1")
        resp = ParsedResponse(200, "OK", {}, "anything")
        finding = await check.analyze(req, req, point, "{{NOT_IN_MAP}}", resp)
        assert finding is None


class TestScanMathProbe:
    @pytest.mark.asyncio
    async def test_math_probe_detects_ssti(self):
        check = SSTICheck()
        req = _req()
        # Fake server reflects every math-probe expected value back; the
        # error probe yields a clean body (no engine fingerprint), so only
        # phase 2 (math detection) fires.
        all_expected = "\n".join(e for _, e in check._probe_map)

        class Fake:
            async def send(self, request):
                return ParsedResponse(200, "OK", {}, all_expected)

        findings = await check.scan(req, None, Fake(), point=None)
        assert any(f.type == "ssti" for f in findings)


class TestEngineIntegration:
    """End-to-end through ScanEngine — SSTI math probe surfaced via the
    per-point scan()-pipeline. ssti always passes fingerprint relevance
    (allows_check('ssti') is True for any stack)."""

    @pytest.fixture(autouse=True)
    def _reset_session_license(self):
        import pentool.core.license as lic_mod
        saved = lic_mod._session_license
        lic_mod._session_license = None
        yield
        lic_mod._session_license = saved

    @pytest.mark.asyncio
    async def test_engine_detects_ssti(self):
        from pentool.modules.scanner.engine import ScanEngine

        check = SSTICheck()
        all_expected = "\n".join(e for _, e in check._probe_map)

        class FakeClient:
            async def send(self, request):
                return ParsedResponse(200, "OK", {}, all_expected)

            async def get(self, url, headers=None):
                return ParsedResponse(200, "OK", {}, "<html>ok</html>")

        engine = ScanEngine(db_path=":memory:", http_client=FakeClient())
        engine.register_check(check)
        req = _req()
        findings = await engine.run_active_on_requests([req])
        assert any(f.type == "ssti" for f in findings)

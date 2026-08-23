"""Unit tests for pentool/modules/scanner/checks/sqli.py::SQLiCheck.

Part of plan-2026-08-09 section 2.5 coverage (step 1: capture existing
behavior with unit tests, no check code changes yet): SQLiCheck is a
scan()-pipeline, multi-phase check (baseline -> error-based -> quote-type /
boolean blind -> time-based blind). We pin the stable, sleep-free paths —
error-based detection (phase 1) and the DB-error helpers — and note the
time-based phase at the payload constant level. (SQLiUnionCheck has its own
test module; this file covers SQLiCheck only.)
"""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock

pytest.importorskip("pentool.modules.scanner")

from pentool.modules.scanner.checks.sqli import (
    SQLiCheck,
    _BOOL_PAIRS,
    _QUOTE_PROBES,
    _TIME_PAYLOADS,
    _detect_db,
    _has_db_error,
    _is_waf_blocked,
)
from pentool.modules.scanner.mutator import InjectionPoint
from pentool.utils.parser import ParsedRequest, ParsedResponse

MYSQL_ERROR = (
    "You have an error in your SQL syntax; check the manual that corresponds "
    "to your MySQL server version for the right syntax to use near 'x'"
)

CLEAN_BODY = "<html>home page with content</html>"


def _req(url: str = "http://target/item?id=1") -> ParsedRequest:
    return ParsedRequest(method="GET", url=url, headers={}, body="")


class TestMeta:
    def test_name(self):
        assert SQLiCheck.name == "sqli"

    def test_uses_scan_pipeline(self):
        assert SQLiCheck.uses_scan_pipeline is True

    def test_get_payloads_nonempty(self):
        assert len(SQLiCheck().get_payloads()) > 0


class TestHelpers:
    def test_has_db_error(self):
        found, sig = _has_db_error(MYSQL_ERROR)
        assert found
        assert "SQL syntax" in sig
        assert not _has_db_error(CLEAN_BODY)[0]

    def test_detect_db_mysql(self):
        assert "mysql" in _detect_db(MYSQL_ERROR)

    def test_waf_status(self):
        assert _is_waf_blocked(403)
        assert not _is_waf_blocked(200)


class TestPhaseConstantPresence:
    def test_quote_probes(self):
        assert "'" in _QUOTE_PROBES

    def test_bool_pairs_have_numeric(self):
        assert "numeric" in _BOOL_PAIRS

    def test_time_payloads_by_db(self):
        assert isinstance(_TIME_PAYLOADS, dict)
        assert _TIME_PAYLOADS  # non-empty


class TestAnalyze:
    @pytest.mark.asyncio
    async def test_finding_on_db_error(self):
        check = SQLiCheck()
        req = _req()
        point = InjectionPoint(kind="get", name="id", original_value="1")
        resp = ParsedResponse(500, "Error", {}, MYSQL_ERROR)
        finding = await check.analyze(req, req, point, "'", resp)
        assert finding is not None
        assert finding.type == "sqli"
        assert "Error-based" in finding.name

    @pytest.mark.asyncio
    async def test_no_finding_on_clean(self):
        check = SQLiCheck()
        req = _req()
        point = InjectionPoint(kind="get", name="id", original_value="1")
        resp = ParsedResponse(200, "OK", {}, CLEAN_BODY)
        finding = await check.analyze(req, req, point, "'", resp)
        assert finding is None


class TestScanErrorBased:
    @pytest.mark.asyncio
    async def test_error_based_detects_sqli(self):
        check = SQLiCheck()
        req = _req()
        # Baseline (unmutated url) -> clean; any mutation -> MySQL error.
        async def send(request):
            if request.url == req.url:
                return ParsedResponse(200, "OK", {}, CLEAN_BODY)
            return ParsedResponse(500, "Error", {}, MYSQL_ERROR)

        client = MagicMock()
        client.send = AsyncMock(side_effect=send)
        findings = await check.scan(req, None, client)
        assert any(f.type == "sqli" for f in findings)
        assert any("Error-based" in f.name for f in findings)


class TestEngineIntegration:
    """End-to-end through ScanEngine — error-based SQLi surfaced."""

    @pytest.fixture(autouse=True)
    def _reset_session_license(self):
        import pentool.core.license as lic_mod
        saved = lic_mod._session_license
        lic_mod._session_license = None
        yield
        lic_mod._session_license = saved

    @pytest.mark.asyncio
    async def test_engine_detects_sqli(self):
        from pentool.modules.scanner.engine import ScanEngine

        original_url = "http://target/item?id=1"

        class FakeClient:
            async def send(self, request):
                if (request.url or "") == original_url:
                    return ParsedResponse(200, "OK", {}, CLEAN_BODY)
                return ParsedResponse(500, "Error", {}, MYSQL_ERROR)

            async def get(self, url, headers=None):
                return ParsedResponse(200, "OK", {}, CLEAN_BODY)

        engine = ScanEngine(db_path=":memory:", http_client=FakeClient())
        engine.register_check(SQLiCheck())
        req = _req()
        findings = await engine.run_active_on_requests([req])
        assert any(f.type == "sqli" for f in findings)

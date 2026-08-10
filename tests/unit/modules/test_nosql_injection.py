"""Unit tests for pentool/modules/scanner/checks/nosql_injection.py.

Regression coverage for a bug found while auditing checks alongside the
BaseActiveCheck migration (see
MYPLANS/ARCHITECTURE_REFACTOR_PLAN_2026-08-09.md addendum):
NoSQLInjectionCheck declared `uses_scan_pipeline = True` while implementing
the new analyze() API and having an unconditional `scan() -> []` stub — per
BaseCheck.uses_analyze_api this forced the engine to always call the stub
instead of analyze(), so the check silently never found anything in a real
scan. A second bug in the same class: `request_raw` was built by calling
`format_response_raw()` (a response formatter) on the *request* object
instead of `build_http_request()`.
"""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock

pytest.importorskip("pentool.modules.scanner")

from pentool.modules.scanner.checks.nosql_injection import (
    NoSQLInjectionCheck,
    _URL_PAYLOADS,
    _JSON_PAYLOADS,
    _has_nosql_error,
)
from pentool.modules.scanner.engine import ScanEngine
from pentool.modules.scanner.mutator import InjectionPoint
from pentool.utils.parser import ParsedRequest, ParsedResponse


def _make_request(url: str, method: str = "GET", body: str = "") -> ParsedRequest:
    return ParsedRequest(method=method, url=url, headers={}, body=body)


def _make_point(name: str, value: str = "1", kind: str = "get") -> InjectionPoint:
    return InjectionPoint(kind=kind, name=name, original_value=value)


class TestMeta:
    def test_name(self):
        assert NoSQLInjectionCheck.name == "nosql_injection"

    def test_not_uses_scan_pipeline(self):
        # The whole point of the regression: this must stay False (or unset)
        # so BaseCheck.uses_analyze_api routes the engine to analyze(), not
        # to the scan() stub.
        assert getattr(NoSQLInjectionCheck, "uses_scan_pipeline", False) is False

    def test_uses_analyze_api(self):
        assert NoSQLInjectionCheck().uses_analyze_api is True


class TestHasNosqlError:
    def test_detects_mongo_error(self):
        found, evidence = _has_nosql_error("MongoError: bad query operator")
        assert found
        assert "MongoError" in evidence

    def test_clean_body_not_detected(self):
        found, evidence = _has_nosql_error("<html>ok</html>")
        assert not found


class TestAnalyze:
    @pytest.mark.asyncio
    async def test_finding_on_mongo_error(self):
        check = NoSQLInjectionCheck()
        req = _make_request("http://test/api?id=1")
        mutated = _make_request("http://test/api?id=1[$ne]=x")
        point = _make_point("id")
        resp = ParsedResponse(status=500, reason="Internal Server Error",
                               headers={}, body="MongoError: bad query")
        finding = await check.analyze(req, mutated, point, "[$ne]=x", resp)
        assert finding is not None
        assert finding.type == "nosql_injection"
        assert finding.parameter == "id"

    @pytest.mark.asyncio
    async def test_no_finding_on_clean_response(self):
        check = NoSQLInjectionCheck()
        req = _make_request("http://test/api?id=1")
        mutated = _make_request("http://test/api?id=1[$ne]=x")
        point = _make_point("id")
        resp = ParsedResponse(status=200, reason="OK", headers={}, body="ok")
        finding = await check.analyze(req, mutated, point, "[$ne]=x", resp)
        assert finding is None

    @pytest.mark.asyncio
    async def test_request_raw_is_a_real_http_request(self):
        """Regression: request_raw must be built via build_http_request(),
        not format_response_raw() (which expects a response, not a request)
        — the bug produced garbage like 'HTTP/1.1 0 \\r\\nHost: ...'."""
        check = NoSQLInjectionCheck()
        req = _make_request("http://test/api?id=1")
        mutated = _make_request("http://test/api?id=1[$ne]=x")
        point = _make_point("id")
        resp = ParsedResponse(status=500, reason="Internal Server Error",
                               headers={}, body="MongoError: bad query")
        finding = await check.analyze(req, mutated, point, "[$ne]=x", resp)
        assert finding is not None
        assert finding.request_raw.startswith("GET ")
        assert "HTTP/1.1 0" not in finding.request_raw


class TestEngineIntegration:
    """End-to-end through ScanEngine — this is what was actually broken:
    the check never fired at all when run through the real scan pipeline."""

    @pytest.fixture(autouse=True)
    def _reset_session_license(self):
        # BaseCheck.is_available() consults get_session_license(), a
        # process-global cache (pentool.core.license._session_license).
        # Another test module (test_license.py::TestSessionCache) leaves a
        # plan="pro"/features=[] LicenseInfo cached there without resetting
        # it — has_feature("scanner_pro") then returns False for every check
        # in the same test process, and BaseCheck.is_available() filters
        # this check out of active_checks before it ever runs. Reset before
        # and after so this test's outcome doesn't depend on suite order.
        import pentool.core.license as lic_mod
        lic_mod._session_license = None
        yield
        lic_mod._session_license = None

    @pytest.mark.asyncio
    async def test_engine_detects_nosql_injection(self):
        from urllib.parse import unquote

        class FakeClient:
            async def send(self, request):
                # GET-param payloads are URL-encoded by RequestMutator.mutate()
                # (e.g. "$" -> "%24") — decode before matching.
                decoded = unquote(request.url) + (request.body or "")
                body = "MongoError: bad query" if "$" in decoded else "ok"
                return ParsedResponse(status=200, reason="OK", headers={}, body=body)

        engine = ScanEngine(db_path=":memory:", http_client=FakeClient())
        engine.register_check(NoSQLInjectionCheck())
        req = _make_request("http://test/api?id=1")
        findings = await engine.run_active_on_requests([req])
        assert any(f.type == "nosql_injection" for f in findings)

"""Unit tests for pentool/modules/scanner/checks/sqli.py::SQLiUnionCheck.

Regression coverage for the migration of SQLiUnionCheck onto BaseActiveCheck
(see MYPLANS/ARCHITECTURE_REFACTOR_PLAN_2026-08-09.md section 2.5).

Before this fix SQLiUnionCheck declared `uses_scan_pipeline = True` but its
own `scan()` was a `return []` stub — the exact "never runs in a real scan"
bug pattern already fixed for NoSQLInjection/PrototypePollution. By
inheriting BaseActiveCheck it now runs the real `mutate -> send -> analyze`
cycle per injection point and can actually detect union-based SQLi.

Note on licensing: SQLiUnionCheck sets `required_feature = "scanner_sqli_union"`,
a separate PRO feature beyond the base "scanner_pro" trial — so it is filtered
out of `run_active_on_requests()` by `is_available()` under the default dev
license (matches real runtime, see tests/perf/scanner_engine_leak.py). The
engine-integration test below therefore explicitly injects a license carrying
this feature so it exercises the check itself, not the license gate.
"""

from __future__ import annotations

from urllib.parse import unquote

import pytest

pytest.importorskip("pentool.modules.scanner")

from pentool.modules.scanner.base import BaseActiveCheck
from pentool.modules.scanner.checks.sqli import SQLiUnionCheck, _UNION_PAYLOADS
from pentool.modules.scanner.engine import ScanEngine
from pentool.modules.scanner.mutator import InjectionPoint
from pentool.utils.parser import ParsedRequest, ParsedResponse

_MYSQL_ERROR = "You have an error in your SQL syntax; check the manual"


def _make_request(url: str, method: str = "GET", body: str = "") -> ParsedRequest:
    return ParsedRequest(method=method, url=url, headers={}, body=body)


def _make_point(name: str, value: str = "1", kind: str = "get") -> InjectionPoint:
    return InjectionPoint(kind=kind, name=name, original_value=value)


class TestMeta:
    def test_name(self):
        assert SQLiUnionCheck.name == "sqli_union"

    def test_is_base_active_check(self):
        # The whole point of the migration: it must go through the inherited
        # scan() (BaseActiveCheck template method), not a return-[] stub.
        assert issubclass(SQLiUnionCheck, BaseActiveCheck)

    def test_uses_scan_pipeline(self):
        assert SQLiUnionCheck.uses_scan_pipeline is True

    def test_required_feature(self):
        # Separate PRO feature beyond base scanner_pro trial.
        assert SQLiUnionCheck.required_feature == "scanner_sqli_union"


class TestPayloads:
    def test_has_union_payloads(self):
        assert "UNION SELECT" in _UNION_PAYLOADS[0]


class TestAnalyze:
    @pytest.mark.asyncio
    async def test_finding_on_db_error(self):
        check = SQLiUnionCheck()
        req = _make_request("http://test/api?id=1")
        mutated = _make_request("http://test/api?id=1' UNION SELECT NULL--")
        point = _make_point("id")
        resp = ParsedResponse(status=500, reason="Internal Server Error",
                               headers={}, body=_MYSQL_ERROR)
        finding = await check.analyze(req, mutated, point, "' UNION SELECT NULL--", resp)
        assert finding is not None
        assert finding.type == "sqli_union"
        assert finding.parameter == "id"

    @pytest.mark.asyncio
    async def test_no_finding_on_clean_response(self):
        check = SQLiUnionCheck()
        req = _make_request("http://test/api?id=1")
        mutated = _make_request("http://test/api?id=1' UNION SELECT NULL--")
        point = _make_point("id")
        resp = ParsedResponse(status=200, reason="OK", headers={}, body="ok")
        finding = await check.analyze(req, mutated, point, "' UNION SELECT NULL--", resp)
        assert finding is None


class TestEngineIntegration:
    """End-to-end through ScanEngine — the inherited scan() must actually
    drive analyze() against each injection point and surface a finding."""

    @pytest.fixture(autouse=True)
    def _grant_sqli_union_feature(self):
        # SQLiUnionCheck needs "scanner_sqli_union", which the default dev
        # license (["scanner_pro"]) does not carry — without this the engine
        # filters the check out via is_available() and the test would test
        # the license gate, not the check. Save/restore the global cache so
        # suite order doesn't leak state into other tests.
        import pentool.core.license as lic_mod
        saved = lic_mod._session_license
        lic_mod._session_license = lic_mod.LicenseInfo(
            valid=True, plan="pro", features=["scanner_pro", "scanner_sqli_union"]
        )
        yield
        lic_mod._session_license = saved

    @pytest.mark.asyncio
    async def test_engine_detects_sqli_union(self):
        class FakeClient:
            async def send(self, request):
                decoded = unquote(request.url) + (request.body or "")
                body = _MYSQL_ERROR if "SELECT" in decoded else "ok"
                return ParsedResponse(status=500, reason="Internal Server Error",
                                       headers={}, body=body)

            async def get(self, url, headers=None):
                return ParsedResponse(status=200, reason="OK", headers={}, body="")

        engine = ScanEngine(db_path=":memory:", http_client=FakeClient())
        engine.register_check(SQLiUnionCheck())
        req = _make_request("http://test/api?id=1")
        findings = await engine.run_active_on_requests([req])
        assert any(f.type == "sqli_union" for f in findings)

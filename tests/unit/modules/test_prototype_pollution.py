"""Unit tests for pentool/modules/scanner/checks/prototype_pollution.py.

Coverage for the migration of PrototypePollutionCheck onto BaseActiveCheck
(see MYPLANS/ARCHITECTURE_REFACTOR_PLAN_2026-08-09.md section 2.5). The
check is a single-phase per-payload analyze() check (SSPP marker / TypeError
detection in the response body) with no multi-phase logic, so it now uses
the inherited BaseActiveCheck cycle instead of the engine's analyze()-API
branch on a scan() stub. It sets use_baseline_diff_skip=True to keep the
response-diff-skip throughput. History (the pre-existing bug this inverts):
before the migration it wrongly declared uses_scan_pipeline=True, forcing
the engine onto a `return []` scan() stub, so it silently never found
anything in a real scan.
"""

from __future__ import annotations

import pytest

pytest.importorskip("pentool.modules.scanner")

from pentool.modules.scanner.checks.prototype_pollution import (
    PrototypePollutionCheck,
    _MARKER,
    _PAYLOADS,
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
        assert PrototypePollutionCheck.name == "prototype_pollution"

    def test_is_base_active_check(self):
        # Migrated onto BaseActiveCheck (plan 2.5): the inherited scan()
        # drives get_payloads()/analyze() through the base template cycle —
        # the old path was the engine's analyze() branch on a scan() stub.
        from pentool.modules.scanner.base import BaseActiveCheck
        assert issubclass(PrototypePollutionCheck, BaseActiveCheck)

    def test_uses_scan_pipeline(self):
        assert PrototypePollutionCheck.uses_scan_pipeline is True

    def test_use_baseline_diff_skip(self):
        # Keeps the response-diff-skip the engine's analyze() branch used
        # to give this check for throughput.
        assert PrototypePollutionCheck.use_baseline_diff_skip is True


class TestAnalyze:
    @pytest.mark.asyncio
    async def test_finding_on_marker_reflected(self):
        check = PrototypePollutionCheck()
        req = _make_request("http://test/api?id=1")
        mutated = _make_request("http://test/api?id=1", body=_PAYLOADS[0])
        point = _make_point("id")
        resp = ParsedResponse(
            status=200, reason="OK", headers={},
            body=f'{{"{_MARKER}": "1"}}',
        )
        finding = await check.analyze(req, mutated, point, _PAYLOADS[0], resp)
        assert finding is not None
        assert finding.type == "prototype_pollution"

    @pytest.mark.asyncio
    async def test_finding_on_typeerror(self):
        check = PrototypePollutionCheck()
        req = _make_request("http://test/api?id=1")
        mutated = _make_request("http://test/api?id=1", body=_PAYLOADS[0])
        point = _make_point("id")
        resp = ParsedResponse(
            status=500, reason="Internal Server Error", headers={},
            body="TypeError: Cannot set property foo of #<Object>",
        )
        finding = await check.analyze(req, mutated, point, _PAYLOADS[0], resp)
        assert finding is not None
        assert "Error" in finding.name

    @pytest.mark.asyncio
    async def test_no_finding_on_clean_response(self):
        check = PrototypePollutionCheck()
        req = _make_request("http://test/api?id=1")
        mutated = _make_request("http://test/api?id=1", body=_PAYLOADS[0])
        point = _make_point("id")
        resp = ParsedResponse(status=200, reason="OK", headers={}, body="ok")
        finding = await check.analyze(req, mutated, point, _PAYLOADS[0], resp)
        assert finding is None

    @pytest.mark.asyncio
    async def test_request_raw_is_a_real_http_request(self):
        check = PrototypePollutionCheck()
        req = _make_request("http://test/api?id=1")
        mutated = _make_request("http://test/api?id=1", body=_PAYLOADS[0])
        point = _make_point("id")
        resp = ParsedResponse(
            status=200, reason="OK", headers={},
            body=f'{{"{_MARKER}": "1"}}',
        )
        finding = await check.analyze(req, mutated, point, _PAYLOADS[0], resp)
        assert finding is not None
        assert finding.request_raw.startswith("GET ")
        assert "HTTP/1.1 0" not in finding.request_raw


class TestEngineIntegration:
    @pytest.fixture(autouse=True)
    def _reset_session_license(self):
        # See identical fixture/explanation in test_nosql_injection.py:
        # another test module leaves a stale plan="pro"/features=[]
        # LicenseInfo in the process-global session-license cache, which
        # makes BaseCheck.is_available() filter this check out regardless
        # of test order.
        import pentool.core.license as lic_mod
        lic_mod._session_license = None
        yield
        lic_mod._session_license = None

    @pytest.mark.asyncio
    async def test_engine_detects_prototype_pollution(self):
        class FakeClient:
            async def send(self, request):
                body = (
                    f'{{"{_MARKER}": "1"}}'
                    if "__proto__" in (request.body or "") or "__proto__" in request.url
                    else "ok"
                )
                return ParsedResponse(status=200, reason="OK", headers={}, body=body)

            async def get(self, url, headers=None):
                # TechFingerprinter probes via get() before the scan starts —
                # respond as an Express/Node.js stack so
                # TechProfile.allows_check("prototype_pollution")
                # (applicable_techs=["nodejs"]) doesn't filter this check out.
                return ParsedResponse(
                    status=200, reason="OK",
                    headers={"X-Powered-By": "Express"}, body="",
                )

        engine = ScanEngine(db_path=":memory:", http_client=FakeClient())
        engine.register_check(PrototypePollutionCheck())
        req = _make_request("http://test/api", method="POST", body='{"id": "1"}')
        findings = await engine.run_active_on_requests([req])
        assert any(f.type == "prototype_pollution" for f in findings)

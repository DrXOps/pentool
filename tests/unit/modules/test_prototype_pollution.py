"""Unit tests for pentool/modules/scanner/checks/prototype_pollution.py.

Regression coverage for the same bug class documented in
test_nosql_injection.py (see
MYPLANS/ARCHITECTURE_REFACTOR_PLAN_2026-08-09.md addendum):
PrototypePollutionCheck declared `uses_scan_pipeline = True` while
implementing the new analyze() API and having an unconditional
`scan() -> []` stub, so the check silently never found anything in a real
scan. Also fixed: `request_raw` used `format_response_raw()` (a response
formatter) on the request object instead of `build_http_request()`.
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

    def test_not_uses_scan_pipeline(self):
        assert getattr(PrototypePollutionCheck, "uses_scan_pipeline", False) is False

    def test_uses_analyze_api(self):
        assert PrototypePollutionCheck().uses_analyze_api is True


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

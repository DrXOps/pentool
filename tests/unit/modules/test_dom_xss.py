"""Unit tests for pentool/modules/scanner/checks/dom_xss.py.

DOM XSS is a PASSIVE static check: it inspects inline <script> blocks for a
source→sink dataflow (location.search/src → innerHTML/eval/write/...) without
issuing any extra request, so http_client is never touched.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

pytest.importorskip("pentool.modules.scanner")


class TestCheckDomXss:
    def test_source_to_sink_found(self) -> None:
        from pentool.modules.scanner.checks.dom_xss import _check_dom_xss

        pairs = _check_dom_xss("<script>var q = location.search; document.write(q)</script>")
        assert pairs, "expected a (source, sink) pair for location.search → document.write"
        assert any("location.search" in s for s, _ in pairs)
        assert any("document.write" in sink for _, sink in pairs)

    def test_source_without_sink_no_finding(self) -> None:
        from pentool.modules.scanner.checks.dom_xss import _check_dom_xss

        # location.search present but no sink assignment in the same block.
        assert _check_dom_xss("<script>var q = location.search; console.log(q)</script>") == []

    def test_sink_without_source_no_finding(self) -> None:
        from pentool.modules.scanner.checks.dom_xss import _check_dom_xss

        # element.innerHTML is used, but no source flows into it.
        assert _check_dom_xss('<script>el.innerHTML = "static"</script>') == []

    def test_no_script_no_finding(self) -> None:
        from pentool.modules.scanner.checks.dom_xss import _check_dom_xss

        assert _check_dom_xss("<html><body>plain</body></html>") == []

    def test_eval_sink_detected(self) -> None:
        from pentool.modules.scanner.checks.dom_xss import _check_dom_xss

        pairs = _check_dom_xss("<script>eval(location.hash.substring(1))</script>")
        assert any("eval" in sink for _, sink in pairs)


def _mk_request() -> "ParsedRequest":
    from pentool.utils.parser import ParsedRequest

    return ParsedRequest(method="GET", url="http://x.com/page", headers={}, body="")


class TestDOMXSSCheckScan:
    @pytest.mark.asyncio
    async def test_finds_dom_xss_in_response(self) -> None:
        from pentool.modules.scanner.checks.dom_xss import DOMXSSCheck
        from pentool.utils.parser import ParsedRequest, ParsedResponse

        req = ParsedRequest(method="GET", url="http://x.com/page", headers={}, body="")
        resp = ParsedResponse(
            status=200,
            headers={"content-type": "text/html"},
            body='<html><script>var q = location.search; document.write(q)</script></html>',
        )
        findings = await DOMXSSCheck().scan(req, resp, MagicMock())
        assert any(f.type == "dom_xss" for f in findings)
        assert any("Potential DOM XSS" in f.name for f in findings)

    @pytest.mark.asyncio
    async def test_no_script_returns_none(self) -> None:
        from pentool.modules.scanner.checks.dom_xss import DOMXSSCheck
        from pentool.utils.parser import ParsedResponse

        req = _mk_request()
        resp = ParsedResponse(status=200, headers={}, body="<html>no script here</html>")
        findings = await DOMXSSCheck().scan(req, resp, MagicMock())
        assert findings == []

    @pytest.mark.asyncio
    async def test_sink_without_source_returns_none(self) -> None:
        from pentool.modules.scanner.checks.dom_xss import DOMXSSCheck
        from pentool.utils.parser import ParsedResponse

        req = _mk_request()
        resp = ParsedResponse(
            status=200,
            headers={},
            body='<script>document.getElementById("a").innerHTML = "x"</script>',
        )
        findings = await DOMXSSCheck().scan(req, resp, MagicMock())
        assert findings == []

    @pytest.mark.asyncio
    async def test_response_none_returns_none(self) -> None:
        from pentool.modules.scanner.checks.dom_xss import DOMXSSCheck

        findings = await DOMXSSCheck().scan(_mk_request(), None, MagicMock())
        assert findings == []


class TestDOMXSSEngineIntegration:
    """DOM XSS surfaced through ScanEngine's passive run."""

    @pytest.fixture(autouse=True)
    def _reset_session_license(self) -> None:
        import pentool.core.license as lic_mod

        saved = lic_mod._session_license
        lic_mod._session_license = None
        yield
        lic_mod._session_license = saved

    @pytest.mark.asyncio
    async def test_engine_surfaces_dom_xss(self) -> None:
        # DOM XSS is a PASSIVE check — it never runs in the active phase
        # (run_active_on_requests filters `if not check.passive`). The passive
        # path is run_passive(request, response), which is what a real scan
        # uses to surface passive findings.
        from unittest.mock import MagicMock

        from pentool.modules.scanner.checks.dom_xss import DOMXSSCheck
        from pentool.modules.scanner.engine import ScanEngine
        from pentool.utils.parser import ParsedRequest, ParsedResponse

        engine = ScanEngine(db_path=":memory:", http_client=MagicMock())
        engine.register_check(DOMXSSCheck())
        req = ParsedRequest(method="GET", url="http://x.com/page", headers={}, body="")
        resp = ParsedResponse(
            status=200,
            headers={},
            body='<script>eval(location.hash.substring(1))</script>',
        )
        findings = await engine.run_passive(req, resp)
        assert any(f.type == "dom_xss" for f in findings)

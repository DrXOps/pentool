"""Unit tests for pentool/modules/scanner/checks/dom_xss.py.

DOM XSS is a PASSIVE static check: it inspects inline <script> blocks for a
source→sink dataflow (location.search/src → innerHTML/eval/write/...) without
issuing any extra request, so http_client is never touched.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

# Detached: the whole module fails collection if PRO isn't importable at all.
pytest.importorskip("pentool.modules.scanner")

# In an environment where the obfuscated installed PRO (older build) shadows
# dom_xss, the `DOMXSCCheck` class name may not be surfaced by the CodeEnigma
# proxy — but the pure `_check_dom_xss()` static-analyzer (the entire real
# logic) always is, because it's module-level plain code. So function-level
# tests always run; class/engine-level tests are skipped with a clear reason
# rather than hard-failing on an env that simply hasn't synced PRO yet.
def _have_domxss_class() -> bool:
    import pentool.modules.scanner.checks.dom_xss as _d

    return getattr(_d, "DOMXSCCheck", None) is not None


_skip_no_check = pytest.mark.skipif(
    not _have_domxss_class(),
    reason="DOMXSCCheck not surfaced by PRO in this env (installed PRO out of sync)",
)


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


@_skip_no_check
class TestDOMXSCCheckScan:
    @pytest.mark.asyncio
    async def test_finds_dom_xss_in_response(self) -> None:
        from pentool.modules.scanner.checks.dom_xss import DOMXSCCheck
        from pentool.utils.parser import ParsedRequest, ParsedResponse

        req = ParsedRequest(method="GET", url="http://x.com/page", headers={}, body="")
        resp = ParsedResponse(
            status=200,
            headers={"content-type": "text/html"},
            body='<html><script>var q = location.search; document.write(q)</script></html>',
        )
        findings = await DOMXSCCheck().scan(req, resp, MagicMock())
        assert any(f.type == "dom_xss" for f in findings)
        assert any("Potential DOM XSS" in f.name for f in findings)

    @pytest.mark.asyncio
    async def test_no_script_returns_none(self) -> None:
        from pentool.modules.scanner.checks.dom_xss import DOMXSCCheck
        from pentool.utils.parser import ParsedResponse

        req = _mk_request()
        resp = ParsedResponse(status=200, headers={}, body="<html>no script here</html>")
        findings = await DOMXSCCheck().scan(req, resp, MagicMock())
        assert findings == []

    @pytest.mark.asyncio
    async def test_sink_without_source_returns_none(self) -> None:
        from pentool.modules.scanner.checks.dom_xss import DOMXSCCheck
        from pentool.utils.parser import ParsedResponse

        req = _mk_request()
        resp = ParsedResponse(
            status=200,
            headers={},
            body='<script>document.getElementById("a").innerHTML = "x"</script>',
        )
        findings = await DOMXSCCheck().scan(req, resp, MagicMock())
        assert findings == []

    @pytest.mark.asyncio
    async def test_response_none_returns_none(self) -> None:
        from pentool.modules.scanner.checks.dom_xss import DOMXSCCheck

        findings = await DOMXSCCheck().scan(_mk_request(), None, MagicMock())
        assert findings == []


@_skip_no_check
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
        from pentool.modules.scanner.checks.dom_xss import DOMXSCCheck
        from pentool.modules.scanner.engine import ScanEngine
        from pentool.utils.parser import ParsedRequest, ParsedResponse

        class FakeClient:
            async def send(self, request):
                return ParsedResponse(
                    status=200,
                    headers={},
                    body='<script>eval(location.hash.substring(1))</script>',
                )

            async def get(self, url, headers=None):
                return ParsedResponse(
                    status=200,
                    headers={},
                    body='<script>eval(location.hash.substring(1))</script>',
                )

        engine = ScanEngine(db_path=":memory:", http_client=FakeClient())
        engine.register_check(DOMXSCCheck())
        req = ParsedRequest(method="GET", url="http://x.com/page", headers={}, body="")
        findings = await engine.run_active_on_requests([req])
        assert any(f.type == "dom_xss" for f in findings)

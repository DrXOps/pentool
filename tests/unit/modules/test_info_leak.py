"""Unit tests for pentool/modules/scanner/checks/info_leak.py.

InfoLeakCheck is a PASSIVE check: it inspects response headers for
server/technology-disclosure headers (Server, X-Powered-By, X-AspNet-Version,
X-Generator, Via, ...) and flags them. Header matching is case-insensitive.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

pytest.importorskip("pentool.modules.scanner")


class TestInfoLeakCheck:
    @pytest.mark.asyncio
    async def test_flags_server_header(self) -> None:
        from pentool.modules.scanner.checks.info_leak import InfoLeakCheck
        from pentool.utils.parser import ParsedRequest, ParsedResponse

        req = ParsedRequest(method="GET", url="http://x.com/", headers={}, body="")
        resp = ParsedResponse(status=200, headers={"Server": "Apache/2.4.1"}, body="")
        findings = await InfoLeakCheck().scan(req, resp, MagicMock())
        assert any(f.type == "info_leak" for f in findings)
        assert any(f.parameter == "Server" for f in findings)

    @pytest.mark.asyncio
    async def test_flags_x_powered_by(self) -> None:
        from pentool.modules.scanner.checks.info_leak import InfoLeakCheck
        from pentool.utils.parser import ParsedRequest, ParsedResponse

        req = ParsedRequest(method="GET", url="http://x.com/", headers={}, body="")
        resp = ParsedResponse(status=200, headers={"X-Powered-By": "PHP/8.1"}, body="")
        findings = await InfoLeakCheck().scan(req, resp, MagicMock())
        assert any(f.parameter == "X-Powered-By" for f in findings)

    @pytest.mark.asyncio
    async def test_flags_multiple_leaky_headers(self) -> None:
        from pentool.modules.scanner.checks.info_leak import InfoLeakCheck
        from pentool.utils.parser import ParsedRequest, ParsedResponse

        req = ParsedRequest(method="GET", url="http://x.com/", headers={}, body="")
        resp = ParsedResponse(
            status=200,
            headers={"Server": "nginx", "X-AspNet-Version": "4.0", "Via": "1.1 proxy"},
            body="",
        )
        findings = await InfoLeakCheck().scan(req, resp, MagicMock())
        params = {f.parameter for f in findings}
        assert {"Server", "X-AspNet-Version", "Via"} <= params

    @pytest.mark.asyncio
    async def test_no_leaky_headers_returns_none(self) -> None:
        from pentool.modules.scanner.checks.info_leak import InfoLeakCheck
        from pentool.utils.parser import ParsedRequest, ParsedResponse

        req = ParsedRequest(method="GET", url="http://x.com/", headers={}, body="")
        resp = ParsedResponse(
            status=200,
            headers={"Content-Type": "text/html", "Cache-Control": "no-cache"},
            body="",
        )
        findings = await InfoLeakCheck().scan(req, resp, MagicMock())
        assert findings == []

    @pytest.mark.asyncio
    async def test_header_matching_is_case_insensitive(self) -> None:
        from pentool.modules.scanner.checks.info_leak import InfoLeakCheck
        from pentool.utils.parser import ParsedRequest, ParsedResponse

        req = ParsedRequest(method="GET", url="http://x.com/", headers={}, body="")
        resp = ParsedResponse(status=200, headers={"server": "nginx"}, body="")
        findings = await InfoLeakCheck().scan(req, resp, MagicMock())
        assert any(f.type == "info_leak" for f in findings)

    @pytest.mark.asyncio
    async def test_response_none_returns_none(self) -> None:
        from pentool.modules.scanner.checks.info_leak import InfoLeakCheck
        from pentool.utils.parser import ParsedRequest

        req = ParsedRequest(method="GET", url="http://x.com/", headers={}, body="")
        findings = await InfoLeakCheck().scan(req, None, MagicMock())
        assert findings == []

    @pytest.mark.asyncio
    async def test_evidence_contains_value(self) -> None:
        from pentool.modules.scanner.checks.info_leak import InfoLeakCheck
        from pentool.utils.parser import ParsedRequest, ParsedResponse

        req = ParsedRequest(method="GET", url="http://x.com/", headers={}, body="")
        resp = ParsedResponse(status=200, headers={"Server": "Apache/2.4.1"}, body="")
        findings = await InfoLeakCheck().scan(req, resp, MagicMock())
        leak = next(f for f in findings if f.parameter == "Server")
        assert "Apache/2.4.1" in leak.evidence

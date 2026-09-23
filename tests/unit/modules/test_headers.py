"""Unit tests for pentool/modules/scanner/checks/headers.py.

MissingSecurityHeadersCheck is a PASSIVE check: it inspects response headers
for the presence of required security headers (X-Content-Type-Options,
X-Frame-Options, CSP, Strict-Transport-Security, Referrer-Policy). Missing →
"missing_security_header"; X-Content-Type-Options without a "nosniff" value →
"weak_security_header".
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

pytest.importorskip("pentool.modules.scanner")


def _mk_check():
    from pentool.modules.scanner.checks.headers import MissingSecurityHeadersCheck
    return MissingSecurityHeadersCheck()


async def _scan(req, resp):
    return await _mk_check().scan(req, resp, MagicMock())


def _mk_request():
    from pentool.utils.parser import ParsedRequest

    return ParsedRequest(method="GET", url="http://x.com/", headers={}, body="")


class TestMissingSecurityHeaders:
    @pytest.mark.asyncio
    async def test_flags_all_missing(self) -> None:
        from pentool.utils.parser import ParsedResponse

        req = _mk_request()
        resp = ParsedResponse(status=200, headers={}, body="")
        findings = await _scan(req, resp)
        missing = [f for f in findings if f.type == "missing_security_header"]
        assert len(missing) >= 1
        assert {"X-Content-Type-Options", "X-Frame-Options", "Content-Security-Policy",
                "Strict-Transport-Security", "Referrer-Policy"} <= {f.parameter for f in missing}

    @pytest.mark.asyncio
    async def test_flags_only_missing_one(self) -> None:
        from pentool.utils.parser import ParsedResponse

        req = _mk_request()
        resp = ParsedResponse(
            status=200,
            headers={
                "X-Content-Type-Options": "nosniff",
                "X-Frame-Options": "DENY",
                "Content-Security-Policy": "default-src 'self'",
                "Strict-Transport-Security": "max-age=1000",
            },
            body="",
        )
        findings = await _scan(req, resp)
        # Referrer-Policy is absent → exactly one missing finding for it.
        missing = [f for f in findings if f.type == "missing_security_header"]
        assert [f.parameter for f in missing] == ["Referrer-Policy"]

    @pytest.mark.asyncio
    async def test_all_present_returns_none(self) -> None:
        from pentool.utils.parser import ParsedResponse

        req = _mk_request()
        resp = ParsedResponse(
            status=200,
            headers={
                "X-Content-Type-Options": "nosniff",
                "X-Frame-Options": "DENY",
                "Content-Security-Policy": "default-src 'self'",
                "Strict-Transport-Security": "max-age=1000",
                "Referrer-Policy": "strict-origin-when-cross-origin",
            },
            body="",
        )
        findings = await _scan(req, resp)
        assert findings == []

    @pytest.mark.asyncio
    async def test_weak_x_content_type_options(self) -> None:
        from pentool.utils.parser import ParsedResponse

        req = _mk_request()
        resp = ParsedResponse(status=200, headers={"X-Content-Type-Options": "sniff"}, body="")
        findings = await _scan(req, resp)
        weak = [f for f in findings if f.type == "weak_security_header"]
        assert any(f.parameter == "X-Content-Type-Options" for f in weak)

    @pytest.mark.asyncio
    async def test_nosniff_value_not_flagged_weak(self) -> None:
        from pentool.utils.parser import ParsedResponse

        req = _mk_request()
        resp = ParsedResponse(status=200, headers={"X-Content-Type-Options": "nosniff"}, body="")
        findings = await _scan(req, resp)
        assert not any(f.type == "weak_security_header" for f in findings)

    @pytest.mark.asyncio
    async def test_header_matching_is_case_insensitive(self) -> None:
        from pentool.utils.parser import ParsedResponse

        req = _mk_request()
        # All headers present but lowercase name → not missing.
        resp = ParsedResponse(
            status=200,
            headers={
                "x-content-type-options": "nosniff",
                "x-frame-options": "DENY",
                "content-security-policy": "default-src 'self'",
                "strict-transport-security": "max-age=1000",
                "referrer-policy": "strict-origin-when-cross-origin",
            },
            body="",
        )
        findings = await _scan(req, resp)
        assert findings == []

    @pytest.mark.asyncio
    async def test_response_none_returns_none(self) -> None:
        findings = await _mk_check().scan(_mk_request(), None, MagicMock())
        assert findings == []

"""Unit tests for pentool/modules/scanner/checks/sensitive_data.py.

SensitiveDataCheck is a PASSIVE check: it scans the response body for leaked
secrets (AWS access keys, private keys, JWT tokens, ...) without extra
requests, so http_client is never touched.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

pytest.importorskip("pentool.modules.scanner")

from pentool.utils.parser import ParsedRequest, ParsedResponse  # noqa: E402


def _mk_request() -> ParsedRequest:
    return ParsedRequest(
        method="GET",
        url="http://target.example.com/page?id=1",
        headers={"Host": "target.example.com"},
        body="",
    )


def _mk_client():
    client = MagicMock()
    client.send = MagicMock(return_value=None)
    return client


# A realistic JWT (header.payload.signature — each part >= 10 chars).
_JWT = (
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9"
    ".eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6IkpvaG4gRG9lIiwiaWF0IjoxNTE2MjM5MDIyfQ"
    ".SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV_adQssw5c"
)


class TestSensitiveDataCheck:
    @pytest.mark.asyncio
    async def test_aws_key_detected(self) -> None:
        from pentool.modules.scanner.checks.sensitive_data import SensitiveDataCheck
        from pentool.utils.parser import ParsedResponse

        check = SensitiveDataCheck()
        resp = ParsedResponse(200, "OK", {}, "AKIA1234567890ABCDEF")
        findings = await check.scan(_mk_request(), resp, _mk_client())
        assert len(findings) > 0, "Expected finding for AWS Access Key"
        assert any("AWS" in f.name for f in findings)

    @pytest.mark.asyncio
    async def test_private_key_detected(self) -> None:
        from pentool.modules.scanner.checks.sensitive_data import SensitiveDataCheck
        from pentool.utils.parser import ParsedResponse

        check = SensitiveDataCheck()
        body = "-----BEGIN RSA PRIVATE KEY-----\nMIIE...\n-----END RSA PRIVATE KEY-----"
        resp = ParsedResponse(200, "OK", {}, body)
        findings = await check.scan(_mk_request(), resp, MagicMock())
        assert len(findings) > 0, "Expected finding for RSA Private Key"
        assert any("Private Key" in f.name for f in findings)

    @pytest.mark.asyncio
    async def test_no_false_positive_clean_response(self) -> None:
        from pentool.modules.scanner.checks.sensitive_data import SensitiveDataCheck
        from pentool.utils.parser import ParsedResponse

        check = SensitiveDataCheck()
        resp = ParsedResponse(200, "OK", {}, "Hello World")
        findings = await check.scan(_mk_request(), resp, MagicMock())
        assert len(findings) == 0, f"Expected no findings for clean response, got: {findings}"

    @pytest.mark.asyncio
    async def test_jwt_token_in_body_detected(self) -> None:
        from pentool.modules.scanner.checks.sensitive_data import SensitiveDataCheck
        from pentool.utils.parser import ParsedResponse

        check = SensitiveDataCheck()
        resp = ParsedResponse(200, "OK", {}, f"token: {_JWT}")
        findings = await check.scan(_mk_request(), resp, MagicMock())
        assert len(findings) > 0, "Expected finding for JWT token in body"
        assert any("JWT" in f.name for f in findings)

    @pytest.mark.asyncio
    async def test_response_none_returns_none(self) -> None:
        from pentool.modules.scanner.checks.sensitive_data import SensitiveDataCheck

        findings = await SensitiveDataCheck().scan(_mk_request(), None, MagicMock())
        assert findings == []

"""Unit tests for pentool/modules/scanner/checks/cors.py.

CORSCheck is an ACTIVE check (inherits BaseActiveCheck): it builds an
Origin-header injection point and probes with attacker origins, flagging
`Access-Control-Allow-Origin: *` + credentials, or a reflected evil origin
with credentials. The engine passes response=None to scan(), so the old
passive branch is gone — these tests drive the active prober by mocking
http_client.get/post.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

pytest.importorskip("pentool.modules.scanner")

from pentool.utils.parser import ParsedRequest, ParsedResponse  # noqa: E402


@pytest.fixture
def base_request() -> ParsedRequest:
    return ParsedRequest(
        method="GET",
        url="http://target.example.com/page?id=1",
        headers={"Host": "target.example.com"},
        body="",
    )


class TestCorsCheck:
    @pytest.mark.asyncio
    async def test_is_base_active_check(self) -> None:
        from pentool.modules.scanner.base import BaseActiveCheck
        from pentool.modules.scanner.checks.cors import CORSCheck

        assert issubclass(CORSCheck, BaseActiveCheck)

    @pytest.mark.asyncio
    async def test_cors_wildcard_with_credentials_detected(self, base_request) -> None:
        """Access-Control-Allow-Origin: * + credentials — flagged via the
        active Origin probe."""
        from pentool.modules.scanner.checks.cors import CORSCheck

        check = CORSCheck()
        resp = ParsedResponse(
            status=200,
            headers={
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Credentials": "true",
            },
            body="OK",
        )

        client = MagicMock()
        client.get = AsyncMock(return_value=resp)

        findings = await check.scan(base_request, None, client)
        assert len(findings) > 0, "Expected CORS finding for wildcard + credentials"
        assert any("cors" in f.type.lower() or "CORS" in f.name for f in findings)

    @pytest.mark.asyncio
    async def test_cors_origin_reflected_active(self, base_request) -> None:
        """Active check: evil origin reflected with credentials."""
        from pentool.modules.scanner.checks.cors import CORSCheck

        check = CORSCheck()
        clean_resp = ParsedResponse(200, "OK", {}, "OK")
        evil_resp = ParsedResponse(
            status=200,
            headers={
                "Access-Control-Allow-Origin": "https://evil.com",
                "Access-Control-Allow-Credentials": "true",
            },
            body="OK",
        )

        client = MagicMock()
        client.get = AsyncMock(return_value=evil_resp)
        client.post = AsyncMock(return_value=evil_resp)

        findings = await check.scan(base_request, clean_resp, client)
        assert len(findings) > 0, "Expected CORS finding for reflected evil origin with credentials"

    @pytest.mark.asyncio
    async def test_cors_no_finding_normal_response(self, base_request) -> None:
        """A normal response without CORS headers yields no findings."""
        from pentool.modules.scanner.checks.cors import CORSCheck

        check = CORSCheck()
        resp = ParsedResponse(200, "OK", {"Content-Type": "text/html"}, "Hello")

        client = MagicMock()
        client.get = AsyncMock(return_value=resp)
        client.post = AsyncMock(return_value=resp)

        findings = await check.scan(base_request, resp, client)
        assert len(findings) == 0, f"Expected no findings, got {findings}"

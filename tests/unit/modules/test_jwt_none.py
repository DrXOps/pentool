"""Unit tests for pentool/modules/scanner/checks/jwt_none.py.

Part of plan-2026-08-09 section 2.5 coverage (step 1: capture existing
behavior with unit tests, no check code changes yet): JWTNoneCheck is a
scan()-pipeline check whose logic lives in `scan()` (analyze() is a stub
returning None). It inspects an Authorization/`x-*-token` header, rebuilds
JWT variants (alg:none, exp bypass, role escalation, kid injection) and
sends via http_client.get()/post(). Tests pin the current behavior before
any structural migration.
"""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock

pytest.importorskip("pentool.modules.scanner")

from pentool.modules.scanner.checks.jwt_none import (
    JWTNoneCheck,
    _b64_decode,
    _b64_encode,
    _build_expire_jwt,
    _build_kid_jwts,
    _build_none_jwt,
    _build_role_escalation_jwts,
    _find_jwt,
    _is_accepted,
    _set_bearer,
)
from pentool.utils.parser import ParsedRequest, ParsedResponse

ACCEPTED_BODY = "Welcome, user. Here is your dashboard data." * 2


def _make_jwt(header: dict, payload: dict) -> str:
    sig = _b64_encode({"sig": "x"})
    return f"{_b64_encode(header)}.{_b64_encode(payload)}.{sig}"


JWT_HEADER = {"alg": "HS256", "typ": "JWT"}


def _make_request(
    url: str, method: str = "GET", headers: dict | None = None, body: str = ""
) -> ParsedRequest:
    return ParsedRequest(method=method, url=url, headers=headers or {}, body=body)


def _bearer_request(payload: dict, header: dict | None = None) -> ParsedRequest:
    token = _make_jwt(header or JWT_HEADER, payload)
    return _make_request(
        "http://target/api", headers={"Authorization": f"Bearer {token}"}
    )


def _accepted_client(**kwargs) -> MagicMock:
    client = MagicMock()
    client.get = AsyncMock(return_value=kwargs.get("get", ParsedResponse(200, "OK", {}, ACCEPTED_BODY)))
    client.post = AsyncMock(return_value=kwargs.get("post", ParsedResponse(200, "OK", {}, ACCEPTED_BODY)))
    return client


class TestMeta:
    def test_name(self):
        assert JWTNoneCheck.name == "jwt_none"

    def test_uses_scan_pipeline(self):
        assert JWTNoneCheck.uses_scan_pipeline is True


class TestHelpers:
    def test_b64_roundtrip(self):
        d = {"alg": "none", "sub": "1"}
        assert _b64_decode(_b64_encode(d)) == d

    def test_find_jwt_bearer(self):
        t = _make_jwt(JWT_HEADER, {"sub": "1"})
        found = _find_jwt({"Authorization": f"Bearer {t}"})
        assert found is not None
        name, tok = found
        assert name == "Authorization"
        assert tok == t

    def test_find_jwt_returns_none_without_jwt(self):
        assert _find_jwt({"Authorization": "Basic ABC"}) is None
        assert _find_jwt({"Host": "x"}) is None

    def test_set_bearer_preserves_scheme(self):
        assert _set_bearer("Authorization", "Bearer abc", "AAA") == "Bearer AAA"
        assert _set_bearer("x-jwt-token", "abc", "AAA") == "AAA"

    def test_is_accepted(self):
        assert _is_accepted(200, ACCEPTED_BODY)
        assert not _is_accepted(401, ACCEPTED_BODY)
        assert not _is_accepted(200, "token invalid or expired")

    def test_build_none_jwt_variants(self):
        variants = _build_none_jwt(JWT_HEADER, {"sub": "1"})
        assert len(variants) == 4
        for alg, token in variants:
            decoded = _b64_decode(token.split(".")[0])
            assert decoded["alg"] == alg

    def test_build_expire_jwt_only_with_exp(self):
        assert _build_expire_jwt(JWT_HEADER, {"sub": "1"}) is None
        tok = _build_expire_jwt(JWT_HEADER, {"sub": "1", "exp": 100})
        assert tok is not None
        assert _b64_decode(tok.split(".")[1])["exp"] > 4000000000


class TestScanPhase1AlgNone:
    @pytest.mark.asyncio
    async def test_alg_none_findings_when_accepted(self):
        check = JWTNoneCheck()
        req = _bearer_request({"sub": "1"})
        client = _accepted_client()  # every variant accepted
        findings = await check.scan(req, None, client)
        assert any(f.type == "jwt_none" for f in findings)
        assert any("alg:None" in f.name or "alg:" in f.name for f in findings)


class TestScanNoJwt:
    @pytest.mark.asyncio
    async def test_no_jwt_no_finding(self):
        check = JWTNoneCheck()
        req = _make_request("http://target/api")
        client = _accepted_client()
        findings = await check.scan(req, None, client)
        assert findings == []

    @pytest.mark.asyncio
    async def test_401_skips(self):
        # orig_status 401 -> check bails out immediately.
        check = JWTNoneCheck()
        req = _bearer_request({"sub": "1"})
        resp = ParsedResponse(401, "Unauthorized", {}, "denied")
        client = _accepted_client()
        findings = await check.scan(req, resp, client)
        assert findings == []


class TestEngineIntegration:
    """End-to-end through ScanEngine — the check actually finds a bypass
    when the server accepts every reconstructed JWT."""

    @pytest.fixture(autouse=True)
    def _reset_session_license(self):
        import pentool.core.license as lic_mod
        saved = lic_mod._session_license
        lic_mod._session_license = None
        yield
        lic_mod._session_license = saved

    @pytest.mark.asyncio
    async def test_engine_detects_jwt_bypass(self):
        from pentool.modules.scanner.engine import ScanEngine

        class FakeClient:
            async def send(self, request):
                return ParsedResponse(200, "OK", {}, ACCEPTED_BODY)

            async def get(self, url, headers=None):
                return ParsedResponse(200, "OK", {}, ACCEPTED_BODY)

            async def post(self, url, body="", headers=None):
                return ParsedResponse(200, "OK", {}, ACCEPTED_BODY)

        engine = ScanEngine(db_path=":memory:", http_client=FakeClient())
        engine.register_check(JWTNoneCheck())
        req = _bearer_request({"sub": "1"})
        findings = await engine.run_active_on_requests([req])
        assert any(f.type == "jwt_none" for f in findings)

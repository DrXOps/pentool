"""Security: scanner checks detect vulnerabilities in mocked responses."""
from __future__ import annotations

import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, MagicMock

from pentool.modules.scanner.base import Finding
from pentool.utils.parser import ParsedRequest, ParsedResponse


@pytest.fixture
def mock_http_client():
    client = MagicMock()
    client.send = AsyncMock(return_value=ParsedResponse(
        status=200,
        reason="OK",
        headers={"Content-Type": "text/html"},
        body="Normal response",
    ))
    return client


@pytest.fixture
def base_request():
    return ParsedRequest(
        method="GET",
        url="http://target.example.com/page?id=1",
        headers={"Host": "target.example.com"},
        body="",
    )


# ── CORS ─────────────────────────────────────────────────────────────────────

class TestCorsCheck:
    """CORS check tests.

    CORSCheck.scan() is an ACTIVE check that probes with attacker origins.
    We mock http_client.get to return a response with the reflected evil origin.
    """

    @pytest.mark.security
    async def test_cors_wildcard_with_credentials_detected(self, base_request):
        """ACAO: * + credentials в passive-ветке scan()."""
        from pentool.modules.scanner.checks.cors import CORSCheck

        check = CORSCheck()
        # Passive branch: original response already has CORS issue
        resp = ParsedResponse(
            status=200,
            reason="OK",
            headers={
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Credentials": "true",
            },
            body="OK",
        )

        # http_client не вызовется в passive-ветке, но нужен для сигнатуры
        client = MagicMock()
        client.get = AsyncMock(return_value=resp)

        findings = await check.scan(base_request, resp, client)
        assert len(findings) > 0, "Expected CORS finding for wildcard + credentials"
        assert any(
            "cors" in f.type.lower() or "CORS" in f.name
            for f in findings
        )

    @pytest.mark.security
    async def test_cors_origin_reflected_active(self, base_request):
        """Active check: evil origin отражается с credentials."""
        from pentool.modules.scanner.checks.cors import CORSCheck

        check = CORSCheck()
        # В passive-ветке нет findings (нет CORS заголовков)
        clean_resp = ParsedResponse(200, "OK", {}, "OK")

        # Active: mock возвращает response с reflected evil origin
        evil_resp = ParsedResponse(
            status=200,
            reason="OK",
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

    @pytest.mark.security
    async def test_cors_no_finding_normal_response(self, base_request, mock_http_client):
        """Обычный ответ без CORS заголовков не должен давать findings."""
        from pentool.modules.scanner.checks.cors import CORSCheck

        check = CORSCheck()
        resp = ParsedResponse(200, "OK", {"Content-Type": "text/html"}, "Hello")

        # Active probes — все возвращают обычный ответ без ACAO
        mock_http_client.get = AsyncMock(return_value=resp)
        mock_http_client.post = AsyncMock(return_value=resp)

        findings = await check.scan(base_request, resp, mock_http_client)
        assert len(findings) == 0, f"Expected no findings, got {findings}"


# ── Sensitive Data ────────────────────────────────────────────────────────────

class TestSensitiveDataCheck:
    """SensitiveDataCheck — passive, анализирует тело ответа."""

    @pytest.mark.security
    async def test_aws_key_detected(self, base_request, mock_http_client):
        from pentool.modules.scanner.checks.sensitive_data import SensitiveDataCheck

        check = SensitiveDataCheck()
        resp = ParsedResponse(200, "OK", {}, "AKIA1234567890ABCDEF")
        findings = await check.scan(base_request, resp, mock_http_client)
        assert len(findings) > 0, "Expected finding for AWS Access Key"
        assert any("AWS" in f.name for f in findings), \
            f"Expected 'AWS' in finding name, got: {[f.name for f in findings]}"

    @pytest.mark.security
    async def test_private_key_detected(self, base_request, mock_http_client):
        from pentool.modules.scanner.checks.sensitive_data import SensitiveDataCheck

        check = SensitiveDataCheck()
        body = "-----BEGIN RSA PRIVATE KEY-----\nMIIE...\n-----END RSA PRIVATE KEY-----"
        resp = ParsedResponse(200, "OK", {}, body)
        findings = await check.scan(base_request, resp, mock_http_client)
        assert len(findings) > 0, "Expected finding for RSA Private Key"
        assert any("Private Key" in f.name for f in findings), \
            f"Expected 'Private Key' in finding name, got: {[f.name for f in findings]}"

    @pytest.mark.security
    async def test_no_false_positive_clean_response(self, base_request, mock_http_client):
        from pentool.modules.scanner.checks.sensitive_data import SensitiveDataCheck

        check = SensitiveDataCheck()
        resp = ParsedResponse(200, "OK", {}, "Hello World")
        findings = await check.scan(base_request, resp, mock_http_client)
        assert len(findings) == 0, f"Expected no findings for clean response, got: {findings}"

    @pytest.mark.security
    async def test_jwt_token_in_body_detected(self, base_request, mock_http_client):
        from pentool.modules.scanner.checks.sensitive_data import SensitiveDataCheck

        check = SensitiveDataCheck()
        # Настоящий JWT-подобный токен (header.payload.signature — каждая часть >= 10 символов)
        jwt_token = (
            "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9"
            ".eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6IkpvaG4gRG9lIiwiaWF0IjoxNTE2MjM5MDIyfQ"
            ".SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV_adQssw5c"
        )
        resp = ParsedResponse(200, "OK", {}, f"token: {jwt_token}")
        findings = await check.scan(base_request, resp, mock_http_client)
        assert len(findings) > 0, "Expected finding for JWT token in body"
        assert any("JWT" in f.name for f in findings), \
            f"Expected 'JWT' in finding name, got: {[f.name for f in findings]}"


# ── Proxy Scope ───────────────────────────────────────────────────────────────

class TestProxyScope:
    """Тестирование is_in_scope без запуска реального сервера."""

    @pytest.mark.security
    def test_empty_scope_allows_all(self):
        from pentool.modules.proxy import ProxyServer

        proxy = ProxyServer.__new__(ProxyServer)
        proxy.scope = []
        assert proxy.is_in_scope("example.com") is True
        assert proxy.is_in_scope("evil.com") is True

    @pytest.mark.security
    def test_scope_allows_listed_host(self):
        from pentool.modules.proxy import ProxyServer

        proxy = ProxyServer.__new__(ProxyServer)
        proxy.scope = ["example.com"]
        assert proxy.is_in_scope("example.com") is True

    @pytest.mark.security
    def test_scope_blocks_unlisted(self):
        from pentool.modules.proxy import ProxyServer

        proxy = ProxyServer.__new__(ProxyServer)
        proxy.scope = ["example.com"]
        assert proxy.is_in_scope("evil.com") is False

    @pytest.mark.security
    def test_wildcard_scope(self):
        from pentool.modules.proxy import ProxyServer

        proxy = ProxyServer.__new__(ProxyServer)
        proxy.scope = ["*.example.com"]
        assert proxy.is_in_scope("sub.example.com") is True

    @pytest.mark.security
    def test_wildcard_blocks_parent(self):
        from pentool.modules.proxy import ProxyServer

        proxy = ProxyServer.__new__(ProxyServer)
        proxy.scope = ["*.example.com"]
        assert proxy.is_in_scope("evil.com") is False

    @pytest.mark.security
    def test_scope_case_insensitive(self):
        from pentool.modules.proxy import ProxyServer

        proxy = ProxyServer.__new__(ProxyServer)
        # set_scope нормализует к lower(), но здесь мы проверяем is_in_scope напрямую
        # is_in_scope сам приводит host к lower(), поэтому паттерн тоже должен быть lower
        proxy.scope = ["example.com"]  # уже lower
        # host передаём в верхнем регистре — is_in_scope делает host.lower()
        assert proxy.is_in_scope("EXAMPLE.COM") is True


# ── License ───────────────────────────────────────────────────────────────────

class TestLicense:
    """Тесты license.py — без сетевых запросов."""

    @pytest.mark.security
    def test_get_machine_id_nonempty(self):
        from pentool.core.license import get_machine_id

        mid = get_machine_id()
        assert isinstance(mid, str)
        assert len(mid) > 0

    @pytest.mark.security
    def test_license_info_free_plan(self):
        from pentool.core.license import LicenseInfo

        info = LicenseInfo()
        assert info.plan == "free"
        assert info.valid is False

    @pytest.mark.security
    def test_license_info_status_text(self):
        from pentool.core.license import LicenseInfo

        info = LicenseInfo(valid=False)
        assert info.status_text == "FREE"

    @pytest.mark.security
    def test_license_info_is_pro_false(self):
        from pentool.core.license import LicenseInfo

        # valid=True но plan="free" → is_pro() == False
        info = LicenseInfo(valid=True, plan="free")
        assert info.is_pro() is False

    @pytest.mark.security
    def test_license_info_is_pro_true(self):
        from pentool.core.license import LicenseInfo

        info = LicenseInfo(valid=True, plan="pro")
        assert info.is_pro() is True

    @pytest.mark.security
    def test_has_feature_false_when_invalid(self):
        from pentool.core.license import LicenseInfo

        info = LicenseInfo(valid=False, features=["scanner_advanced"])
        assert info.has_feature("scanner_advanced") is False

    @pytest.mark.security
    def test_has_feature_true_when_valid(self):
        from pentool.core.license import LicenseInfo

        info = LicenseInfo(valid=True, features=["scanner_advanced"])
        assert info.has_feature("scanner_advanced") is True

"""Unit-тесты для core/license.py."""

from __future__ import annotations

import json
import time
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from pentool.core.license import (
    LicenseInfo,
    _GRACE_PERIOD_DAYS,
    _LICENSE_FILE,
    activate_license,
    deactivate_license,
    get_license,
    get_machine_id,
    get_session_license,
    refresh_session_license,
    _load_cached,
    _save_cached,
)


# ── LicenseInfo ────────────────────────────────────────────────────────────────

class TestLicenseInfo:
    def test_defaults(self):
        info = LicenseInfo()
        assert info.valid is False
        assert info.plan == "free"
        assert info.features == []
        assert info.expires is None
        assert info.machine_id == ""
        assert info.license_key == ""
        assert info.last_check is None
        assert info.error == ""

    def test_has_feature_false_when_invalid(self):
        info = LicenseInfo(valid=False, features=["scanner_pro"])
        assert info.has_feature("scanner_pro") is False

    def test_has_feature_true_when_valid(self):
        info = LicenseInfo(valid=True, plan="pro", features=["scanner_pro", "reports_pro"])
        assert info.has_feature("scanner_pro") is True
        assert info.has_feature("reports_pro") is True
        assert info.has_feature("unknown") is False

    def test_is_pro_false_when_invalid(self):
        info = LicenseInfo(valid=False, plan="pro")
        assert info.is_pro() is False

    def test_is_pro_false_when_free(self):
        info = LicenseInfo(valid=True, plan="free")
        assert info.is_pro() is False

    def test_is_pro_true_for_pro(self):
        info = LicenseInfo(valid=True, plan="pro")
        assert info.is_pro() is True

    def test_is_pro_true_for_enterprise(self):
        info = LicenseInfo(valid=True, plan="enterprise")
        assert info.is_pro() is True

    def test_status_text_free(self):
        info = LicenseInfo(valid=False)
        assert info.status_text == "FREE"

    def test_status_text_pro(self):
        info = LicenseInfo(valid=True, plan="pro")
        assert info.status_text == "PRO"

    def test_status_text_enterprise(self):
        info = LicenseInfo(valid=True, plan="enterprise")
        assert info.status_text == "ENTERPRISE"

    def test_expires_text_lifetime(self):
        info = LicenseInfo(expires=None)
        assert info.expires_text == "Lifetime"

    def test_expires_text_date(self):
        info = LicenseInfo(expires="2027-01-01")
        assert info.expires_text == "2027-01-01"


# ── get_machine_id ─────────────────────────────────────────────────────────────

class TestGetMachineId:
    def test_returns_32_hex_chars(self):
        mid = get_machine_id()
        assert len(mid) == 32
        assert all(c in "0123456789abcdef" for c in mid)

    def test_consistent(self):
        """Один и тот же machine_id при повторных вызовах."""
        assert get_machine_id() == get_machine_id()

    def test_fallback_on_socket_error(self):
        """Если socket недоступен — используется platform.node()."""
        with patch("pentool.core.license.uuid") as mock_uuid:
            mock_uuid.getnode.side_effect = OSError("no socket")
            # Функция должна вернуть 32 символа без exception
            mid = get_machine_id()
            assert len(mid) == 32


# ── Cache read/write ───────────────────────────────────────────────────────────

class TestCache:
    def test_load_cached_returns_none_when_no_file(self, tmp_path):
        with patch("pentool.core.license._LICENSE_FILE", tmp_path / "missing.dat"):
            assert _load_cached() is None

    def test_save_and_load_roundtrip(self, tmp_path):
        lic_file = tmp_path / ".pentool" / "license.dat"
        data = {"valid": True, "plan": "pro", "last_check": 1234567890.0}
        with patch("pentool.core.license._LICENSE_FILE", lic_file):
            _save_cached(data)
            loaded = _load_cached()
        assert loaded == data

    def test_load_cached_handles_corrupt_file(self, tmp_path):
        lic_file = tmp_path / "corrupt.dat"
        lic_file.write_text("NOT JSON", encoding="utf-8")
        with patch("pentool.core.license._LICENSE_FILE", lic_file):
            assert _load_cached() is None

    def test_save_creates_parent_dirs(self, tmp_path):
        lic_file = tmp_path / "deep" / "nested" / "license.dat"
        with patch("pentool.core.license._LICENSE_FILE", lic_file):
            _save_cached({"valid": False})
        assert lic_file.exists()


# ── get_license ────────────────────────────────────────────────────────────────

class TestGetLicense:
    def test_returns_free_when_no_cache(self, tmp_path):
        lic_file = tmp_path / "missing.dat"
        with patch("pentool.core.license._LICENSE_FILE", lic_file):
            info = get_license()
        assert info.valid is False
        assert info.plan == "free"

    def test_returns_cached_info_within_grace(self, tmp_path):
        lic_file = tmp_path / ".pentool" / "license.dat"
        data = {
            "valid": True,
            "plan": "pro",
            "features": ["scanner_pro"],
            "expires": None,
            "machine_id": "abc123",
            "license_key": "DEMO-1234-5678-ABCD",
            "last_check": time.time(),  # только что
        }
        lic_file.parent.mkdir(parents=True)
        lic_file.write_text(json.dumps(data), encoding="utf-8")
        with patch("pentool.core.license._LICENSE_FILE", lic_file):
            info = get_license()
        assert info.valid is True
        assert info.plan == "pro"
        assert "scanner_pro" in info.features

    def test_grace_period_expired_returns_free(self, tmp_path):
        lic_file = tmp_path / ".pentool" / "license.dat"
        expired_ts = time.time() - (_GRACE_PERIOD_DAYS + 1) * 24 * 3600
        data = {
            "valid": True,
            "plan": "pro",
            "features": ["scanner_pro"],
            "expires": None,
            "machine_id": "abc123",
            "license_key": "DEMO-1234-5678-ABCD",
            "last_check": expired_ts,
        }
        lic_file.parent.mkdir(parents=True)
        lic_file.write_text(json.dumps(data), encoding="utf-8")
        with patch("pentool.core.license._LICENSE_FILE", lic_file):
            info = get_license()
        assert info.valid is False
        assert info.plan == "free"
        assert "Grace period expired" in info.error

    def test_grace_period_boundary_still_valid(self, tmp_path):
        """Ровно за 1 секунду до истечения grace — ещё валидно."""
        lic_file = tmp_path / ".pentool" / "license.dat"
        almost_expired = time.time() - (_GRACE_PERIOD_DAYS * 24 * 3600 - 1)
        data = {
            "valid": True,
            "plan": "pro",
            "features": [],
            "expires": None,
            "machine_id": "abc",
            "license_key": "DEMO-0000-0000-0000",
            "last_check": almost_expired,
        }
        lic_file.parent.mkdir(parents=True)
        lic_file.write_text(json.dumps(data), encoding="utf-8")
        with patch("pentool.core.license._LICENSE_FILE", lic_file):
            info = get_license()
        assert info.valid is True


# ── activate_license ───────────────────────────────────────────────────────────

class TestActivateLicense:
    @pytest.mark.asyncio
    async def test_empty_key_returns_error(self, tmp_path):
        with patch("pentool.core.license._LICENSE_FILE", tmp_path / "l.dat"):
            info = await activate_license("")
        assert info.valid is False
        assert "empty" in info.error.lower()

    @pytest.mark.asyncio
    async def test_whitespace_key_returns_error(self, tmp_path):
        with patch("pentool.core.license._LICENSE_FILE", tmp_path / "l.dat"):
            info = await activate_license("   ")
        assert info.valid is False

    @pytest.mark.asyncio
    async def test_demo_key_activates_pro(self, tmp_path):
        """DEMO-XXXX-XXXX-XXXX → PRO offline fallback."""
        lic_file = tmp_path / "license.dat"
        with patch("pentool.core.license._LICENSE_FILE", lic_file):
            # Имитируем сбой сети чтобы упасть в offline fallback
            with patch("pentool.core.license.activate_license", wraps=None) as _:
                pass
            # Прямой тест offline пути: патчим aiohttp чтобы он падал
            with patch.dict("sys.modules", {"aiohttp": None}):
                info = await activate_license("DEMO-ABCD-1234-EFGH")
        assert info.valid is True
        assert info.plan == "pro"
        assert "scanner_pro" in info.features

    @pytest.mark.asyncio
    async def test_invalid_key_format_returns_error(self, tmp_path):
        """Ключ неправильного формата → ошибка."""
        lic_file = tmp_path / "license.dat"
        with patch("pentool.core.license._LICENSE_FILE", lic_file):
            with patch.dict("sys.modules", {"aiohttp": None}):
                info = await activate_license("INVALID-KEY")
        assert info.valid is False
        assert info.error != ""

    @pytest.mark.asyncio
    async def test_non_demo_valid_format_without_server_fails(self, tmp_path):
        """Валидный формат но не DEMO и нет сервера → ошибка."""
        lic_file = tmp_path / "license.dat"
        with patch("pentool.core.license._LICENSE_FILE", lic_file):
            with patch.dict("sys.modules", {"aiohttp": None}):
                info = await activate_license("ABCD-1234-EFGH-5678")
        assert info.valid is False

    @pytest.mark.asyncio
    async def test_server_success_saves_cache(self, tmp_path):
        """Успешный ответ сервера → кэшируется."""
        lic_file = tmp_path / "license.dat"
        server_resp = {
            "valid": True,
            "plan": "pro",
            "features": ["scanner_pro"],
            "expires": "2028-01-01",
        }

        mock_resp = AsyncMock()
        mock_resp.status = 200
        mock_resp.json = AsyncMock(return_value=server_resp)
        mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_resp.__aexit__ = AsyncMock(return_value=False)

        mock_session = AsyncMock()
        mock_session.post = MagicMock(return_value=mock_resp)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)

        mock_aiohttp = MagicMock()
        mock_aiohttp.ClientSession = MagicMock(return_value=mock_session)
        mock_aiohttp.ClientTimeout = MagicMock(return_value=MagicMock())

        with patch("pentool.core.license._LICENSE_FILE", lic_file):
            with patch.dict("sys.modules", {"aiohttp": mock_aiohttp}):
                info = await activate_license("PROD-AAAA-BBBB-CCCC")

        assert info.valid is True
        assert info.plan == "pro"
        assert lic_file.exists()
        cached = json.loads(lic_file.read_text())
        assert cached["valid"] is True
        assert cached["plan"] == "pro"

    @pytest.mark.asyncio
    async def test_server_returns_invalid(self, tmp_path):
        """Сервер вернул valid=False → не кэшируется."""
        lic_file = tmp_path / "license.dat"
        server_resp = {"valid": False, "plan": "free", "features": []}

        mock_resp = AsyncMock()
        mock_resp.status = 200
        mock_resp.json = AsyncMock(return_value=server_resp)
        mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_resp.__aexit__ = AsyncMock(return_value=False)

        mock_session = AsyncMock()
        mock_session.post = MagicMock(return_value=mock_resp)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)

        mock_aiohttp = MagicMock()
        mock_aiohttp.ClientSession = MagicMock(return_value=mock_session)
        mock_aiohttp.ClientTimeout = MagicMock(return_value=MagicMock())

        with patch("pentool.core.license._LICENSE_FILE", lic_file):
            with patch.dict("sys.modules", {"aiohttp": mock_aiohttp}):
                info = await activate_license("XXXX-YYYY-ZZZZ-0000")

        assert info.valid is False
        assert not lic_file.exists()


# ── deactivate_license ─────────────────────────────────────────────────────────

class TestDeactivateLicense:
    def test_removes_file(self, tmp_path):
        lic_file = tmp_path / "license.dat"
        lic_file.write_text('{"valid": true}', encoding="utf-8")
        with patch("pentool.core.license._LICENSE_FILE", lic_file):
            deactivate_license()
        assert not lic_file.exists()

    def test_no_error_when_file_missing(self, tmp_path):
        lic_file = tmp_path / "missing.dat"
        with patch("pentool.core.license._LICENSE_FILE", lic_file):
            deactivate_license()  # не должно падать


# ── Session cache ──────────────────────────────────────────────────────────────

class TestSessionCache:
    def test_get_session_license_caches(self, tmp_path):
        import pentool.core.license as lic_mod
        lic_mod._session_license = None  # сбрасываем
        with patch("pentool.core.license._LICENSE_FILE", tmp_path / "missing.dat"):
            info1 = get_session_license()
            info2 = get_session_license()
        assert info1 is info2  # тот же объект из кэша

    def test_refresh_session_license_with_info(self):
        import pentool.core.license as lic_mod
        custom = LicenseInfo(valid=True, plan="pro")
        result = refresh_session_license(custom)
        assert result is custom
        assert lic_mod._session_license is custom

    def test_refresh_session_license_none_reloads(self, tmp_path):
        import pentool.core.license as lic_mod
        lic_mod._session_license = None
        with patch("pentool.core.license._LICENSE_FILE", tmp_path / "missing.dat"):
            result = refresh_session_license(None)
        assert result is not None
        assert result.plan == "free"

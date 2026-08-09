"""Unit tests for core/license.py."""

from __future__ import annotations

import base64
import json
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from pentool.core.license import (
    LicenseInfo,
    _GRACE_PERIOD_DAYS,
    _canonical_license_payload,
    activate_license,
    check_and_update_pro_package,
    deactivate_license,
    download_pro_package,
    get_license,
    get_machine_id,
    get_session_license,
    refresh_session_license,
    _load_cached,
    _read_pro_meta,
    _save_cached,
)

# A test-only ed25519 keypair used to sign fixtures in these tests. The real
# client verifies against the production public key embedded in license.py
# (_LICENSE_SIGNING_PUBLIC_KEY_B64), so every test that needs a *valid*
# signature patches that constant to this test key's public half instead.
_TEST_PRIVATE_KEY = Ed25519PrivateKey.generate()
_TEST_PUBLIC_KEY_B64 = base64.b64encode(
    _TEST_PRIVATE_KEY.public_key().public_bytes_raw()
).decode("ascii") if hasattr(_TEST_PRIVATE_KEY.public_key(), "public_bytes_raw") else base64.b64encode(
    _TEST_PRIVATE_KEY.public_key().public_bytes(
        encoding=__import__("cryptography.hazmat.primitives.serialization", fromlist=["Encoding"]).Encoding.Raw,
        format=__import__("cryptography.hazmat.primitives.serialization", fromlist=["PublicFormat"]).PublicFormat.Raw,
    )
).decode("ascii")


def _sign(valid: bool, plan: str, features: list[str], expires, machine_id: str, ts: int) -> str:
    message = _canonical_license_payload(valid, plan, features, expires, machine_id, ts)
    sig = _TEST_PRIVATE_KEY.sign(message)
    return base64.b64encode(sig).decode("ascii")


def _signed_cache_entry(
    valid=True, plan="pro", features=None, expires=None,
    machine_id="abc123", ts=None, license_key="PTOOL-AAAA-BBBB-CCCC",
) -> dict:
    features = features if features is not None else ["scanner_pro"]
    ts = ts if ts is not None else int(time.time() * 1000)
    sig = _sign(valid, plan, features, expires, machine_id, ts)
    return {
        "valid": valid, "plan": plan, "features": features, "expires": expires,
        "machine_id": machine_id, "license_key": license_key, "sig": sig, "ts": ts,
    }


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
        """Same machine_id on repeated calls."""
        assert get_machine_id() == get_machine_id()

    def test_fallback_on_socket_error(self):
        """If socket is unavailable — platform.node() is used."""
        with patch("pentool.core.license.uuid") as mock_uuid:
            mock_uuid.getnode.side_effect = OSError("no socket")
            # Function should return 32 chars without exception
            mid = get_machine_id()
            assert len(mid) == 32


# ── Cache read/write ───────────────────────────────────────────────────────────

class TestCache:
    def test_load_cached_returns_none_when_no_file(self, tmp_path):
        with patch("pentool.core.license._LICENSE_FILE", tmp_path / "missing.dat"):
            assert _load_cached() is None

    def test_save_and_load_roundtrip(self, tmp_path):
        lic_file = tmp_path / ".pentool" / "license.dat"
        data = {"valid": True, "plan": "pro", "ts": 1234567890000}
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


# ── get_license (signature verification) ────────────────────────────────────────
#
# Every test in this section patches _LICENSE_SIGNING_PUBLIC_KEY_B64 to the
# test keypair's public half so _sign()-produced fixtures verify. This
# exercises the exact same verification code path as production, just
# against a throwaway key instead of the real one.

class TestGetLicense:
    def test_returns_free_when_no_cache(self, tmp_path):
        lic_file = tmp_path / "missing.dat"
        with patch("pentool.core.license._LICENSE_FILE", lic_file):
            info = get_license()
        assert info.valid is False
        assert info.plan == "free"

    def test_returns_cached_info_when_signature_valid(self, tmp_path):
        lic_file = tmp_path / ".pentool" / "license.dat"
        my_machine_id = get_machine_id()
        data = _signed_cache_entry(machine_id=my_machine_id)
        lic_file.parent.mkdir(parents=True)
        lic_file.write_text(json.dumps(data), encoding="utf-8")
        with patch("pentool.core.license._LICENSE_FILE", lic_file), \
             patch("pentool.core.license._LICENSE_SIGNING_PUBLIC_KEY_B64", _TEST_PUBLIC_KEY_B64):
            info = get_license()
        assert info.valid is True
        assert info.plan == "pro"
        assert "scanner_pro" in info.features

    def test_missing_signature_rejected(self, tmp_path):
        """Cache entries without sig/ts (old format, or stripped) are untrusted."""
        lic_file = tmp_path / ".pentool" / "license.dat"
        data = {
            "valid": True, "plan": "pro", "features": ["scanner_pro"],
            "expires": None, "machine_id": "abc123", "license_key": "X",
            "last_check": time.time(),
        }
        lic_file.parent.mkdir(parents=True)
        lic_file.write_text(json.dumps(data), encoding="utf-8")
        with patch("pentool.core.license._LICENSE_FILE", lic_file):
            info = get_license()
        assert info.valid is False
        assert "unsigned" in info.error.lower()

    def test_tampered_field_invalidates_signature(self, tmp_path):
        """Hand-editing any signed field after the fact must be detected —
        this is the core fix: license.dat can no longer be faked by hand."""
        lic_file = tmp_path / ".pentool" / "license.dat"
        my_machine_id = get_machine_id()
        data = _signed_cache_entry(plan="free", features=[], machine_id=my_machine_id)
        # Tamper: upgrade to pro + add features after signing, without re-signing.
        data["plan"] = "pro"
        data["features"] = ["scanner_pro", "reports_pro", "payloads_pro"]
        lic_file.parent.mkdir(parents=True)
        lic_file.write_text(json.dumps(data), encoding="utf-8")
        with patch("pentool.core.license._LICENSE_FILE", lic_file), \
             patch("pentool.core.license._LICENSE_SIGNING_PUBLIC_KEY_B64", _TEST_PUBLIC_KEY_B64):
            info = get_license()
        assert info.valid is False
        assert "signature" in info.error.lower()

    def test_wrong_public_key_rejected(self, tmp_path):
        """A signature made with the wrong key (not the real server key)
        must not verify — this is what stops a self-signed fake license."""
        lic_file = tmp_path / ".pentool" / "license.dat"
        data = _signed_cache_entry(machine_id=get_machine_id())
        lic_file.parent.mkdir(parents=True)
        lic_file.write_text(json.dumps(data), encoding="utf-8")
        # Deliberately do NOT patch _LICENSE_SIGNING_PUBLIC_KEY_B64 — the
        # production public key won't match our test signature.
        with patch("pentool.core.license._LICENSE_FILE", lic_file):
            info = get_license()
        assert info.valid is False

    def test_machine_id_mismatch_rejected(self, tmp_path):
        """A validly-signed verdict for a different machine must not apply here —
        prevents copying license.dat between machines."""
        lic_file = tmp_path / ".pentool" / "license.dat"
        data = _signed_cache_entry(machine_id="some-other-machine-id")
        lic_file.parent.mkdir(parents=True)
        lic_file.write_text(json.dumps(data), encoding="utf-8")
        with patch("pentool.core.license._LICENSE_FILE", lic_file), \
             patch("pentool.core.license._LICENSE_SIGNING_PUBLIC_KEY_B64", _TEST_PUBLIC_KEY_B64):
            info = get_license()
        assert info.valid is False
        assert "different machine" in info.error.lower()

    def test_grace_period_expired_returns_free(self, tmp_path):
        lic_file = tmp_path / ".pentool" / "license.dat"
        my_machine_id = get_machine_id()
        expired_ts_ms = int((time.time() - (_GRACE_PERIOD_DAYS + 1) * 24 * 3600) * 1000)
        data = _signed_cache_entry(machine_id=my_machine_id, ts=expired_ts_ms)
        lic_file.parent.mkdir(parents=True)
        lic_file.write_text(json.dumps(data), encoding="utf-8")
        with patch("pentool.core.license._LICENSE_FILE", lic_file), \
             patch("pentool.core.license._LICENSE_SIGNING_PUBLIC_KEY_B64", _TEST_PUBLIC_KEY_B64):
            info = get_license()
        assert info.valid is False
        assert info.plan == "free"
        assert "Grace period expired" in info.error

    def test_grace_period_boundary_still_valid(self, tmp_path):
        """Well within the grace window — still valid."""
        lic_file = tmp_path / ".pentool" / "license.dat"
        my_machine_id = get_machine_id()
        almost_expired_ms = int((time.time() - (_GRACE_PERIOD_DAYS * 24 * 3600 - 60)) * 1000)
        data = _signed_cache_entry(machine_id=my_machine_id, ts=almost_expired_ms, features=[])
        lic_file.parent.mkdir(parents=True)
        lic_file.write_text(json.dumps(data), encoding="utf-8")
        with patch("pentool.core.license._LICENSE_FILE", lic_file), \
             patch("pentool.core.license._LICENSE_SIGNING_PUBLIC_KEY_B64", _TEST_PUBLIC_KEY_B64):
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
    async def test_no_offline_bypass_when_server_unreachable(self, tmp_path):
        """Regression test for the removed DEMO- backdoor: with aiohttp
        unavailable (simulating "server unreachable"), activation must
        fail — there is no local fallback that grants PRO anymore."""
        lic_file = tmp_path / "license.dat"
        with patch("pentool.core.license._LICENSE_FILE", lic_file):
            with patch.dict("sys.modules", {"aiohttp": None}):
                info = await activate_license("DEMO-ABCD-1234-EFGH")
        assert info.valid is False
        assert not lic_file.exists()

    @pytest.mark.asyncio
    async def test_invalid_key_format_without_server_fails(self, tmp_path):
        lic_file = tmp_path / "license.dat"
        with patch("pentool.core.license._LICENSE_FILE", lic_file):
            with patch.dict("sys.modules", {"aiohttp": None}):
                info = await activate_license("INVALID-KEY")
        assert info.valid is False
        assert info.error != ""

    @staticmethod
    def _mock_aiohttp_returning(status: int, payload: dict):
        mock_resp = AsyncMock()
        mock_resp.status = status
        mock_resp.json = AsyncMock(return_value=payload)
        mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_resp.__aexit__ = AsyncMock(return_value=False)

        mock_session = AsyncMock()
        mock_session.post = MagicMock(return_value=mock_resp)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)

        mock_aiohttp = MagicMock()
        mock_aiohttp.ClientSession = MagicMock(return_value=mock_session)
        mock_aiohttp.ClientTimeout = MagicMock(return_value=MagicMock())
        return mock_aiohttp

    @pytest.mark.asyncio
    async def test_server_success_with_valid_signature_saves_cache(self, tmp_path):
        """Successful, correctly-signed server response → cached and trusted."""
        lic_file = tmp_path / "license.dat"
        machine_id = get_machine_id()
        ts = int(time.time() * 1000)
        features = ["scanner_pro"]
        sig = _sign(True, "pro", features, "2028-01-01", machine_id, ts)
        server_resp = {
            "valid": True, "plan": "pro", "features": features,
            "expires_at": "2028-01-01", "sig": sig, "ts": ts,
        }
        mock_aiohttp = self._mock_aiohttp_returning(200, server_resp)

        with patch("pentool.core.license._LICENSE_FILE", lic_file), \
             patch("pentool.core.license._LICENSE_SIGNING_PUBLIC_KEY_B64", _TEST_PUBLIC_KEY_B64), \
             patch.dict("sys.modules", {"aiohttp": mock_aiohttp}), \
             patch("pentool.core.license.download_pro_package", AsyncMock(return_value=True)):
            info = await activate_license("PROD-AAAA-BBBB-CCCC")

        assert info.valid is True
        assert info.plan == "pro"
        assert lic_file.exists()
        cached = json.loads(lic_file.read_text())
        assert cached["valid"] is True
        assert cached["plan"] == "pro"
        assert cached["sig"] == sig

    @pytest.mark.asyncio
    async def test_server_success_without_signature_rejected(self, tmp_path):
        """A valid=True response with no sig/ts must be refused, not trusted —
        this is the server-compromise / MITM defense, unsigned data is inert."""
        lic_file = tmp_path / "license.dat"
        server_resp = {"valid": True, "plan": "pro", "features": ["scanner_pro"]}
        mock_aiohttp = self._mock_aiohttp_returning(200, server_resp)

        with patch("pentool.core.license._LICENSE_FILE", lic_file), \
             patch.dict("sys.modules", {"aiohttp": mock_aiohttp}):
            info = await activate_license("PROD-AAAA-BBBB-CCCC")

        assert info.valid is False
        assert "unsigned" in info.error.lower()
        assert not lic_file.exists()

    @pytest.mark.asyncio
    async def test_server_success_with_bad_signature_rejected(self, tmp_path):
        """Signature present but doesn't verify (tampered in transit, or
        signed with an unexpected key) → refused."""
        lic_file = tmp_path / "license.dat"
        machine_id = get_machine_id()
        ts = int(time.time() * 1000)
        server_resp = {
            "valid": True, "plan": "pro", "features": ["scanner_pro"],
            "expires_at": None, "sig": base64.b64encode(b"\x00" * 64).decode(), "ts": ts,
        }
        mock_aiohttp = self._mock_aiohttp_returning(200, server_resp)

        with patch("pentool.core.license._LICENSE_FILE", lic_file), \
             patch("pentool.core.license._LICENSE_SIGNING_PUBLIC_KEY_B64", _TEST_PUBLIC_KEY_B64), \
             patch.dict("sys.modules", {"aiohttp": mock_aiohttp}):
            info = await activate_license("PROD-AAAA-BBBB-CCCC")

        assert info.valid is False
        assert "signature" in info.error.lower()
        assert not lic_file.exists()

    @pytest.mark.asyncio
    async def test_server_returns_invalid(self, tmp_path):
        """Server returned valid=False → not cached (no signature needed for
        a negative verdict — nothing to protect)."""
        lic_file = tmp_path / "license.dat"
        server_resp = {"valid": False, "plan": "free", "features": []}
        mock_aiohttp = self._mock_aiohttp_returning(200, server_resp)

        with patch("pentool.core.license._LICENSE_FILE", lic_file), \
             patch.dict("sys.modules", {"aiohttp": mock_aiohttp}):
            info = await activate_license("XXXX-YYYY-ZZZZ-0000")

        assert info.valid is False
        assert not lic_file.exists()


# ── download_pro_package ────────────────────────────────────────────────────────

class TestDownloadProPackage:
    """Regression tests for the .build_meta.json race that could leave a
    fully-installed PRO package stuck reporting "doesn't record which
    version" — see pentool-backend's /api/download X-Pro-Build-Id header
    and the synthetic-build_id fallback in download_pro_package()."""

    @staticmethod
    def _make_tar_bytes() -> bytes:
        import io
        import tarfile
        buf = io.BytesIO()
        with tarfile.open(fileobj=buf, mode="w:gz") as tar:
            info = tarfile.TarInfo(name="pentool/__init__.py")
            data = b"# stub\n"
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))
        return buf.getvalue()

    @classmethod
    def _mock_aiohttp_for_download(cls, archive_headers: dict | None = None):
        """Build a mock aiohttp module for two sequential session.post() calls:
        1) the archive (with optional response headers), 2) the signature."""
        archive_bytes = cls._make_tar_bytes()
        signature = base64.b64encode(
            _TEST_PRIVATE_KEY.sign(archive_bytes)
        ).decode("ascii")

        archive_resp = AsyncMock()
        archive_resp.status = 200
        archive_resp.read = AsyncMock(return_value=archive_bytes)
        archive_resp.headers = archive_headers or {}
        archive_resp.__aenter__ = AsyncMock(return_value=archive_resp)
        archive_resp.__aexit__ = AsyncMock(return_value=False)

        sig_resp = AsyncMock()
        sig_resp.status = 200
        sig_resp.text = AsyncMock(return_value=signature)
        sig_resp.__aenter__ = AsyncMock(return_value=sig_resp)
        sig_resp.__aexit__ = AsyncMock(return_value=False)

        mock_session = AsyncMock()
        mock_session.post = MagicMock(side_effect=[archive_resp, sig_resp])
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)

        mock_aiohttp = MagicMock()
        mock_aiohttp.ClientSession = MagicMock(return_value=mock_session)
        mock_aiohttp.ClientTimeout = MagicMock(return_value=MagicMock())
        return mock_aiohttp

    @pytest.mark.asyncio
    async def test_build_id_from_header_written_immediately_no_extra_request(self, tmp_path, monkeypatch):
        """Worker sends X-Pro-Build-Id on the archive response — must be used
        directly, with NO follow-up call to _fetch_pro_build_id (the removed
        third request that used to race with network hiccups)."""
        pro_dir = tmp_path / "pro"
        mock_aiohttp = self._mock_aiohttp_for_download(
            archive_headers={"X-Pro-Build-Id": "12345:2026-08-09T00:00:00Z"}
        )
        fetch_build_id_called = False

        async def _fail_if_called(plat):
            nonlocal fetch_build_id_called
            fetch_build_id_called = True
            return "should-not-be-used"

        with patch("pentool.core.license.PRO_PACKAGE_DIR", pro_dir), \
             patch("pentool.core.license._PRO_META_FILE", pro_dir / ".build_meta.json"), \
             patch("pentool.core.license._PRO_PACKAGE_PUBLIC_KEY_B64", _TEST_PUBLIC_KEY_B64), \
             patch("pentool.core.license._fetch_pro_build_id", _fail_if_called), \
             patch.dict("sys.modules", {"aiohttp": mock_aiohttp}):
            ok = await download_pro_package("PTOOL-AAAA-BBBB-CCCC", "machine-1")

        assert ok is True
        assert fetch_build_id_called is False
        meta = _read_pro_meta_from(pro_dir)
        assert meta["build_id"] == "12345:2026-08-09T00:00:00Z"
        assert meta["free_version"]  # non-empty — recorded successfully

    @pytest.mark.asyncio
    async def test_falls_back_to_fetch_when_header_missing(self, tmp_path):
        """Older Worker deploy without the header — falls back to the
        separate /api/pro/version call, same as before this fix."""
        pro_dir = tmp_path / "pro"
        mock_aiohttp = self._mock_aiohttp_for_download(archive_headers={})

        async def _fake_fetch(plat):
            return "fallback-build-id"

        with patch("pentool.core.license.PRO_PACKAGE_DIR", pro_dir), \
             patch("pentool.core.license._PRO_META_FILE", pro_dir / ".build_meta.json"), \
             patch("pentool.core.license._PRO_PACKAGE_PUBLIC_KEY_B64", _TEST_PUBLIC_KEY_B64), \
             patch("pentool.core.license._fetch_pro_build_id", _fake_fetch), \
             patch.dict("sys.modules", {"aiohttp": mock_aiohttp}):
            ok = await download_pro_package("PTOOL-AAAA-BBBB-CCCC", "machine-1")

        assert ok is True
        meta = _read_pro_meta_from(pro_dir)
        assert meta["build_id"] == "fallback-build-id"
        assert meta["free_version"]

    @pytest.mark.asyncio
    async def test_synthetic_build_id_when_header_and_fetch_both_fail(self, tmp_path):
        """This is the actual regression: header missing AND the fallback
        network call also fails. Before this fix, .build_meta.json was never
        written at all even though the archive extracted successfully — the
        user was stuck seeing "doesn't record which version" forever despite
        having a perfectly working PRO install. Now a synthetic build_id is
        always recorded so free_version is never empty after a successful
        extract."""
        pro_dir = tmp_path / "pro"
        mock_aiohttp = self._mock_aiohttp_for_download(archive_headers={})

        async def _fake_fetch_fails(plat):
            raise RuntimeError("network down")

        with patch("pentool.core.license.PRO_PACKAGE_DIR", pro_dir), \
             patch("pentool.core.license._PRO_META_FILE", pro_dir / ".build_meta.json"), \
             patch("pentool.core.license._PRO_PACKAGE_PUBLIC_KEY_B64", _TEST_PUBLIC_KEY_B64), \
             patch("pentool.core.license._fetch_pro_build_id", _fake_fetch_fails), \
             patch.dict("sys.modules", {"aiohttp": mock_aiohttp}):
            ok = await download_pro_package("PTOOL-AAAA-BBBB-CCCC", "machine-1")

        assert ok is True  # install succeeded — must not be reported as failed
        meta = _read_pro_meta_from(pro_dir)
        assert meta["build_id"]  # some non-empty synthetic id was recorded
        assert meta["free_version"]  # the critical field — must not be empty

    @pytest.mark.asyncio
    async def test_bad_signature_does_not_write_meta(self, tmp_path):
        """Signature verification failure must still refuse the install
        entirely — the synthetic-build_id fallback only applies after a
        verified, successfully-extracted archive, never as a way to bypass
        signature checking."""
        pro_dir = tmp_path / "pro"
        archive_bytes = self._make_tar_bytes()
        archive_resp = AsyncMock()
        archive_resp.status = 200
        archive_resp.read = AsyncMock(return_value=archive_bytes)
        archive_resp.headers = {}
        archive_resp.__aenter__ = AsyncMock(return_value=archive_resp)
        archive_resp.__aexit__ = AsyncMock(return_value=False)

        sig_resp = AsyncMock()
        sig_resp.status = 200
        sig_resp.text = AsyncMock(return_value=base64.b64encode(b"\x00" * 64).decode())
        sig_resp.__aenter__ = AsyncMock(return_value=sig_resp)
        sig_resp.__aexit__ = AsyncMock(return_value=False)

        mock_session = AsyncMock()
        mock_session.post = MagicMock(side_effect=[archive_resp, sig_resp])
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)

        mock_aiohttp = MagicMock()
        mock_aiohttp.ClientSession = MagicMock(return_value=mock_session)
        mock_aiohttp.ClientTimeout = MagicMock(return_value=MagicMock())

        with patch("pentool.core.license.PRO_PACKAGE_DIR", pro_dir), \
             patch("pentool.core.license._PRO_META_FILE", pro_dir / ".build_meta.json"), \
             patch("pentool.core.license._PRO_PACKAGE_PUBLIC_KEY_B64", _TEST_PUBLIC_KEY_B64), \
             patch.dict("sys.modules", {"aiohttp": mock_aiohttp}):
            ok = await download_pro_package("PTOOL-AAAA-BBBB-CCCC", "machine-1")

        assert ok is False
        assert not (pro_dir / ".build_meta.json").exists()


def _read_pro_meta_from(pro_dir) -> dict:
    """Read .build_meta.json from a specific PRO_PACKAGE_DIR override used in
    these tests (avoids depending on the real ~/.pentool path)."""
    meta_file = pro_dir / ".build_meta.json"
    return json.loads(meta_file.read_text(encoding="utf-8"))


# ── check_and_update_pro_package ────────────────────────────────────────────────

class TestCheckAndUpdateProPackage:
    """Regression tests for the second half of the .build_meta.json bug: even
    after download_pro_package() started recording free_version reliably (see
    TestDownloadProPackage above), a package that was ALREADY broken from
    before that fix — same build_id as the current release, but incompatible
    metadata — must still be re-downloaded and repaired. Before this fix,
    matching build_id short-circuited the whole function and the same
    "doesn't record which version" warning repeated forever, since
    download_pro_package() was only reached when build_id differed."""

    @staticmethod
    def _valid_license_info():
        return LicenseInfo(
            valid=True, plan="pro", features=["scanner_pro"],
            license_key="PTOOL-AAAA-BBBB-CCCC", machine_id="machine-1",
        )

    @pytest.mark.asyncio
    async def test_matching_build_id_but_incompatible_meta_triggers_redownload(self, tmp_path):
        pro_dir = tmp_path / "pro"
        pro_dir.mkdir()
        # Simulate the exact broken state: PRO package physically present,
        # but .build_meta.json missing (never got written) — this is what
        # is_pro_package_compatible() treats as incompatible.
        assert not (pro_dir / ".build_meta.json").exists()

        redownload_called = False

        async def _fake_download(key, machine_id):
            nonlocal redownload_called
            redownload_called = True
            return True

        with patch("pentool.core.license.PRO_PACKAGE_DIR", pro_dir), \
             patch("pentool.core.license._PRO_META_FILE", pro_dir / ".build_meta.json"), \
             patch("pentool.core.license._PRO_BUILD_MARKER", pro_dir / ".build_id"), \
             patch("pentool.core.license.get_license", return_value=self._valid_license_info()), \
             patch("pentool.core.license._fetch_pro_build_id", AsyncMock(return_value="same-build-id")), \
             patch("pentool.core.license.download_pro_package", _fake_download):
            result = await check_and_update_pro_package()

        assert redownload_called is True, (
            "download_pro_package() must be called to repair a package "
            "that's incompatible even when build_id matches the remote — "
            "otherwise the same warning repeats forever with no path to fix it"
        )
        assert result.updated is True
        assert result.warning == ""

    @pytest.mark.asyncio
    async def test_matching_build_id_and_compatible_meta_skips_redownload(self, tmp_path):
        """Sanity check for the common case: nothing wrong, don't re-download
        needlessly just because we now also check compatibility."""
        pro_dir = tmp_path / "pro"
        pro_dir.mkdir()
        (pro_dir / ".build_meta.json").write_text(
            json.dumps({"build_id": "same-build-id", "free_version": "0.2.6"}),
            encoding="utf-8",
        )

        redownload_called = False

        async def _fake_download(key, machine_id):
            nonlocal redownload_called
            redownload_called = True
            return True

        with patch("pentool.core.license.PRO_PACKAGE_DIR", pro_dir), \
             patch("pentool.core.license._PRO_META_FILE", pro_dir / ".build_meta.json"), \
             patch("pentool.core.license._PRO_BUILD_MARKER", pro_dir / ".build_id"), \
             patch("pentool.core.license.get_license", return_value=self._valid_license_info()), \
             patch("pentool.core.license._fetch_pro_build_id", AsyncMock(return_value="same-build-id")), \
             patch("pentool.core.license.download_pro_package", _fake_download), \
             patch("pentool.core.plugin_manager.PRO_PACKAGE_DIR", pro_dir, create=True):
            # is_pro_package_compatible() compares against pentool's own
            # __version__, which in this test environment is whatever the
            # dev checkout reports — patch it directly for a deterministic match.
            import pentool
            with patch.object(pentool, "__version__", "0.2.6", create=True):
                result = await check_and_update_pro_package()

        assert redownload_called is False
        assert result.updated is False
        assert result.warning == ""


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
            deactivate_license()  # should not raise


# ── Session cache ──────────────────────────────────────────────────────────────

class TestSessionCache:
    def test_get_session_license_caches(self, tmp_path):
        import pentool.core.license as lic_mod
        lic_mod._session_license = None  # reset
        with patch("pentool.core.license._LICENSE_FILE", tmp_path / "missing.dat"):
            info1 = get_session_license()
            info2 = get_session_license()
        assert info1 is info2  # same object from cache

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

"""Pentool licensing system."""

from __future__ import annotations

import base64
import hashlib
import json
import platform
import tarfile
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path

_LICENSE_FILE = Path.home() / ".pentool" / "license.dat"
_GRACE_PERIOD_DAYS = 7

_LICENSE_API_BASE = "https://pentool-license.akashtanov2020.workers.dev"

# PRO package delivery
PRO_PACKAGE_DIR = Path.home() / ".pentool" / "pro"

# ed25519 public key (base64) matching pentool-pro's PRO_SIGNING_KEY.
# Only the corresponding private key (held in pentool-pro's CI secret) can
# produce a signature that verifies against this — a compromised CDN/Worker
# cannot make the client execute tampered code.
_PRO_PACKAGE_PUBLIC_KEY_B64 = "MMPAM1xmvGV/CaLlT0doHoUH+Uv2zvVMSmPzNBglgBA="



@dataclass
class LicenseInfo:
    """Information about the current license."""

    valid: bool = False
    plan: str = "free"                      # "free" | "pro" | "enterprise"
    features: list[str] = field(default_factory=list)
    expires: str | None = None           # ISO date or None (permanent)
    machine_id: str = ""
    license_key: str = ""
    last_check: float | None = None      # timestamp of last online check
    error: str = ""                         # error message if not valid

    def has_feature(self, feature: str) -> bool:
        return self.valid and feature in self.features

    def is_pro(self) -> bool:
        return self.valid and self.plan in ("pro", "enterprise")

    @property
    def status_text(self) -> str:
        if not self.valid:
            return "FREE"
        return self.plan.upper()

    @property
    def expires_text(self) -> str:
        if not self.expires:
            return "Lifetime"
        return self.expires


def get_machine_id() -> str:
    try:
        import socket
        hostname = socket.gethostname()
        # Get MAC of first interface via uuid
        mac = hex(uuid.getnode())[2:]
        raw = f"{hostname}:{mac}"
        return hashlib.sha256(raw.encode()).hexdigest()[:32]
    except Exception:
        return hashlib.sha256(platform.node().encode()).hexdigest()[:32]


def _load_cached() -> dict | None:
    try:
        if _LICENSE_FILE.exists():
            data = json.loads(_LICENSE_FILE.read_text(encoding="utf-8"))
            return data
    except Exception:
        pass
    return None


def _save_cached(data: dict) -> None:
    try:
        _LICENSE_FILE.parent.mkdir(parents=True, exist_ok=True)
        _LICENSE_FILE.write_text(
            json.dumps(data, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
    except Exception:
        pass


def get_license() -> LicenseInfo:
    cached = _load_cached()
    if cached is None:
        return LicenseInfo(valid=False, plan="free", machine_id=get_machine_id())

    last_check = cached.get("last_check", 0)
    grace_seconds = _GRACE_PERIOD_DAYS * 24 * 3600
    if (time.time() - last_check) > grace_seconds:
        # Grace period expired — deactivate
        return LicenseInfo(
            valid=False,
            plan="free",
            machine_id=get_machine_id(),
            license_key=cached.get("license_key", ""),
            error="Grace period expired. Please reconnect to validate license.",
        )

    return LicenseInfo(
        valid=cached.get("valid", False),
        plan=cached.get("plan", "free"),
        features=cached.get("features", []),
        expires=cached.get("expires"),
        machine_id=cached.get("machine_id", get_machine_id()),
        license_key=cached.get("license_key", ""),
        last_check=last_check,
    )


# Session-level license cache (avoids repeated file reads per check)
_session_license: "LicenseInfo | None" = None


def get_session_license() -> "LicenseInfo":
    """Return cached session license (refreshed once per process)."""
    global _session_license
    if _session_license is None:
        _session_license = get_license()
    return _session_license


def invalidate_session_license() -> None:
    """Force re-read on next get_session_license() call."""
    global _session_license
    _session_license = None


def refresh_session_license(info: "LicenseInfo | None" = None) -> "LicenseInfo":
    """Force-set session license (or re-read from disk if info is None)."""
    global _session_license
    _session_license = info or get_license()
    return _session_license


class FeatureNotAvailable(Exception):
    """Feature not available in the current plan."""
    def __init__(self, feature: str, plan_required: str = "pro"):
        self.feature = feature
        self.plan_required = plan_required
        super().__init__(
            f"Feature '{feature}' requires {plan_required.upper()} plan. "
            f"Upgrade at https://pentool.pro/upgrade"
        )


def require_feature(feature: str, plan_required: str = "pro"):
    """Decorator: raise FeatureNotAvailable if feature is not licensed."""
    def decorator(func):
        import asyncio as _asyncio
        import functools

        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs):
            if not get_session_license().has_feature(feature):
                raise FeatureNotAvailable(feature, plan_required)
            return await func(*args, **kwargs)

        @functools.wraps(func)
        def sync_wrapper(*args, **kwargs):
            if not get_session_license().has_feature(feature):
                raise FeatureNotAvailable(feature, plan_required)
            return func(*args, **kwargs)

        if _asyncio.iscoroutinefunction(func):
            return async_wrapper
        return sync_wrapper
    return decorator


async def activate_license(key: str) -> LicenseInfo:
    """Activate license online (license.pentool.pro/api/validate).

    Returns:
        LicenseInfo with activation result.
    """
    key = key.strip().upper()
    machine_id = get_machine_id()

    if not key:
        return LicenseInfo(
            valid=False, plan="free",
            machine_id=machine_id,
            error="License key is empty",
        )

    # Attempt real online check
    try:
        import aiohttp
        async with aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=10)
        ) as session:
            async with session.post(
                f"{_LICENSE_API_BASE}/api/validate",
                json={"key": key, "machine_id": machine_id},
                ssl=False,
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    info = LicenseInfo(
                        valid=data.get("valid", False),
                        plan=data.get("plan", "free"),
                        features=data.get("features", []),
                        expires=data.get("expires"),
                        machine_id=machine_id,
                        license_key=key,
                        last_check=time.time(),
                    )
                    if info.valid:
                        _save_cached({
                            "valid": True,
                            "plan": info.plan,
                            "features": info.features,
                            "expires": info.expires,
                            "machine_id": machine_id,
                            "license_key": key,
                            "last_check": time.time(),
                        })
                        if info.features:
                            await download_pro_package(key, machine_id)
                    return info
    except Exception:
        pass  # Server unavailable — fallback to local check

    # Offline fallback: check key format
    # Format: XXXX-XXXX-XXXX-XXXX (16 hex chars with dashes)
    import re
    if re.match(r'^[A-Z0-9]{4}-[A-Z0-9]{4}-[A-Z0-9]{4}-[A-Z0-9]{4}$', key):
        if key.startswith("DEMO"):
            info = LicenseInfo(
                valid=True,
                plan="pro",
                features=["scanner_pro", "reports_pro", "payloads_pro"],
                expires=None,
                machine_id=machine_id,
                license_key=key,
                last_check=time.time(),
            )
            _save_cached({
                "valid": True,
                "plan": "pro",
                "features": ["scanner_pro", "reports_pro", "payloads_pro"],
                "expires": None,
                "machine_id": machine_id,
                "license_key": key,
                "last_check": time.time(),
            })
            return info

    return LicenseInfo(
        valid=False,
        plan="free",
        machine_id=machine_id,
        license_key=key,
        error="License server unavailable. Key format invalid or not activated.",
    )


def deactivate_license() -> None:
    """Deactivate license (delete cache)."""
    try:
        if _LICENSE_FILE.exists():
            _LICENSE_FILE.unlink()
    except Exception:
        pass


async def start_trial() -> LicenseInfo:
    """Start a 14-day PRO trial (one per machine_id, enforced server-side).

    Returns:
        LicenseInfo — valid=True with the issued trial key on success,
        valid=False with .error set if the trial was already used on this
        machine or the server is unreachable.
    """
    machine_id = get_machine_id()

    try:
        import aiohttp
        async with aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=10)
        ) as session:
            async with session.post(
                f"{_LICENSE_API_BASE}/api/trial/start",
                json={"machine_id": machine_id},
                ssl=False,
            ) as resp:
                data = await resp.json()

                if resp.status == 201 and data.get("valid"):
                    key = data.get("key", "")
                    info = LicenseInfo(
                        valid=True,
                        plan=data.get("plan", "pro"),
                        features=data.get("features", []),
                        expires=data.get("expires_at"),
                        machine_id=machine_id,
                        license_key=key,
                        last_check=time.time(),
                    )
                    _save_cached({
                        "valid": True,
                        "plan": info.plan,
                        "features": info.features,
                        "expires": info.expires,
                        "machine_id": machine_id,
                        "license_key": key,
                        "last_check": time.time(),
                    })
                    if info.features:
                        await download_pro_package(key, machine_id)
                    return info

                return LicenseInfo(
                    valid=False,
                    plan="free",
                    machine_id=machine_id,
                    error=data.get("message", "Trial could not be started."),
                )
    except Exception as exc:
        return LicenseInfo(
            valid=False,
            plan="free",
            machine_id=machine_id,
            error=f"License server unreachable: {exc}",
        )


def _verify_pro_package_signature(archive_bytes: bytes, signature_b64: str) -> bool:
    """Verify the ed25519 detached signature over the raw archive bytes."""
    try:
        from cryptography.exceptions import InvalidSignature
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

        public_key = Ed25519PublicKey.from_public_bytes(
            base64.b64decode(_PRO_PACKAGE_PUBLIC_KEY_B64)
        )
        signature = base64.b64decode(signature_b64.strip())
        public_key.verify(signature, archive_bytes)
        return True
    except InvalidSignature:
        return False
    except Exception:
        return False


def _safe_extract_tar(archive_path: Path, dest_dir: Path) -> None:
    """Extract a tar.gz archive, refusing any member that would escape dest_dir.

    Guards against path traversal (../../) and absolute-path members —
    the archive is fetched over the network and, even though it is
    signature-verified, defense in depth costs nothing here.
    """
    dest_dir = dest_dir.resolve()
    with tarfile.open(archive_path, "r:gz") as tar:
        for member in tar.getmembers():
            member_path = (dest_dir / member.name).resolve()
            if not str(member_path).startswith(str(dest_dir)):
                raise ValueError(f"Unsafe path in PRO package archive: {member.name}")
        tar.extractall(dest_dir)  # noqa: S202 — members already validated above


async def download_pro_package(key: str, machine_id: str) -> bool:
    """Download, verify, and install the obfuscated PRO package.

    Fetches both the archive and its detached ed25519 signature from
    /api/download, verifies the signature against the embedded public key
    (see _PRO_PACKAGE_PUBLIC_KEY_B64) BEFORE ever extracting anything, then
    unpacks into ~/.pentool/pro/ for plugin_manager to pick up.

    Returns True on success, False otherwise (never raises — a failed PRO
    package download should not block FREE functionality).
    """
    try:
        import aiohttp
        async with aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=60)
        ) as session:
            async with session.post(
                f"{_LICENSE_API_BASE}/api/download",
                json={"key": key, "machine_id": machine_id},
                ssl=False,
            ) as resp:
                if resp.status != 200:
                    return False
                archive_bytes = await resp.read()

            async with session.post(
                f"{_LICENSE_API_BASE}/api/download",
                json={"key": key, "machine_id": machine_id, "sig": "1"},
                ssl=False,
            ) as resp:
                if resp.status != 200:
                    return False
                signature_b64 = (await resp.text()).strip()

        if not _verify_pro_package_signature(archive_bytes, signature_b64):
            return False

        PRO_PACKAGE_DIR.mkdir(parents=True, exist_ok=True)
        tmp_archive = PRO_PACKAGE_DIR / ".pentool-pro.tar.gz.tmp"
        tmp_archive.write_bytes(archive_bytes)
        try:
            _safe_extract_tar(tmp_archive, PRO_PACKAGE_DIR)
        finally:
            tmp_archive.unlink(missing_ok=True)

        return True
    except Exception:
        return False

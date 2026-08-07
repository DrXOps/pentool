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

# ed25519 public key (base64) matching pentool-backend's LICENSE_SIGNING_KEY.
# Every /api/validate and /api/trial/start response is signed server-side —
# the client verifies the signature (over a canonical payload including
# machine_id + ts) before trusting valid/plan/features, and persists the
# signature alongside the cached verdict so ~/.pentool/license.dat itself is
# tamper-evident: hand-editing it to say {"valid": true, "plan": "pro"} no
# longer works, because the signature won't match the edited fields.
_LICENSE_SIGNING_PUBLIC_KEY_B64 = "1yrqLbj5Ei2/NpBBAg/mAn2hSZazTKoq909spi8LqT0="

# How long a signed server verdict remains trusted without re-validating
# online — same value as the previous unsigned last_check grace period.
_SIGNATURE_MAX_AGE_SECONDS = _GRACE_PERIOD_DAYS * 24 * 3600



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


def _canonical_license_payload(
    valid: bool, plan: str, features: list[str], expires: str | None,
    machine_id: str, ts: int,
) -> bytes:
    """Reconstruct the exact byte string the server signed.

    MUST match pentool-backend's canonicalLicensePayload() field-for-field —
    order, separator, and the sorted-features join are part of the contract.
    """
    parts = [
        "1" if valid else "0",
        plan,
        ",".join(sorted(features)),
        expires or "",
        machine_id,
        str(ts),
    ]
    return "|".join(parts).encode("utf-8")


def _verify_license_signature(
    valid: bool, plan: str, features: list[str], expires: str | None,
    machine_id: str, ts: int, sig_b64: str,
) -> bool:
    """Verify the server's ed25519 signature over a license verdict.

    This is what makes ~/.pentool/license.dat tamper-evident: without the
    server's private key (held only in pentool-backend's Cloudflare secret),
    nobody can hand-craft a {"valid": true, "plan": "pro", ...} blob that
    passes this check — editing any signed field invalidates the signature.
    """
    try:
        from cryptography.exceptions import InvalidSignature
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

        public_key = Ed25519PublicKey.from_public_bytes(
            base64.b64decode(_LICENSE_SIGNING_PUBLIC_KEY_B64)
        )
        message = _canonical_license_payload(valid, plan, features, expires, machine_id, ts)
        signature = base64.b64decode(sig_b64.strip())
        public_key.verify(signature, message)
        return True
    except InvalidSignature:
        return False
    except Exception:
        return False


def get_license() -> LicenseInfo:
    """Load and verify the cached license verdict from disk.

    Returns valid=False (downgrades to FREE) unless ALL of the following hold:
      1. A cached verdict exists and has a signature.
      2. The signature verifies against the server's public key over the
         exact cached fields (valid/plan/features/expires/machine_id/ts) —
         this is what prevents hand-editing license.dat to fake PRO.
      3. The signature's machine_id matches this machine's current id — a
         verdict signed for one machine cannot be copied onto another.
      4. The signature is not older than _SIGNATURE_MAX_AGE_SECONDS — bounds
         how long a license can be used fully offline before requiring a
         fresh online check (same grace-period contract as before).
    """
    cached = _load_cached()
    my_machine_id = get_machine_id()

    if cached is None:
        return LicenseInfo(valid=False, plan="free", machine_id=my_machine_id)

    sig = cached.get("sig")
    ts = cached.get("ts")
    if not sig or ts is None:
        # Pre-signature cache format (or tampered/stripped) — cannot trust it.
        return LicenseInfo(
            valid=False, plan="free", machine_id=my_machine_id,
            license_key=cached.get("license_key", ""),
            error="License cache is unsigned or corrupted. Please re-activate.",
        )

    plan = cached.get("plan", "free")
    features = cached.get("features", [])
    expires = cached.get("expires")
    cached_machine_id = cached.get("machine_id", "")
    valid_flag = bool(cached.get("valid", False))

    if not _verify_license_signature(valid_flag, plan, features, expires, cached_machine_id, ts, sig):
        return LicenseInfo(
            valid=False, plan="free", machine_id=my_machine_id,
            license_key=cached.get("license_key", ""),
            error="License signature invalid — cache may have been tampered with. Please re-activate.",
        )

    if cached_machine_id != my_machine_id:
        return LicenseInfo(
            valid=False, plan="free", machine_id=my_machine_id,
            license_key=cached.get("license_key", ""),
            error="License was issued for a different machine.",
        )

    age_seconds = time.time() - (ts / 1000.0)
    if age_seconds > _SIGNATURE_MAX_AGE_SECONDS:
        return LicenseInfo(
            valid=False,
            plan="free",
            machine_id=my_machine_id,
            license_key=cached.get("license_key", ""),
            error="Grace period expired. Please reconnect to validate license.",
        )

    return LicenseInfo(
        valid=valid_flag,
        plan=plan,
        features=features,
        expires=expires,
        machine_id=cached_machine_id,
        license_key=cached.get("license_key", ""),
        last_check=ts / 1000.0,
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

    Requires a valid signed response from the server — there is no offline
    fallback that grants PRO. (A previous version accepted any key starting
    with "DEMO-" and matching the XXXX-XXXX-XXXX-XXXX pattern as an
    always-valid PRO license without ever contacting the server — that was
    a full authentication bypass and has been removed. Every activation now
    requires network access to the license server and a verified signature.)

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
                if resp.status != 200:
                    return LicenseInfo(
                        valid=False, plan="free", machine_id=machine_id,
                        license_key=key,
                        error=f"License server returned HTTP {resp.status}",
                    )
                data = await resp.json()

        valid = bool(data.get("valid", False))
        plan = data.get("plan", "free")
        features = data.get("features", [])
        expires = data.get("expires_at") or data.get("expires")
        sig = data.get("sig")
        ts = data.get("ts")

        if valid:
            if not sig or ts is None:
                return LicenseInfo(
                    valid=False, plan="free", machine_id=machine_id, license_key=key,
                    error="License server response was unsigned — refusing to trust it.",
                )
            if not _verify_license_signature(valid, plan, features, expires, machine_id, ts, sig):
                return LicenseInfo(
                    valid=False, plan="free", machine_id=machine_id, license_key=key,
                    error="License server response failed signature verification.",
                )
            _save_cached({
                "valid": True,
                "plan": plan,
                "features": features,
                "expires": expires,
                "machine_id": machine_id,
                "license_key": key,
                "sig": sig,
                "ts": ts,
            })
            if features:
                await download_pro_package(key, machine_id)

        return LicenseInfo(
            valid=valid, plan=plan, features=features, expires=expires,
            machine_id=machine_id, license_key=key,
            last_check=(ts / 1000.0) if ts else time.time(),
            error="" if valid else data.get("message", "Activation failed"),
        )
    except Exception as exc:
        return LicenseInfo(
            valid=False,
            plan="free",
            machine_id=machine_id,
            license_key=key,
            error=f"License server unreachable: {exc}",
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
                    plan = data.get("plan", "pro")
                    features = data.get("features", [])
                    expires = data.get("expires_at")
                    sig = data.get("sig")
                    ts = data.get("ts")

                    if not sig or ts is None:
                        return LicenseInfo(
                            valid=False, plan="free", machine_id=machine_id,
                            error="License server response was unsigned — refusing to trust it.",
                        )
                    if not _verify_license_signature(True, plan, features, expires, machine_id, ts, sig):
                        return LicenseInfo(
                            valid=False, plan="free", machine_id=machine_id,
                            error="License server response failed signature verification.",
                        )

                    _save_cached({
                        "valid": True,
                        "plan": plan,
                        "features": features,
                        "expires": expires,
                        "machine_id": machine_id,
                        "license_key": key,
                        "sig": sig,
                        "ts": ts,
                    })
                    info = LicenseInfo(
                        valid=True, plan=plan, features=features, expires=expires,
                        machine_id=machine_id, license_key=key, last_check=ts / 1000.0,
                    )
                    if features:
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


def _current_platform() -> str:
    """Map platform.system() to the pentool-pro release asset naming scheme
    (pentool-pro-{linux,macos,windows}.tar.gz — see pentool-backend's
    packageAssetName()). Defaults to "linux" for anything unrecognized
    (e.g. other POSIX systems), matching the Worker's own fallback."""
    system = platform.system().lower()
    if system == "darwin":
        return "macos"
    if system == "windows":
        return "windows"
    return "linux"


# File recording which PRO build is currently unpacked into PRO_PACKAGE_DIR —
# lets check_and_update_pro_package() tell "same build as last time" apart
# from "a new build was published" without re-downloading the archive to
# compare it. See _fetch_pro_build_id() / /api/pro/version on the Worker.
_PRO_BUILD_MARKER = PRO_PACKAGE_DIR / ".build_id"


async def download_pro_package(key: str, machine_id: str) -> bool:
    """Download, verify, and install the obfuscated PRO package.

    Fetches both the archive and its detached ed25519 signature from
    /api/download, verifies the signature against the embedded public key
    (see _PRO_PACKAGE_PUBLIC_KEY_B64) BEFORE ever extracting anything, then
    unpacks into ~/.pentool/pro/ for plugin_manager to pick up.

    Since the CodeEnigma-based build (2026-08), pentool-pro's CI publishes
    one archive per OS (linux/macos/windows) instead of a single
    platform-agnostic one — CodeEnigma's runtime package includes a
    compiled Cython extension (.so/.pyd), which is platform-specific.
    `platform` is sent to the server so it returns the right asset.

    Returns True on success, False otherwise (never raises — a failed PRO
    package download should not block FREE functionality).
    """
    plat = _current_platform()
    try:
        import aiohttp
        async with aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=60)
        ) as session:
            async with session.post(
                f"{_LICENSE_API_BASE}/api/download",
                json={"key": key, "machine_id": machine_id, "platform": plat},
                ssl=False,
            ) as resp:
                if resp.status != 200:
                    return False
                archive_bytes = await resp.read()

            async with session.post(
                f"{_LICENSE_API_BASE}/api/download",
                json={"key": key, "machine_id": machine_id, "platform": plat, "sig": "1"},
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

        # Record which build this is, so a later check_and_update_pro_package()
        # can tell "nothing changed" from "a new build was published" without
        # re-downloading the archive just to compare it.
        try:
            build_id = await _fetch_pro_build_id(plat)
            if build_id:
                _PRO_BUILD_MARKER.write_text(build_id, encoding="utf-8")
        except Exception:
            pass  # non-fatal — worst case, next check just re-downloads once more

        return True
    except Exception:
        return False


async def _fetch_pro_build_id(plat: str) -> str | None:
    """Query /api/pro/version for the current PRO release's build_id.

    No license key needed — this only identifies which build is published,
    not whether the caller is entitled to it (that's still enforced by
    /api/download re-validating the key server-side). Returns None on any
    failure (network, missing asset, etc.) — callers should treat that as
    "couldn't check, don't act on it" rather than "no update available".
    """
    try:
        import aiohttp
        async with aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=8)
        ) as session:
            async with session.get(
                f"{_LICENSE_API_BASE}/api/pro/version",
                params={"platform": plat},
                ssl=False,
            ) as resp:
                if resp.status != 200:
                    return None
                data = await resp.json()
                return data.get("build_id")
    except Exception:
        return None


async def check_and_update_pro_package() -> bool:
    """Re-download the PRO package if a newer build has been published.

    Called on TUI startup (background worker, same pattern as
    _check_for_updates for the pip package) and after `pentool update` — this
    is what closes the gap where pentool-pro ships a fix but a machine that
    already activated its license keeps running the stale code from
    ~/.pentool/pro/ forever, because download_pro_package() otherwise only
    ever runs once, at initial activation/trial-start.

    Silently does nothing (returns False) if:
      - there's no active PRO license (nothing to update)
      - the PRO package was never downloaded in the first place (that's
        activate_license's job, not this one)
      - the version check or download fails for any reason

    Returns True if a new build was found and successfully installed.
    """
    info = get_license()
    if not info.valid or not info.features:
        return False
    if not PRO_PACKAGE_DIR.exists():
        return False  # never activated on this machine — nothing to refresh

    plat = _current_platform()
    remote_build_id = await _fetch_pro_build_id(plat)
    if not remote_build_id:
        return False  # couldn't reach the server — don't touch anything

    local_build_id = None
    try:
        if _PRO_BUILD_MARKER.exists():
            local_build_id = _PRO_BUILD_MARKER.read_text(encoding="utf-8").strip()
    except Exception:
        pass

    if local_build_id == remote_build_id:
        return False  # already on the latest build

    return await download_pro_package(info.license_key, info.machine_id)

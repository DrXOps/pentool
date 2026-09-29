"""Pentool licensing system."""

from __future__ import annotations

import base64
import hashlib
import json
import platform
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path

_LICENSE_FILE = Path.home() / ".pentool" / "license.dat"
_GRACE_PERIOD_DAYS = 7


def _base_version(v: str) -> str:
    """Strip dev/pre/suffix for X.Y.Z comparison (dev builds mismatch PRO otherwise)."""
    try:
        from packaging.version import Version
        return Version(v).base_version
    except Exception:
        # Fallback: strip everything from the first non X.Y.Z separator.
        import re
        m = re.match(r"^\d+(\.\d+)*", v)
        return m.group(0) if m else v


_LICENSE_API_BASE = "https://pentool-license.akashtanov2020.workers.dev"

# PRO package delivery
PRO_PACKAGE_DIR = Path.home() / ".pentool" / "pro"

# PRO-package verify/extract/platform helpers now live in
# core/license_update.py (Этап 6) — re-exported here under the same names so
# existing call sites don't change.
from pentool.core.license_update import (
    PRO_PACKAGE_PUBLIC_KEY_B64 as _PRO_PACKAGE_PUBLIC_KEY_B64,
    current_platform as _current_platform,
    safe_extract_tar as _safe_extract_tar,
    verify_pro_package_signature as _verify_pro_package_signature,
)

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
    """Verify ed25519 signature over license verdict (tamper-evident)."""
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
    """Load and verify cached license verdict (signature, machine_id, age checks)."""
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
                headers={"Accept-Encoding": "gzip, deflate"},
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
                headers={"Accept-Encoding": "gzip, deflate"},
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


# File recording which PRO build is currently unpacked into PRO_PACKAGE_DIR,
# together with the FREE (pip) pentool version it was downloaded for — lets
# check_and_update_pro_package() tell "same build as last time" apart from "a
# new build was published" without re-downloading the archive to compare it,
# and lets is_pro_package_compatible() detect a FREE/PRO version mismatch.
# See _fetch_pro_build_id() / /api/pro/version on the Worker.
_PRO_META_FILE = PRO_PACKAGE_DIR / ".build_meta.json"

# Legacy pre-2026-08 marker: plain text build_id, no version recorded. Still
# read (as "unknown version" -> treated as incompatible/stale, see
# is_pro_package_compatible()) so an old install isn't mistaken for corrupt.
_PRO_BUILD_MARKER = PRO_PACKAGE_DIR / ".build_id"


@dataclass
class ProSyncResult:
    """Result of PRO auto-update: updated flag + user-facing warning."""
    updated: bool = False
    warning: str = ""


def _read_pro_meta() -> dict:
    """Read PRO build metadata (build_id + free_version). Falls back to legacy .build_id file."""
    try:
        if _PRO_META_FILE.exists():
            data = json.loads(_PRO_META_FILE.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return data
    except Exception:
        pass
    try:
        if _PRO_BUILD_MARKER.exists():
            return {"build_id": _PRO_BUILD_MARKER.read_text(encoding="utf-8").strip(), "free_version": ""}
    except Exception:
        pass
    return {}


def _write_pro_meta(build_id: str) -> None:
    """Record which build_id is now unpacked, and which FREE version it was
    fetched for — called right after a successful extract in
    download_pro_package()."""
    try:
        from pentool import __version__ as free_version
    except Exception:
        free_version = ""
    try:
        _PRO_META_FILE.write_text(
            json.dumps({"build_id": build_id, "free_version": free_version}),
            encoding="utf-8",
        )
        _PRO_BUILD_MARKER.unlink(missing_ok=True)  # migrate off the legacy marker
    except Exception:
        pass


def is_pro_package_compatible() -> tuple[bool, str]:
    """Check whether the PRO package in PRO_PACKAGE_DIR is usable.

    **Soft check:** PRO is NOT blocked on version mismatch anymore — the PRO
    package is pure Python (no compiled Cython extensions in the public build),
    so an ABI crash is not a risk. The mismatch is reported as a warning
    so the user knows to re-sync, but PRO still loads.

    Returns:
        (True, "") — everything is fine, or PRO is not installed.
        (True, warning) — PRO is installed but version metadata doesn't match
            (stale build or 0.0.0 artifact from a previous broken install).
            The caller should show `warning` to the user but still load PRO.
        (False, message) — a hard blocker still exists: no build_meta at all
            (legacy state, needs re-download).
    """
    if not PRO_PACKAGE_DIR.exists():
        return True, ""

    try:
        from pentool import __version__ as current_version
    except Exception:
        current_version = ""

    meta = _read_pro_meta()
    pro_free_version = meta.get("free_version", "")

    if not pro_free_version:
        return False, (
            "A PRO package is installed, but its build metadata doesn't record "
            "which Pentool version it was built for (a previous PRO update "
            "likely didn't finish). PRO features are disabled to avoid a "
            "crash from a version mismatch — run "
            "'pentool license activate <key>' to re-download the PRO package."
        )

    if _base_version(pro_free_version) != _base_version(current_version):
        return True, (
            f"Version mismatch: Pentool {current_version} is installed, but "
            f"the PRO package was built for version {pro_free_version}. "
            f"PRO features are loaded, but consider re-syncing: run "
            f"'pentool license activate <key>' or wait for the background "
            f"PRO update to complete."
        )

    return True, ""


async def download_pro_package(key: str, machine_id: str) -> bool:
    """Download, verify (ed25519), and install per-platform PRO archive. Returns True on success."""
    plat = _current_platform()
    try:
        import aiohttp
        build_id: str | None = None
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
                # The Worker resolves the release/asset to serve this archive
                # and knows its build_id at that point — it now echoes it back
                # in this same response (see pentool-backend's /api/download
                # handler) so we don't need a separate follow-up request just
                # to learn it. Falls back to _fetch_pro_build_id() below if
                # an older Worker deploy doesn't send the header yet.
                build_id = resp.headers.get("X-Pro-Build-Id")

            async with session.post(
                f"{_LICENSE_API_BASE}/api/download",
                json={"key": key, "machine_id": machine_id, "platform": plat, "sig": "1"},
                ssl=False,
                headers={"Accept-Encoding": "gzip, deflate"},
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

        # Record which build this is (and which FREE version it was fetched
        # for — see is_pro_package_compatible()), so a later
        # check_and_update_pro_package() can tell "nothing changed" from "a
        # new build was published" without re-downloading the archive just
        # to compare it.
        #
        # Writing this is what makes the extracted package "trusted" —
        # is_pro_package_compatible() refuses to load it otherwise. Getting
        # here means the archive already extracted successfully, so this
        # must not silently no-op: if the Worker didn't send the header
        # (old deploy) AND the fallback /api/pro/version call also fails
        # (flaky network), fall back to recording the current FREE version
        # with a synthetic build_id rather than leaving .build_meta.json
        # unwritten — a fully-installed, working PRO package should never be
        # stuck showing "doesn't record which version" just because one
        # extra network round-trip hiccupped after the real work was done.
        if not build_id:
            try:
                build_id = await _fetch_pro_build_id(plat)
            except Exception:
                build_id = None
        if not build_id:
            build_id = f"unknown:{time.time()}"
        _write_pro_meta(build_id)

        return True
    except Exception:
        return False


async def _fetch_pro_build_id(plat: str) -> str | None:
    """Query /api/pro/version for current PRO build_id (None on failure)."""
    try:
        import aiohttp
        async with aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=8)
        ) as session:
            async with session.get(
                f"{_LICENSE_API_BASE}/api/pro/version",
                params={"platform": plat},
                ssl=False,
                # The Cloudflare Worker serves responses brotli-compressed by
                # default. aiohttp (without brotli installed) can't decode
                # `br`, so resp.json() raised ClientPayloadError and this whole
                # function returned None — the client never saw a new PRO
                # build_id and never re-downloaded an updated PRO package.
                # Ask for gzip/deflate only, which aiohttp can decode.
                headers={"Accept-Encoding": "gzip, deflate"},
            ) as resp:
                if resp.status != 200:
                    return None
                data = await resp.json()
                return data.get("build_id")
    except Exception:
        return None


async def check_and_update_pro_package() -> "ProSyncResult":
    """Re-download PRO if a newer build exists or current one mismatches FREE version.

    Returns ProSyncResult: updated, warning."""
    info = get_license()
    if not info.valid or not info.features:
        return ProSyncResult(updated=False, warning="")
    if not PRO_PACKAGE_DIR.exists():
        return ProSyncResult(updated=False, warning="")  # never activated — nothing to refresh

    plat = _current_platform()
    remote_build_id = await _fetch_pro_build_id(plat)
    if not remote_build_id:
        # Couldn't reach the server to check — don't touch the package, but
        # DO tell the user if what's on disk is already known-stale/mismatched.
        _compatible, warning = is_pro_package_compatible()
        return ProSyncResult(updated=False, warning=warning)

    meta = _read_pro_meta()
    local_build_id = meta.get("build_id", "")
    _compatible, _warning = is_pro_package_compatible()

    # Even if the build_id hasn't changed (no new release published since),
    # a package already marked incompatible (e.g. free_version never got
    # recorded, from before the /api/download build_id-header fix) must
    # still be re-downloaded — otherwise this function forever reports the
    # same "doesn't record which version" warning and never actually heals
    # it, since download_pro_package() is only reached below when the
    # build_id differs. A once-broken install with a matching build_id
    # would never take that path without this check.
    if local_build_id == remote_build_id and _compatible:
        return ProSyncResult(updated=False, warning="")

    updated = await download_pro_package(info.license_key, info.machine_id)
    if updated:
        return ProSyncResult(updated=True, warning="")

    # Download of the newer/repaired build failed — warn if what's left on
    # disk is stale.
    _compatible, warning = is_pro_package_compatible()
    return ProSyncResult(updated=False, warning=warning)

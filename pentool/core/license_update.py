"""PRO-package updater domain: signature verify + safe tar extract + platform.

Extracted from core/license.py (Этап 6, license_update) so the PRO-download
mechanics are pure and testable in isolation, separate from license state.
"""

from __future__ import annotations

import base64
import platform
import tarfile
from pathlib import Path

# ed25519 public key (base64) matching pentool-pro's PRO_SIGNING_KEY.
PRO_PACKAGE_PUBLIC_KEY_B64 = "MMPAM1xmvGV/CaLlT0doHoUH+Uv2zvVMSmPzNBglgBA="


def verify_pro_package_signature(archive_bytes: bytes, signature_b64: str) -> bool:
    """Verify the ed25519 detached signature over the raw archive bytes."""
    try:
        from cryptography.exceptions import InvalidSignature
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

        public_key = Ed25519PublicKey.from_public_bytes(
            base64.b64decode(PRO_PACKAGE_PUBLIC_KEY_B64)
        )
        signature = base64.b64decode(signature_b64.strip())
        public_key.verify(signature, archive_bytes)
        return True
    except InvalidSignature:
        return False
    except Exception:
        return False


def safe_extract_tar(archive_path: Path, dest_dir: Path) -> None:
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


def current_platform() -> str:
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

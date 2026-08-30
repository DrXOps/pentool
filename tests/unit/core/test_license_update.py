"""Unit tests for core/license_update.py (Этап 6, PRO package updater).

These are the pure helpers extracted from license.py — signature verify,
safe tar extract, platform mapping.
"""

from __future__ import annotations

import tarfile
from pathlib import Path

import pytest

from pentool.core.license_update import (
    current_platform,
    safe_extract_tar,
    verify_pro_package_signature,
)


class TestVerifySignature:
    def test_garbage_returns_false(self):
        # Malformed signature / bytes must return False, never raise.
        assert verify_pro_package_signature(b"package-bytes", "not-a-b64-sig") is False

    def test_empty_archive_false(self):
        assert verify_pro_package_signature(b"", "") is False


class TestSafeExtractTar:
    def _make_tar(self, target: Path, member_name: str):
        src = target.parent / "content.txt"
        src.write_text("hello")
        arc = target.parent / "pkg.tar.gz"
        with tarfile.open(arc, "w:gz") as tar:
            tar.add(src, arcname=member_name)
        return arc

    def test_clean_extract(self, tmp_path):
        dest = tmp_path / "out"
        dest.mkdir()
        arc = self._make_tar(tmp_path / "x", "ok/file.txt")
        safe_extract_tar(arc, dest)
        assert (dest / "ok" / "file.txt").exists()

    def test_path_traversal_refused(self, tmp_path):
        dest = tmp_path / "out"
        dest.mkdir()
        arc = self._make_tar(tmp_path / "x", "../escape.txt")
        with pytest.raises(ValueError):
            safe_extract_tar(arc, dest)
        # nothing escaped
        assert not (tmp_path / "escape.txt").exists()


class TestCurrentPlatform:
    @pytest.mark.parametrize("sys,expected", [
        ("Linux", "linux"), ("Darwin", "macos"), ("Windows", "windows"),
        ("FreeBSD", "linux"),
    ])
    def test_mapping(self, monkeypatch, sys, expected):
        monkeypatch.setattr(
            "pentool.core.license_update.platform.system", lambda: sys
        )
        assert current_platform() == expected

"""Unit tests: utils/lightpanda.py — headless JS rendering via Lightpanda (Этап A)."""

from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from pentool.utils.lightpanda import (
    find_lightpanda_binary,
    is_lightpanda_available,
    lightpanda_fetch_html,
)


class TestFindBinary:
    @patch.dict("os.environ", {}, clear=False)
    def test_returns_none_when_not_installed(self):
        with patch("pentool.utils.lightpanda.shutil.which", return_value=None), \
             patch.object(Path, "is_file", return_value=False):
            assert find_lightpanda_binary() is None

    def test_finds_on_path(self):
        with patch("pentool.utils.lightpanda.shutil.which", return_value="/usr/local/bin/lightpanda"), \
             patch.object(Path, "is_file", return_value=True), \
             patch("os.access", return_value=True):
            assert find_lightpanda_binary() == "/usr/local/bin/lightpanda"

    def test_prefers_env_bin(self):
        # env-override is checked first and beats PATH/HINTs (which we stub
        # away so they cannot accidentally match a real system install).
        with patch.dict("os.environ", {"LIGHTPANDA_BIN": "/custom/lightpanda"}), \
             patch("pentool.utils.lightpanda.shutil.which", return_value=None), \
             patch("pentool.utils.lightpanda._INSTALL_HINTS", ()), \
             patch.object(Path, "is_file", return_value=True), \
             patch("os.access", return_value=True):
            assert find_lightpanda_binary() == "/custom/lightpanda"

    def test_home_hint(self, tmp_path: Path):
        # Create an actual executable file under a hint location.
        fake_dir = tmp_path / ".local" / "bin"
        fake_dir.mkdir(parents=True, exist_ok=True)
        fake = fake_dir / "lightpanda"
        fake.write_text("")
        fake.chmod(0o755)
        with patch.dict("os.environ", {}, clear=False), \
             patch("pentool.utils.lightpanda.shutil.which", return_value=None), \
             patch("pentool.utils.lightpanda._INSTALL_HINTS", (str(fake),)), \
             patch("os.access", return_value=True):
            assert find_lightpanda_binary() == str(fake)


class TestIsAvailable:
    def test_false_without_binary(self):
        with patch("pentool.utils.lightpanda.find_lightpanda_binary", return_value=None):
            assert is_lightpanda_available() is False

    def test_true_with_binary(self):
        with patch("pentool.utils.lightpanda.find_lightpanda_binary", return_value="/x/lightpanda"):
            assert is_lightpanda_available() is True


class TestFetchHtml:
    async def test_returns_none_when_no_binary(self):
        with patch("pentool.utils.lightpanda.find_lightpanda_binary", return_value=None):
            assert await lightpanda_fetch_html("http://example.com") is None

    async def test_returns_none_on_timeout(self):
        from unittest.mock import Mock

        fake_proc = AsyncMock()
        fake_proc.communicate = AsyncMock(side_effect=asyncio.TimeoutError())
        fake_proc.returncode = 0
        fake_proc.kill = Mock(return_value=None)  # asyncio Process.kill() is sync
        with patch("pentool.utils.lightpanda.find_lightpanda_binary", return_value="/x/lightpanda"), \
             patch("pentool.utils.lightpanda.asyncio.create_subprocess_exec",
                   return_value=fake_proc):
            assert await lightpanda_fetch_html("http://example.com", timeout=1) is None

    async def test_returns_none_on_nonzero_exit(self):
        fake_proc = AsyncMock()
        fake_proc.communicate = AsyncMock(return_value=(b"<html></html>", b""))
        fake_proc.returncode = 1
        with patch("pentool.utils.lightpanda.find_lightpanda_binary", return_value="/x/lightpanda"), \
             patch("pentool.utils.lightpanda.asyncio.create_subprocess_exec",
                   return_value=fake_proc):
            assert await lightpanda_fetch_html("http://example.com") is None

    async def test_returns_html_on_success(self):
        fake_proc = AsyncMock()
        fake_proc.communicate = AsyncMock(return_value=(b"<html>rendered</html>", b""))
        fake_proc.returncode = 0
        with patch("pentool.utils.lightpanda.find_lightpanda_binary", return_value="/x/lightpanda"), \
             patch("pentool.utils.lightpanda.asyncio.create_subprocess_exec",
                   return_value=fake_proc) as exec_mock:
            html = await lightpanda_fetch_html("https://example.com")
        assert html == "<html>rendered</html>"
        # команда: lightpanda fetch --dump html <url>
        args = exec_mock.call_args.args
        assert args[0] == "/x/lightpanda"
        assert args[1:3] == ("fetch", "--dump")
        assert args[3] == "html"
        assert args[4] == "https://example.com"

    async def test_returns_none_on_exception(self):
        with patch("pentool.utils.lightpanda.find_lightpanda_binary", return_value="/x/lightpanda"), \
             patch("pentool.utils.lightpanda.asyncio.create_subprocess_exec",
                   side_effect=RuntimeError("boom")):
            assert await lightpanda_fetch_html("http://example.com") is None

    async def test_never_raises_on_decode_issue(self):
        fake_proc = AsyncMock()
        # invalid UTF-8 → decode errors="replace" → still returns str
        fake_proc.communicate = AsyncMock(return_value=(b"\xff\xfe bogus", b""))
        fake_proc.returncode = 0
        with patch("pentool.utils.lightpanda.find_lightpanda_binary", return_value="/x/lightpanda"), \
             patch("pentool.utils.lightpanda.asyncio.create_subprocess_exec",
                   return_value=fake_proc):
            html = await lightpanda_fetch_html("http://example.com")
        assert isinstance(html, str)


class TestFetchHtmlIntegration:
    """Optional live integration — needs a real `lightpanda` binary in PATH.

    Skipped unless the binary is installed, so this never breaks CI/packaging
    when the third-party binary is absent.
    """

    @pytest.mark.asyncio
    @pytest.mark.skipif(
        find_lightpanda_binary() is None,
        reason="lightpanda binary not installed",
    )
    async def test_fetch_rendered_html_live(self):
        # A page whose title is written via JS must come back rendered.
        html = await lightpanda_fetch_html("https://example.com", timeout=25)
        assert html is not None and "<html" in html.lower()

"""Unit tests: core/updater.py — version parsing and GitHub release check."""

from __future__ import annotations

import asyncio
import sys
import types
from contextlib import contextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from pentool.core.updater import (
    _parse_version,
    check_update_async,
    check_update_sync,
    do_pip_upgrade,
)


@contextmanager
def _fake_aiohttp(session_mock):
    """Substitute sys.modules['aiohttp'] with a minimal fake so updater's
    local `import aiohttp` picks up our mock. Returns the fake module."""
    fake = types.ModuleType("aiohttp")
    fake.ClientSession = lambda *a, **k: session_mock
    fake.ClientTimeout = MagicMock
    fake__ = types.ModuleType("aiohttp_client_timeout")  # not needed
    real = sys.modules.get("aiohttp")
    sys.modules["aiohttp"] = fake
    try:
        yield fake
    finally:
        if real is not None:
            sys.modules["aiohttp"] = real
        else:
            del sys.modules["aiohttp"]


def test_parse_version_ok():
    assert _parse_version("v1.2.3") == (1, 2, 3)
    assert _parse_version("1.2.3") == (1, 2, 3)
    assert _parse_version("v10.0.0") == (10, 0, 0)
    assert _parse_version("  v2.1.4  ") == (2, 1, 4)


def test_parse_version_short_and_bad():
    assert _parse_version("v1.2") == (1, 2)
    assert _parse_version("v2") == (2,)
    assert _parse_version("not-a-version") == (0,)
    assert _parse_version("") == (0,)


def test_parse_version_compares_major_minor_patch():
    assert _parse_version("v2.0.0") > _parse_version("v1.9.9")
    assert _parse_version("v1.1.0") > _parse_version("v1.0.9")
    assert _parse_version("v1.0.1") > _parse_version("v1.0.0")


def _make_session(json_result=None, status=200, exc=None):
    # aiohttp's `async with session.get(...) as resp:` works because session.get()
    # returns an object whose __aenter__ is a coroutine that yields the response.
    resp = AsyncMock()
    resp.status = status
    if exc is None:
        resp.json = AsyncMock(return_value=json_result)
    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=resp)
    cm.__aexit__ = AsyncMock(return_value=False)
    session = MagicMock()
    if exc is not None:
        session.get = MagicMock(side_effect=exc)
    else:
        session.get = MagicMock(return_value=cm)
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=False)
    return session


@pytest.mark.asyncio
async def test_check_update_no_update_when_same_version():
    session = _make_session(json_result={"tag_name": "v0.0.0", "html_url": "https://x"})
    with _fake_aiohttp(session), patch("pentool.__version__", "0.0.0"):
        info = await check_update_async()
    assert info.has_update is False


@pytest.mark.asyncio
async def test_check_update_has_update_when_newer():
    session = _make_session(json_result={"tag_name": "v99.0.0", "html_url": "https://release"})
    with _fake_aiohttp(session), patch("pentool.__version__", "0.1.0"):
        info = await check_update_async()
    assert info.has_update is True
    assert info.latest_version == "v99.0.0"
    assert info.url == "https://release"


@pytest.mark.asyncio
async def test_check_update_http_error():
    session = _make_session(status=404)
    with _fake_aiohttp(session):
        info = await check_update_async()
    assert info.has_update is False
    assert info.error == "HTTP 404"


@pytest.mark.asyncio
async def test_check_update_missing_aiohttp():
    real_import = __builtins__["__import__"] if isinstance(__builtins__, dict) else __builtins__.__import__

    def fake_import(name, *a, **k):
        if name == "aiohttp":
            raise ImportError("No module named 'aiohttp'")
        return real_import(name, *a, **k)

    with patch("builtins.__import__", side_effect=fake_import):
        info = await check_update_async()
    assert info.error == "aiohttp not installed"


@pytest.mark.asyncio
async def test_check_update_missing_tag():
    session = _make_session(json_result={"html_url": "https://x"})
    with _fake_aiohttp(session):
        info = await check_update_async()
    assert info.error == "no tag_name in response"


@pytest.mark.asyncio
async def test_check_update_timeout():
    session = _make_session(exc=asyncio.TimeoutError())
    with _fake_aiohttp(session):
        info = await check_update_async()
    assert info.error == "timeout"


@pytest.mark.asyncio
async def test_check_update_generic_exception():
    session = _make_session(exc=RuntimeError("boom"))
    with _fake_aiohttp(session):
        info = await check_update_async()
    assert "boom" in info.error


def test_check_update_sync_success():
    result = MagicMock()
    result.has_update = False
    result.latest_version = "v0.0.0"
    result.url = ""
    with patch("pentool.core.updater.check_update_async", new=AsyncMock(return_value=result)):
        info = check_update_sync()
    assert info.has_update is False


def test_check_update_sync_error():
    with patch("pentool.core.updater.check_update_async", new=AsyncMock(side_effect=RuntimeError("loop fail"))):
        info = check_update_sync()
    assert "loop fail" in info.error


def test_do_pip_upgrade_success():
    proc = MagicMock()
    proc.returncode = 0
    with patch("subprocess.run", return_value=proc):
        assert do_pip_upgrade() is True


def test_do_pip_upgrade_failure_nonzero():
    proc = MagicMock()
    proc.returncode = 1
    with patch("subprocess.run", return_value=proc):
        assert do_pip_upgrade() is False


def test_do_pip_upgrade_exception():
    with patch("subprocess.run", side_effect=Exception("no pip")):
        assert do_pip_upgrade() is False

"""Unit tests: core/crash_reporter.py — anonymous crash + first-run telemetry."""

from __future__ import annotations

import sys
import types
from contextlib import contextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from pentool.core import crash_reporter as cr


@contextmanager
def _fake_aiohttp(post_mock=None, post_exc=None):
    class FakeSession:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        post = post_mock if post_mock is not None else MagicMock()

    fake = types.ModuleType("aiohttp")
    fake.ClientTimeout = MagicMock
    fake.ClientSession = FakeSession
    real = sys.modules.get("aiohttp")
    sys.modules["aiohttp"] = fake
    try:
        yield
    finally:
        if real is not None:
            sys.modules["aiohttp"] = real
        else:
            del sys.modules["aiohttp"]


def test_get_metadata_has_fields():
    with patch("pentool.__version__", "9.9.9"):
        md = cr._get_metadata()
    assert md["version"] == "9.9.9"
    assert "python" in md and "os" in md and "arch" in md


def test_get_metadata_version_unknown():
    with patch("pentool.__version__", create=False), \
         patch("builtins.__import__") as importer:
        def fake_import(name, *a, **k):
            if name == "pentool":
                raise ImportError
            return __import__(name, *a, **k)
        importer.side_effect = fake_import
        md = cr._get_metadata()
    assert md["version"] == "unknown"


def test_anonymize_removes_paths_and_tokens():
    tb = '  File "/home/user/project/pentool/foo.py", line 5\n  token: 0123456789abcdef0123456789abcdef\n'
    out = cr._anonymize(tb)
    assert "foo.py" in out
    assert "/home/user/project" not in out
    assert "<TOKEN>" in out
    assert "0123456789abcdef0123456789abcdef" not in out


@pytest.mark.asyncio
async def test_send_crash_async_success():
    post = AsyncMock(return_value=MagicMock())
    with _fake_aiohttp(post_mock=post):
        await cr.send_crash_async(ValueError("boom"))
    post.assert_awaited_once()
    args = post.await_args
    assert "exception" in args.kwargs["json"]
    assert args.kwargs["json"]["exception"] == "ValueError"


@pytest.mark.asyncio
async def test_send_crash_async_includes_traceback():
    post = AsyncMock(return_value=MagicMock())
    with _fake_aiohttp(post_mock=post):
        err = ValueError("x")
        await cr.send_crash_async(err)
    tb = post.await_args.kwargs["json"]["traceback"]
    assert "ValueError" in tb


@pytest.mark.asyncio
async def test_send_crash_async_missing_aiohttp():
    # Remove aiohttp → ImportError → returns silently
    real = sys.modules.get("aiohttp")
    sys.modules.pop("aiohttp", None)
    real_import = __builtins__["__import__"] if isinstance(__builtins__, dict) else __builtins__.__import__

    def fake_import(name, *a, **k):
        if name == "aiohttp":
            raise ImportError
        return real_import(name, *a, **k)

    try:
        with patch("builtins.__import__", side_effect=fake_import):
            await cr.send_crash_async(ValueError("x"))  # no raise
    finally:
        if real is not None:
            sys.modules["aiohttp"] = real


@pytest.mark.asyncio
async def test_send_crash_async_post_error_swallowed():
    with _fake_aiohttp(post_exc=RuntimeError("net down")):
        await cr.send_crash_async(ValueError("x"))  # no raise


def test_send_crash_honours_opt_out():
    cfg = MagicMock(send_crash_reports=False)
    with patch("pentool.core.config.get_config", return_value=cfg), \
         patch("pentool.core.crash_reporter.asyncio.new_event_loop") as nel:
        cr.send_crash(ValueError("x"))
    nel.assert_not_called()


def test_send_crash_sends_async():
    cfg = MagicMock(send_crash_reports=True)
    result = MagicMock()
    result.run_until_complete = MagicMock()
    with patch("pentool.core.config.get_config", return_value=cfg), \
         patch("pentool.core.crash_reporter.asyncio.new_event_loop", return_value=result):
        cr.send_crash(ValueError("x"))
    assert result.run_until_complete.called


def test_send_crash_config_error_swallowed():
    with patch("pentool.core.config.get_config", side_effect=ImportError), \
         patch("pentool.core.crash_reporter.asyncio.new_event_loop", side_effect=RuntimeError("no loop")):
        cr.send_crash(ValueError("x"))  # no raise


@pytest.mark.asyncio
async def test_first_run_ping_success():
    post = AsyncMock(return_value=MagicMock())
    with _fake_aiohttp(post_mock=post), \
         patch("pentool.core.license.get_machine_id", return_value="mach-123"):
        await cr.send_first_run_ping_async()
    json_body = post.await_args.kwargs["json"]
    assert json_body == {"machine_id": "mach-123"}


@pytest.mark.asyncio
async def test_first_run_ping_license_error_returns():
    with _fake_aiohttp(), \
         patch("pentool.core.license.get_machine_id", side_effect=Exception("no license")):
        await cr.send_first_run_ping_async()  # no raise


@pytest.mark.asyncio
async def test_first_run_ping_missing_aiohttp():
    real = sys.modules.get("aiohttp")
    sys.modules.pop("aiohttp", None)
    real_import = __builtins__["__import__"] if isinstance(__builtins__, dict) else __builtins__.__import__

    def fake_import(name, *a, **k):
        if name == "aiohttp":
            raise ImportError
        return real_import(name, *a, **k)

    try:
        with patch("builtins.__import__", side_effect=fake_import):
            await cr.send_first_run_ping_async()
    finally:
        if real is not None:
            sys.modules["aiohttp"] = real


def test_first_run_ping_honours_opt_out():
    cfg = MagicMock(send_crash_reports=False)
    with patch("pentool.core.config.get_config", return_value=cfg), \
         patch("pentool.core.crash_reporter.asyncio.new_event_loop") as nel:
        cr.send_first_run_ping()
    nel.assert_not_called()


def test_first_run_ping_sends():
    cfg = MagicMock(send_crash_reports=True)
    result = MagicMock()
    result.run_until_complete = MagicMock()
    with patch("pentool.core.config.get_config", return_value=cfg), \
         patch("pentool.core.crash_reporter.asyncio.new_event_loop", return_value=result):
        cr.send_first_run_ping()
    assert result.run_until_complete.called


@pytest.mark.asyncio
async def test_first_run_ping_post_error_swallowed():
    with _fake_aiohttp(post_exc=RuntimeError("down")), \
         patch("pentool.core.license.get_machine_id", return_value="m"):
        await cr.send_first_run_ping_async()  # no raise


def test_send_crash_config_exception_still_attempts():
    # get_config raises but send_crash should still try (except-pass)
    result = MagicMock()
    result.run_until_complete = MagicMock()
    with patch("pentool.core.config.get_config", side_effect=Exception("cfg")), \
         patch("pentool.core.crash_reporter.asyncio.new_event_loop", return_value=result):
        cr.send_crash(ValueError("x"))
    assert result.run_until_complete.called


def test_first_run_ping_config_exception_still_attempts():
    result = MagicMock()
    result.run_until_complete = MagicMock()
    with patch("pentool.core.config.get_config", side_effect=Exception("cfg")), \
         patch("pentool.core.crash_reporter.asyncio.new_event_loop", return_value=result):
        cr.send_first_run_ping()
    assert result.run_until_complete.called


def test_send_first_run_ping_loop_error_swallowed():
    cfg = MagicMock(send_crash_reports=True)
    with patch("pentool.core.config.get_config", return_value=cfg), \
         patch("pentool.core.crash_reporter.asyncio.new_event_loop", side_effect=RuntimeError("no loop")):
        cr.send_first_run_ping()  # no raise

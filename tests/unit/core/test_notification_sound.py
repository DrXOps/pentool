"""Unit tests: core/notification_sound.py — best-effort OS notification sounds.

2026-08-30: by design, Linux/macOS no longer fork a subprocess player (that
produced _fork_exec-frozen daemon threads on rapid-fire notifications, which
stalled the UI and caused abnormal "run() returned cleanly" exits). Linux and
macOS now fall back to the terminal BEL only; Windows keeps in-process
winsound.Beep(). These tests lock in the no-subprocess guarantee.
"""

from __future__ import annotations

import sys
import types
from contextlib import contextmanager
from unittest.mock import patch

import pytest

from pentool.core import notification_sound as ns


@contextmanager
def _fake_winsound():
    """Provide a fake winsound module so the windows branch is importable on Linux."""
    fake = types.ModuleType("winsound")
    fake.Beep = None  # replaced by patch in tests
    real = sys.modules.get("winsound")
    sys.modules["winsound"] = fake
    try:
        yield
    finally:
        if real is not None:
            sys.modules["winsound"] = real
        else:
            del sys.modules["winsound"]


def test_play_blocking_windows():
    with _fake_winsound(), patch.object(sys, "platform", "win32"), \
         patch("winsound.Beep") as beep:
        ns._play_blocking("success")
    assert beep.call_count == 1  # single in-process beep


def test_play_blocking_windows_unknown_severity_defaults_info():
    with _fake_winsound(), patch.object(sys, "platform", "win32"), \
         patch("winsound.Beep") as beep:
        ns._play_blocking("mystery")
    assert beep.call_count == 1


def test_play_blocking_windows_beep_error_falls_back_to_bell():
    with _fake_winsound(), patch.object(sys, "platform", "win32"), \
         patch("winsound.Beep", side_effect=RuntimeError("no device")), \
         patch("pentool.core.notification_sound._terminal_bell") as bell:
        ns._play_blocking("information")
    bell.assert_called_once()


def test_play_blocking_macos_uses_bell_only():
    # macOS must NOT fork afplay anymore — stability-first product decision.
    with patch.object(sys, "platform", "darwin"), \
         patch("pentool.core.notification_sound._terminal_bell") as bell:
        ns._play_blocking("information")
    bell.assert_called_once()


def test_play_blocking_linux_uses_bell_only():
    # Linux must NOT fork aplay/paplay — same stability-first decision.
    with patch.object(sys, "platform", "linux"), \
         patch("pentool.core.notification_sound._terminal_bell") as bell:
        ns._play_blocking("error")
    bell.assert_called_once()


def test_non_windows_never_spawns_subprocess():
    """Guard: playback code must not fork a subprocess (stability decision).

    Only the docstring mentions "subprocess" historically; assert against the
    actual code (excludes comment/docstring text) to stay meaningful.
    """
    import ast
    import inspect

    src = inspect.getsource(ns)
    tree = ast.parse(src)
    nodes = [n for n in ast.walk(tree) if isinstance(n, ast.Name, )]
    forbidden = {"subprocess", "Popen", "popen", "fork"}
    offending = sorted({n.id for n in nodes if n.id in forbidden})
    assert not offending, f"playback imports subprocess-forks: {offending}"


def test_play_blocking_unknown_platform_uses_bell():
    with patch.object(sys, "platform", "os2"), \
         patch("pentool.core.notification_sound._terminal_bell") as bell:
        ns._play_blocking("info")
    bell.assert_called_once()


def test_play_blocking_swallows_exception():
    with _fake_winsound(), patch.object(sys, "platform", "win32"), \
         patch("winsound.Beep", side_effect=RuntimeError("device")), \
         patch("pentool.core.notification_sound._terminal_bell", side_effect=RuntimeError("stdout")):
        # both beep and bell fail — still no raise
        ns._play_blocking("info")


def test_terminal_bell_counts_by_int():
    writes = []
    with patch("sys.stdout") as stdout:
        stdout.write.side_effect = lambda s: writes.append(s)
        ns._terminal_bell(3)  # critical
        ns._terminal_bell(2)  # warning/error
        ns._terminal_bell(1)  # info/success
    assert writes == ["\a\a\a", "\a\a", "\a"]


def test_terminal_bell_swallows_write_error():
    with patch("sys.stdout.write", side_effect=OSError("closed")):
        ns._terminal_bell(1)  # no raise


def test_play_notification_sound_starts_thread():
    with patch("threading.Thread") as Thread:
        instance = Thread.return_value
        instance.start.return_value = None
        ns.play_notification_sound("success")
    Thread.assert_called_once()
    assert instance.start.called


def test_play_notification_sound_handles_thread_error():
    with patch("threading.Thread.start", side_effect=RuntimeError("boom")):
        ns.play_notification_sound("info")  # no raise

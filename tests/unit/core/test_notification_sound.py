"""Unit tests: core/notification_sound.py — best-effort OS notification sounds."""

from __future__ import annotations

import sys
import types
from contextlib import contextmanager
from unittest.mock import patch

import pytest

from pentool.core import notification_sound as ns


@contextmanager
def _fake_winsound():
    """Provide a fake winsound module so windows-import works on Linux."""
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
    # success tone = two beeps (freq, dur) pairs
    assert beep.call_count == 2


def test_play_blocking_windows_unknown_severity_defaults_info():
    with _fake_winsound(), patch.object(sys, "platform", "win32"), \
         patch("winsound.Beep") as beep:
        ns._play_blocking("mystery")
    assert beep.call_count == 1  # information = single beep


def test_play_blocking_windows_beep_error_falls_back_to_bell():
    with _fake_winsound(), patch.object(sys, "platform", "win32"), \
         patch("winsound.Beep", side_effect=RuntimeError("no device")), \
         patch("pentool.core.notification_sound._terminal_bell") as bell:
        ns._play_blocking("information")
    bell.assert_called_once()


def test_play_blocking_macos_with_afplay():
    with patch.object(sys, "platform", "darwin"), \
         patch("pentool.core.notification_sound.shutil.which", return_value="/usr/bin/afplay"), \
         patch("pentool.core.notification_sound.subprocess.run") as run:
        ns._play_blocking("information")
    run.assert_called_once()


def test_play_blocking_macos_without_afplay():
    with patch.object(sys, "platform", "darwin"), \
         patch("pentool.core.notification_sound.shutil.which", return_value=None), \
         patch("pentool.core.notification_sound._terminal_bell") as bell:
        ns._play_blocking("information")
    bell.assert_called_once()


def test_play_blocking_linux_uses_bell_when_no_player():
    with patch.object(sys, "platform", "linux"), \
         patch("pentool.core.notification_sound.shutil.which", return_value=None), \
         patch("pentool.core.notification_sound._terminal_bell") as bell:
        ns._play_blocking("error")
    bell.assert_called_once_with("error")


def test_play_blocking_linux_uses_real_tone_when_player_exists():
    with patch.object(sys, "platform", "linux"), \
         patch("pentool.core.notification_sound.shutil.which", return_value="/usr/bin/aplay"), \
         patch("pentool.core.notification_sound.subprocess.run") as run:
        ns._play_blocking("success")
    run.assert_called_once()
    # aplay reads the WAV stream from stdin
    assert run.call_args.args[0] == ["/usr/bin/aplay", "-"]
    # the piped input is a valid RIFF/WAVE blob
    wav = run.call_args.kwargs.get("input") or run.call_args.args[0][-1]
    assert wav[:4] == b"RIFF"


def test_play_blocking_unknown_platform_uses_bell():
    with patch.object(sys, "platform", "os2"), \
         patch("pentool.core.notification_sound.shutil.which", return_value=None), \
         patch("pentool.core.notification_sound._terminal_bell"):
        ns._play_blocking("info")  # falls into else → _play_linux → bell


def test_play_blocking_swallows_exception():
    with _fake_winsound(), patch.object(sys, "platform", "win32"), \
         patch("winsound.Beep", side_effect=RuntimeError("device")), \
         patch("pentool.core.notification_sound._terminal_bell", side_effect=RuntimeError("stdout")):
        # both beep and bell fail — still no raise
        ns._play_blocking("info")


def test_terminal_bell_counts_by_severity():
    writes = []
    with patch("sys.stdout") as stdout:
        stdout.write.side_effect = lambda s: writes.append(s)
        ns._terminal_bell("critical")
        ns._terminal_bell("warning")
        ns._terminal_bell("success")
    assert writes == ["\a\a\a", "\a\a", "\a"]


def test_terminal_bell_missing_severity_default():
    writes = []
    with patch("sys.stdout") as stdout:
        stdout.write.side_effect = lambda s: writes.append(s)
        ns._terminal_bell("bogus")
    assert writes == ["\a"]


def test_terminal_bell_swallows_write_error():
    with patch("sys.stdout.write", side_effect=OSError("closed")):
        ns._terminal_bell()  # no raise


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

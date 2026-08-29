"""Unit tests: TerminalScreen._read_pty must not raise when the App is gone.

Regression guard for "Exception in thread pty-reader ... active_app.get()":
the pty-reader background thread calls self.app.call_from_thread(...), and
self.app resolves via active_app.get() which raises LookupError once the app
is no longer in the active asyncio context (teardown / from this off-loop
thread). Previously that exception escaped the thread as a noisy
"Exception in thread pty-reader" traceback. Now it's caught and the reader
stops cleanly.
"""

from __future__ import annotations

import os
import select
from unittest.mock import patch

from pentool.tui.screens.terminal.screen import TerminalScreen


class _GoneApp:
    """An App stub whose call_from_thread raises the same LookupError Textual
    does when there's no active app."""
    def call_from_thread(self, *a, **k):
        raise LookupError("No active app for this context")


def _make_screen():
    screen = object.__new__(TerminalScreen)
    screen._pty_running = True
    screen._pty_master = 9999  # fake fd
    screen._append_output = lambda text: None
    return screen


def test_read_pty_stops_cleanly_when_app_gone():
    """os.read yields data, then app unavailable -> reader breaks, no raise."""
    screen = _make_screen()
    reads = iter([b"some output\n", b""])  # EOF after one line

    def _fake_select(rlist, w, x, timeout):
        return (rlist, [], [])

    def _fake_read(fd, n):
        return next(reads)

    # self.app resolves via Textual's MessagePump.app (active_app.get());
    # simulate it returning a stub whose call_from_thread raises the same
    # LookupError Textual does when there's no active app.
    with patch.object(select, "select", side_effect=_fake_select), \
         patch.object(os, "read", side_effect=_fake_read), \
         patch("textual.message_pump.MessagePump.app",
               new=property(lambda self: _GoneApp())):
        try:
            screen._read_pty()
        except Exception as exc:  # pragma: no cover - should not reach here
            assert False, f"_read_pty raised during teardown: {exc}"


def test_read_pty_no_app_call_after_none_master():
    """If _pty_master is None the reader exits immediately without touching app."""
    screen = _make_screen()
    screen._pty_master = None
    # Would raise if it tried self.app (no pty master -> breaks before that)
    try:
        screen._read_pty()
    except Exception as exc:  # pragma: no cover
        assert False, f"_read_pty raised: {exc}"

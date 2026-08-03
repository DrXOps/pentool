"""Unit tests: БАГ-C — periodic cleanup of ProxyScreen._pending_req_ids.

Covers _cleanup_pending_req_ids(): stale entries (older than 10 minutes)
must be removed from both _pending_req_ids and _pending_req_ids_ts,
while fresh entries must survive.

Built without starting Textual (object.__new__), following the pattern
used in tests/unit/tui/test_message_storm.py.
"""

from __future__ import annotations

import time

from pentool.tui.screens.proxy.screen import ProxyScreen


def _make_screen() -> ProxyScreen:
    """Minimal ProxyScreen instance with only the attributes under test."""
    screen = object.__new__(ProxyScreen)
    screen._pending_req_ids = {}
    screen._pending_req_ids_ts = {}
    return screen


class TestCleanupPendingReqIds:
    def test_no_entries_is_noop(self) -> None:
        screen = _make_screen()
        screen._cleanup_pending_req_ids()
        assert screen._pending_req_ids == {}
        assert screen._pending_req_ids_ts == {}

    def test_fresh_entries_survive(self) -> None:
        screen = _make_screen()
        now = time.time()
        screen._pending_req_ids = {"req-1": -1, "req-2": 42}
        screen._pending_req_ids_ts = {"req-1": now, "req-2": now - 60}

        screen._cleanup_pending_req_ids()

        assert "req-1" in screen._pending_req_ids
        assert "req-2" in screen._pending_req_ids
        assert screen._pending_req_ids_ts == {"req-1": now, "req-2": now - 60}

    def test_stale_entry_removed(self) -> None:
        screen = _make_screen()
        now = time.time()
        stale_ts = now - 700  # > 10 minutes old
        screen._pending_req_ids = {"stale-req": -1}
        screen._pending_req_ids_ts = {"stale-req": stale_ts}

        screen._cleanup_pending_req_ids()

        assert "stale-req" not in screen._pending_req_ids
        assert "stale-req" not in screen._pending_req_ids_ts

    def test_mixed_stale_and_fresh(self) -> None:
        screen = _make_screen()
        now = time.time()
        screen._pending_req_ids = {"old": -1, "new": 7}
        screen._pending_req_ids_ts = {
            "old": now - 900,   # 15 min ago — stale
            "new": now - 30,    # 30 sec ago — fresh
        }

        screen._cleanup_pending_req_ids()

        assert "old" not in screen._pending_req_ids
        assert "old" not in screen._pending_req_ids_ts
        assert screen._pending_req_ids["new"] == 7
        assert "new" in screen._pending_req_ids_ts

    def test_boundary_just_under_10_minutes_survives(self) -> None:
        """Entry at 9m59s should NOT be considered stale."""
        screen = _make_screen()
        now = time.time()
        screen._pending_req_ids = {"boundary": -1}
        screen._pending_req_ids_ts = {"boundary": now - 599}

        screen._cleanup_pending_req_ids()

        assert "boundary" in screen._pending_req_ids

    def test_boundary_just_over_10_minutes_removed(self) -> None:
        """Entry at 10m01s should be considered stale."""
        screen = _make_screen()
        now = time.time()
        screen._pending_req_ids = {"boundary": -1}
        screen._pending_req_ids_ts = {"boundary": now - 601}

        screen._cleanup_pending_req_ids()

        assert "boundary" not in screen._pending_req_ids

    def test_pending_req_ids_and_ts_stay_in_sync(self) -> None:
        """Cleanup must never leave orphaned keys in either dict."""
        screen = _make_screen()
        now = time.time()
        screen._pending_req_ids = {"a": -1, "b": 1, "c": 2}
        screen._pending_req_ids_ts = {
            "a": now - 1000,
            "b": now - 1000,
            "c": now,
        }

        screen._cleanup_pending_req_ids()

        assert set(screen._pending_req_ids.keys()) == set(screen._pending_req_ids_ts.keys())
        assert "c" in screen._pending_req_ids

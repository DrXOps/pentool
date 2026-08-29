"""Intruder.load_request must reset stale results from a previous target.

User report: sending a NEW host to Intruder kept showing the previous host's
attack results in the table. load_request only loaded the raw request and
never cleared the old _all_results table, so a new host started with leftover
rows. Now it clears results first — a fresh target starts with an empty table.
"""

from __future__ import annotations

import types

from pentool.tui.screens.intruder.screen import IntruderScreen


class _FakeEditor:
    """Template editor: load_raw records what was loaded."""

    def __init__(self):
        self.loaded_raw = None

    def load_raw(self, raw, markers=None):
        self.loaded_raw = raw


class _FakeApp:
    pass


def _make_screen():
    screen = object.__new__(IntruderScreen)
    # query_one returns our fake editor for the template editor selector
    editor = _FakeEditor()
    screen.query_one = lambda *a, **k: editor
    screen._update_payload_select = lambda: None
    screen._highlight_nth_marker = lambda idx: None
    return screen, editor


def test_load_request_clears_previous_results():
    screen, editor = _make_screen()
    # simulate leftover results from a previous host
    screen._all_results = ["old-result-1"]
    cleared = []

    original_clear = screen._clear_results

    def _spy_clear():
        cleared.append(1)
        original_clear()

    screen._clear_results = _spy_clear  # type: ignore[method-assign]

    screen.load_request("GET /new HTTP/1.1\r\nHost: new.example\r\n\r\n")
    assert cleared, "_clear_results should run when a new target request is loaded"
    assert screen._all_results == [], "previous host's results must not persist"

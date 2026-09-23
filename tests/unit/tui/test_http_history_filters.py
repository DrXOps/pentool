"""Unit tests for Proxy HTTP-history filter composition (Этап 6)."""

from __future__ import annotations

from pentool.tui.widgets.http_history_filters import build_history_filters


class TestBuildHistoryFilters:
    def test_none_stays_empty(self):
        assert build_history_filters(None, False) == {}
        assert build_history_filters({}, False) == {}

    def test_passthrough_bar_filters(self):
        f = build_history_filters({"host": "example.com", "status_code": 200}, False)
        assert f == {"host": "example.com", "status_code": 200}

    def test_show_comments_adds_flag(self):
        f = build_history_filters(None, True)
        assert f == {"has_comment": True}

    def test_show_comments_merges_with_bar_filters(self):
        f = build_history_filters({"host": "x"}, True)
        assert f == {"host": "x", "has_comment": True}

    def test_does_not_touch_input(self):
        # Caller's dict must not be mutated
        src = {"host": "x"}
        _ = build_history_filters(src, True)
        assert src == {"host": "x"}

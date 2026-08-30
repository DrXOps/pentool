"""Intruder results filter bar (Этап 6) — parse/build filter dicts.

Guards the extracted IntruderFilterBar: status / len_gt / len_lt parsing into
the shared filters dict, reset empty, and empty-reset posting.
"""

from __future__ import annotations

import types

from pentool.tui.widgets.intruder_filter_bar import IntruderFilterBar


def _make_bar(input_values: dict, grep_only_active: bool = False):
    bar = object.__new__(IntruderFilterBar)
    posted = []

    def _query_one(selector, cls=None):
        if selector.lstrip("#") == "grep-only-toggle":
            return types.SimpleNamespace(active=grep_only_active, reset=lambda: None)
        value = input_values.get(selector.lstrip("#"), "")
        return types.SimpleNamespace(value=value)

    bar.query_one = _query_one
    bar.post_message = lambda msg: posted.append(msg)
    return bar, posted


class TestEmitFilters:
    def test_parses_status_and_lengths(self):
        bar, posted = _make_bar({
            "filter-status": "404",
            "filter-len-gt": "100",
            "filter-len-lt": "200",
        })
        bar._emit_filters()
        assert len(posted) == 1
        f = posted[0].filters
        assert f == {"status": "404", "len_gt": 100, "len_lt": 200}

    def test_empty_inputs_produce_empty_dict(self):
        bar, posted = _make_bar({})
        bar._emit_filters()
        assert posted[0].filters == {}

    def test_non_numeric_length_ignored(self):
        bar, posted = _make_bar({"filter-len-gt": "abc"})
        bar._emit_filters()
        assert posted[0].filters == {}


class TestResetEmitsEmpty:
    def test_reset_posts_empty(self):
        bar, posted = _make_bar({"filter-status": "200"})
        bar._reset()
        assert posted[0].filters == {}


class TestGrep:
    def test_emit_grep(self):
        bar, posted = _make_bar({"grep-match-input": "sql", "grep-extract-input": ""})
        bar._emit_grep()
        assert posted[0].filters == {"grep_match": "sql"}

    def test_clear_grep_posts_empty(self):
        bar, posted = _make_bar({"grep-match-input": "x"})
        bar._clear_grep()
        assert posted[0].filters == {}

    def test_emit_grep_applies_only_match_toggle(self):
        bar, posted = _make_bar(
            {"grep-match-input": "sql"}, grep_only_active=True
        )
        bar._emit_grep()
        assert posted[0].filters == {"grep_match": "sql", "grep_only_match": True}

    def test_emit_grep_toggle_off_omits_flag(self):
        bar, posted = _make_bar(
            {"grep-match-input": "sql"}, grep_only_active=False
        )
        bar._emit_grep()
        assert posted[0].filters == {"grep_match": "sql"}

    def test_reset_clears_toggle(self):
        bar, posted = _make_bar({}, grep_only_active=True)
        bar._reset()
        # Reset drops everything (posts empty dict), toggle is reset internally
        assert posted[0].filters == {}

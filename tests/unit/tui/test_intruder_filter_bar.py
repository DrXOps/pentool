"""Intruder results filter bar — FilterSpec-based filter tests.

The bar emits FilterChanged with FilterSpec on Apply/Reset.
"""

from __future__ import annotations

import types

from pentool.collections.filter_predicate import FilterOp, FilterPredicate, FilterSpec
from pentool.tui.widgets.intruder_filter_bar import IntruderFilterBar


def _make_bar(input_values: dict, grep_only_active: bool = False):
    bar = object.__new__(IntruderFilterBar)
    posted = []

    def _query_one(selector, cls=None):
        sid = selector.lstrip("#")
        if sid == "grep-only-toggle":
            t = types.SimpleNamespace(is_active=lambda: grep_only_active, reset=lambda: None)
            return t
        value = input_values.get(sid, "")
        return types.SimpleNamespace(value=value)

    bar.query_one = _query_one
    bar.post_message = lambda msg: posted.append(msg)
    return bar, posted


class TestApply:
    def test_parses_status_and_lengths(self):
        bar, posted = _make_bar({
            "filter-status": "404",
            "filter-len-gt": "100",
            "filter-len-lt": "200",
        })
        bar._apply()
        assert len(posted) == 1
        spec = posted[0].spec
        assert isinstance(spec, FilterSpec)
        assert len(spec.predicates) == 3
        predicates = {(p.field, p.operator, p.value) for p in spec.predicates}
        assert ("status", FilterOp.EQ, "404") in predicates
        assert ("length", FilterOp.GT, 100) in predicates
        assert ("length", FilterOp.LT, 200) in predicates

    def test_empty_inputs_produce_empty_spec(self):
        bar, posted = _make_bar({})
        bar._apply()
        assert posted[0].spec.is_empty

    def test_non_numeric_length_ignored(self):
        bar, posted = _make_bar({"filter-len-gt": "abc"})
        bar._apply()
        assert posted[0].spec.is_empty


class TestResetEmitsEmpty:
    def test_reset_posts_empty(self):
        bar, posted = _make_bar({"filter-status": "200"})
        bar._reset()
        assert posted[0].spec.is_empty


class TestGrep:
    def test_emit_grep_match(self):
        bar, posted = _make_bar({"grep-match-input": "sql", "grep-extract-input": ""})
        bar._apply()
        spec = posted[0].spec
        assert any(p.field == "grep_match" for p in spec.predicates)

    def test_clear_grep_posts_empty(self):
        bar, posted = _make_bar({"grep-match-input": "x"})
        bar._clear_grep()
        assert posted[0].spec.is_empty

    def test_emit_grep_only_match_toggle(self):
        bar, posted = _make_bar(
            {"grep-match-input": "sql"}, grep_only_active=True
        )
        bar._apply()
        spec = posted[0].spec
        assert any(p.field == "grep_only_match" for p in spec.predicates)

    def test_emit_grep_toggle_off_omits_flag(self):
        bar, posted = _make_bar(
            {"grep-match-input": "sql"}, grep_only_active=False
        )
        bar._apply()
        spec = posted[0].spec
        assert all(p.field != "grep_only_match" for p in spec.predicates)

    def test_reset_clears_toggle(self):
        bar, posted = _make_bar({}, grep_only_active=True)
        bar._reset()
        assert posted[0].spec.is_empty
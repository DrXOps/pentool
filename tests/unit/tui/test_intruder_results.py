"""Unit tests for Intruder result-table predicate helpers (Этап 6)."""

from __future__ import annotations

import types

from pentool.tui.widgets.intruder_results import matches_grep, matches_result_filters


def _res(status=200, length=100, payloads=()):
    return types.SimpleNamespace(
        response_status=status,
        response_length=length,
        payload_values=list(payloads),
    )


class TestMatchesResultFilters:
    def test_no_filters_passes(self):
        assert matches_result_filters(_res(), status=None, len_gt=None, len_lt=None)

    def test_status_match(self):
        assert matches_result_filters(_res(status=404), status="404") is True
        assert matches_result_filters(_res(status=200), status="404") is False

    def test_len_gt_boundary(self):
        # length must be STRICTLY greater
        assert matches_result_filters(_res(length=101), len_gt=100) is True
        assert matches_result_filters(_res(length=100), len_gt=100) is False

    def test_len_lt_boundary(self):
        # length must be STRICTLY less
        assert matches_result_filters(_res(length=99), len_lt=100) is True
        assert matches_result_filters(_res(length=100), len_lt=100) is False

    def test_no_length_is_zero(self):
        # missing length treated as 0
        r = types.SimpleNamespace(response_status=200, response_length=None)
        assert matches_result_filters(r, len_gt=0) is False

    def test_combined(self):
        r = _res(status=200, length=150)
        assert matches_result_filters(r, status="200", len_gt=100, len_lt=200) is True
        assert matches_result_filters(r, status="200", len_gt=140, len_lt=145) is False

    def test_grep_only_match_keeps_hits(self):
        # Row whose payload holds the pattern is kept when grep_only_match is on
        r = _res(status=200, length=100, payloads=[">Hi>SQL<"])
        assert matches_grep(r, ["sql"]) is True
        assert matches_result_filters(
            r, grep_patterns=["sql"], grep_only_match=True
        ) is True

    def test_grep_only_match_drops_misses(self):
        r = _res(status=200, length=100, payloads=["plain"])
        assert matches_grep(r, ["sql"]) is False
        assert matches_result_filters(
            r, grep_patterns=["sql"], grep_only_match=True
        ) is False

    def test_grep_only_match_ignored_without_patterns(self):
        # Toggle on but no patterns active → nothing to filter on, row passes
        r = _res(status=200, length=100, payloads=["plain"])
        assert matches_result_filters(r, grep_patterns=None, grep_only_match=True) is True

    def test_grep_only_match_off_keeps_all(self):
        r = _res(status=200, length=100, payloads=["plain"])
        assert matches_result_filters(r, grep_patterns=["sql"], grep_only_match=False) is True


class TestMatchesGrep:
    def test_no_patterns_false(self):
        assert matches_grep(_res(), None) is False
        assert matches_grep(_res(), []) is False

    def test_matches_payload(self):
        r = _res(status=200, length=100, payloads=['"><script>alert(1)</script>'])
        assert matches_grep(r, ["script"]) is True

    def test_matches_status(self):
        assert matches_grep(_res(status=404), ["404"]) is True

    def test_case_insensitive(self):
        assert matches_grep(_res(payloads=["SQLi"]), ["sqli"]) is True

    def test_bad_pattern_skipped(self):
        # A malformed pattern is ignored; a valid co-pattern still matches
        r = _res(payloads=["token=abc"])
        assert matches_grep(r, ["[invalid", "token=abc"]) is True
        assert matches_grep(r, ["[invalid", "zzz"]) is False

    def test_first_hit_wins(self):
        r = _res(payloads=["a", "needle", "b"])
        assert matches_grep(r, ["needle"]) is True

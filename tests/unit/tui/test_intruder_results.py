"""Unit tests for Intruder result-table predicate helpers (Этап 6)."""

from __future__ import annotations

import types

from pentool.tui.widgets.intruder_results import matches_result_filters


def _res(status=200, length=100):
    return types.SimpleNamespace(response_status=status, response_length=length)


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

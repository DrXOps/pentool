"""Unit tests for the history paging rules (pure functions, no Textual).

These pin the two behaviours the tables depend on: one page at a time (the UI must not be
handed thousands of rows) and a counter that says when older rows are one scroll away.
"""

from __future__ import annotations

from pentool.tui.screens.proxy.history_view import count_text, merge_older, page_window, pick_row


def test_no_older_page_before_anything_is_loaded() -> None:
    # oldest_offset == 0 means nothing older exists: the loaders stop right here.
    assert page_window(0, 300) == (0, 0)


def test_next_page_ends_at_the_oldest_loaded_row() -> None:
    # 300 rows loaded (offsets 0..299): the older page is the 300 rows above them.
    assert page_window(300, 300) == (0, 300)
    # 600 loaded: one more page above.
    assert page_window(600, 300) == (300, 300)


def test_partial_page_still_stops_at_zero() -> None:
    # A short tail (100 rows left) must not go negative.
    assert page_window(100, 300) == (0, 100)


def test_older_page_is_prepended_in_table_order() -> None:
    # The service returns newest-first; the table is oldest-first.
    rows = [{"id": 3}, {"id": 4}]
    older_newest_first = [{"id": 2}, {"id": 1}]
    assert [row["id"] for row in merge_older(rows, older_newest_first)] == [1, 2, 3, 4]


def test_counter_says_how_to_reach_older_rows() -> None:
    assert count_text(300, 1200) == "Showing 300 of 1,200 records"
    assert count_text(300, 1200, more_available=True) == "Showing 300 of 1,200 records — scroll up to load more"
    # Everything loaded: no hint to give.
    assert "scroll up" not in count_text(1200, 1200, more_available=False)


def test_pick_row_ignores_a_stale_index() -> None:
    rows = [{"id": 1}, {"id": 2}]
    assert pick_row(rows, 1) == {"id": 2}
    # A highlight event can arrive after a reload shortened the table.
    assert pick_row(rows, 5) is None
    assert pick_row(rows, -1) is None

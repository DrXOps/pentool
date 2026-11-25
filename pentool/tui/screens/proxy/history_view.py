"""The "Showing N of M" counter of the Proxy history tables — one implementation.

HTTP History and WS History each had their own copy of this, and the copies had already
drifted: the HTTP one cached the text and skipped the widget update when the numbers did
not change (a Textual re-measure costs a full layout pass — measured ~55 ms with the cards
UI), while the WS one updated the label on every append. This module keeps the rule in one
place and gives both tables the same behaviour.
"""

from __future__ import annotations

from typing import Any, Callable

from pentool.core.logging import get_logger

logger = get_logger(__name__)


def count_text(shown: int, total: int) -> str:
    """Label text for a history table (thousands separators, same wording in both)."""
    return f"Showing {shown:,} of {total:,} records"


class HistoryCounter:
    """Updating label of one history table, skipping no-op repaints."""

    def __init__(self, selector: str, name: str) -> None:
        self._selector = selector
        self._name = name
        self._text = ""

    def update(self, lookup: Callable[[str], Any], shown: int, total: int) -> None:
        """Set the label from the current row counts.

        ``lookup`` resolves the widget (``screen.query_one``); a missing label is not an
        error — the tab can be unmounted while rows are still arriving.
        """
        text = count_text(shown, total)
        if text == self._text:
            return
        try:
            label = lookup(self._selector)
        except Exception as exc:  # noqa: BLE001 - widget lookup failure only
            # The counter lags behind the rows: "Showing N of M" shows the previous page.
            logger.debug("proxy: %s counter not found: %s", self._name, exc)
            return
        self._text = text
        label.update(text)


def page_window(oldest_offset: int, page_size: int) -> tuple[int, int]:
    """`(offset, limit)` of the next older page.

    Both tables load "one page above what is already shown": the window ends at the
    oldest loaded row and never goes below zero.
    """
    offset = max(oldest_offset - page_size, 0)
    return offset, oldest_offset - offset


def merge_older(rows: list, older_newest_first: list) -> list:
    """Put an older page in front of the loaded rows (oldest-first for the table).

    The service returns newest-first; the table is oldest-first, hence the reversal.
    """
    return list(reversed(older_newest_first)) + rows


def pick_row(rows: list, row_index: int) -> dict | None:
    """The row at ``row_index``, or ``None`` when the index is stale.

    Highlight events can arrive after a reload shortened the table, so the bounds check
    belongs here rather than in every caller.
    """
    if 0 <= row_index < len(rows):
        row = rows[row_index]
        if isinstance(row, dict):
            return row
    return None

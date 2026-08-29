"""Result-table helpers for the Intruder screen (Этап 6, intruder_results).

Pure predicate for filtering an IntruderResult row by status/length — shared
by the full redraw and the live-append paths so filter behavior stays in one
place.
"""

from __future__ import annotations

# Minimal structural dependency, kept duck-typed so the predicate is testable
# with any object exposing response_status / response_length.

_UNSET = object()


def matches_result_filters(
    result,
    status: str | None = None,
    len_gt: int | None = None,
    len_lt: int | None = None,
) -> bool:
    """Whether *result* passes the Intruder result-bar filters.

    status  — if set, the row's response_status string must equal it.
    len_gt  — if set, response_length must be strictly greater than it.
    len_lt  — if set, response_length must be strictly less than it.
    """
    if status and str(result.response_status) != status:
        return False
    length = result.response_length or 0
    if len_gt is not None and length <= len_gt:
        return False
    if len_lt is not None and length >= len_lt:
        return False
    return True

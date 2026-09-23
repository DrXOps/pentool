"""Result-table helpers for the Intruder screen (Этап 6, intruder_results).

Pure predicate for filtering an IntruderResult row by status/length — shared
by the full redraw and the live-append paths so filter behavior stays in one
place.
"""

from __future__ import annotations

import re

# Minimal structural dependency, kept duck-typed so the predicates are
# testable with any object exposing response_status / response_length /
# payload_values.

_UNSET = object()


def matches_grep(
    result,
    patterns: list[str] | None = None,
) -> bool:
    """Check if result matches any grep pattern (shared by highlight + filter)."""
    if not patterns:
        return False
    text = (
        f"{result.response_status} {result.response_length} "
        f"{' '.join(result.payload_values)}"
    )
    for pat in patterns:
        try:
            if re.search(pat, text, re.IGNORECASE):
                return True
        except re.error:
            continue
    return False


def matches_result_filters(
    result,
    status: str | None = None,
    len_gt: int | None = None,
    len_lt: int | None = None,
    grep_patterns: list[str] | None = None,
    grep_only_match: bool = False,
) -> bool:
    """Filter Intruder results by status, length range, and grep patterns."""
    if status and str(result.response_status) != status:
        return False
    length = result.response_length or 0
    if len_gt is not None and length <= len_gt:
        return False
    if len_lt is not None and length >= len_lt:
        return False
    if grep_only_match and grep_patterns and not matches_grep(result, grep_patterns):
        return False
    return True

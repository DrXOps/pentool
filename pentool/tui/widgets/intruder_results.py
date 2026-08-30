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
    """Whether *result* matches any of *patterns* on its status/length/payloads.

    Shared by the live row-highlight (which only colors the row) and the
    "Only matches" filter (which drops non-matching rows), so the grep hit-test
    lives in one place. Case-insensitive regex; a malformed pattern is skipped.

    Returns False when *patterns* is empty/None — nothing to grep for.
    """
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
    """Whether *result* passes the Intruder result-bar filters.

    status  — if set, the row's response_status string must equal it.
    len_gt  — if set, response_length must be strictly greater than it.
    len_lt  — if set, response_length must be strictly less than it.
    grep_patterns   — active Grep-Match patterns (may be None).
    grep_only_match — when True AND grep_patterns set, keep only rows that
                      actually match a grep pattern (the "Only matches"
                      toggle in the filter bar).
    """
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

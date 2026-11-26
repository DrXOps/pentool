"""Rendering the Intruder results table: rows, filtering and the Arrow rebuild.

Extracted from `IntruderScreen` (docs/audit/2026-11-21-tui-report.md, step 5): the same "results →
display rows → Arrow table" block was written twice in the screen (`_rebuild_table_data`
and `_apply_and_display`), each with its own loop over grep-extract patterns, and the
row mapping lived next to the tab machinery. The screen keeps only the DOM calls.

Everything here is pure: given results and the tab's filter settings it returns data.
"""

from __future__ import annotations

import re
from typing import Any, Iterable, Protocol

from pentool.core.logging import get_logger

logger = get_logger(__name__)


class _ResultLike(Protocol):
    request_number: int
    payload_values: list[str]
    response_status: int | None
    response_length: int | None
    response_time_ms: int | None
    error: str | None
    request_raw: str | None


class _FilterSpecLike(Protocol):
    is_empty: bool

    def apply(self, rows: list[dict]) -> list[dict]: ...


def extract_grep_value(result: _ResultLike, patterns: Iterable[str] | None) -> str:
    """First capture group (or full match) of the first pattern that hits, max 30 chars."""
    for pattern in patterns or ():
        try:
            match = re.search(pattern, result.request_raw or "")
        except re.error as exc:
            # A bad user pattern must not break the whole table rebuild.
            logger.debug("intruder: extract pattern %r invalid: %s", pattern, exc)
            continue
        if match:
            return (match.group(1) if match.lastindex else match.group(0))[:30]
    return ""


def row_from_result(result: _ResultLike) -> list[str]:
    """One display row; payloads are joined and shortened so the column stays readable."""
    payloads = " | ".join(result.payload_values)
    if len(payloads) > 40:
        payloads = payloads[:37] + "…"
    return [
        str(result.request_number),
        payloads,
        str(result.response_status or "-"),
        str(result.response_length or "-"),
        str(result.response_time_ms or "-"),
        result.error or "",
    ]


def result_is_visible(
    result: _ResultLike,
    *,
    filter_spec: _FilterSpecLike | None,
    grep_only_match: bool,
    grep_patterns: list[str] | None,
) -> bool:
    """Apply the tab's table filter and the "grep only" mode to one result."""
    row = {
        "status": str(result.response_status),
        "length": result.response_length or 0,
        "payload": " ".join(result.payload_values),
    }
    if filter_spec is not None and not filter_spec.is_empty:
        if filter_spec.apply([row]) != [row]:
            return False
    if grep_only_match and grep_patterns:
        text = f"{result.response_status} {result.response_length} {' '.join(result.payload_values)}"
        return any(re.search(pattern, text, re.IGNORECASE) for pattern in grep_patterns)
    return True


def build_results_arrow(
    results: list[Any],
    *,
    column_names: list[str],
    extract_patterns: list[str] | None = None,
) -> Any:
    """Arrow table for a list of results, adding an "Extract" column when needed.

    Returns ``None`` for an empty list: the caller then just clears the table, which is
    what both call sites used to do with their own branch.
    """
    if not results:
        return None
    import pyarrow as pa

    columns = list(column_names)
    if extract_patterns:
        columns = columns + ["Extract"]
    rows = []
    for result in results:
        row = row_from_result(result)
        if extract_patterns:
            row.append(extract_grep_value(result, extract_patterns))
        rows.append(row)
    data = {name: pa.array([row[index] for row in rows], type=pa.string()) for index, name in enumerate(columns)}
    return pa.table(data)

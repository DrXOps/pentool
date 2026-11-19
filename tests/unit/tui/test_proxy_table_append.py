"""Proxy history rows must actually appear in the table (T-020).

In the log (2026-11-19) every new packet produced:

    ArrowBackendDataTable.add_rows failed: Expected bytes, got a 'int' object
    PROXY SCREEN: _flush_pending_rows: add_rows crashed

Cause: the table was seeded with ``_make_empty_arrow(columns)``, which declares
**every** column as ``string``. The first incremental append carried ints for
``ID`` and ``Size`` → pyarrow raised, rows were dropped, and the old fallback
rebuilt the table with all-string columns (so IDs silently became text).

These tests pin both halves: a typed seed accepts numbers, and a schema mismatch
is coerced instead of losing the row.
"""

from __future__ import annotations

import pyarrow as pa
import pytest

from pentool.tui.widgets.data_table import ArrowBackendDataTable
from pentool.tui.widgets.proxy_helpers import make_empty_table, row_to_record


def _table(initial: pa.Table | None, columns: list[str] | None = None) -> ArrowBackendDataTable:
    return ArrowBackendDataTable(columns=columns or ["ID", "Host"], initial_table=initial)


def test_typed_seed_accepts_integer_columns() -> None:
    table = _table(make_empty_table(), columns=["ID", "Host", "Method", "URL", "Status", "Size", "Time"])

    row = row_to_record(
        {
            "id": 7,
            "host": "example.com",
            "method": "GET",
            "url": "http://example.com/",
            "status_code": 200,
            "length": 1234,
            "timestamp": 1_700_000_000,
        }
    )
    table.add_rows([row])  # must not raise

    assert table.backend.row_count == 1
    assert table.backend.get_cell_at(0, 0) == 7, "ID должен остаться числом"


def test_all_string_schema_is_coerced_not_dropped() -> None:
    """Legacy all-string seed: numbers are coerced, the row is not dropped."""
    table = ArrowBackendDataTable(columns=["ID", "Host"])
    table.add_rows([(5, "example.com")])

    assert table.backend.row_count == 1
    assert str(table.backend.get_cell_at(0, 0)) == "5"


def test_coercion_keeps_previous_rows() -> None:
    table = _table(make_empty_table(), columns=["ID", "Host", "Method", "URL", "Status", "Size", "Time"])
    first = row_to_record(
        {"id": 1, "host": "a.example", "method": "GET", "url": "/a", "status_code": 200, "length": 10}
    )
    table.add_rows([first])

    # a "bad" row (a number inside a string column) must not break the table
    table.add_rows([(2, 42, "POST", "/b", 201, 20, "-")])

    assert table.backend.row_count == 2
    assert table.backend.get_cell_at(1, 0) == 2


@pytest.mark.parametrize(
    ("value", "expected"),
    [("200", 200), ("-", None), ("", None), (None, None), (201, 201)],
)
def test_int_coercion_variants(value, expected) -> None:
    from pentool.tui.widgets.data_table import _coerce_value

    assert _coerce_value(value, pa.int64()) == expected

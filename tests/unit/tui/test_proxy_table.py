"""Unit tests for proxy request-table Arrow builders (Этап 6, proxy_table).

Extracted from ProxyScreen; these helpers are pure and testable in isolation.
"""

from __future__ import annotations

import pyarrow as pa
from datetime import datetime, timezone

from pentool.tui.widgets.proxy_table import COL_NAMES, rows_to_arrow, row_to_record


def _row(**overrides):
    base = {
        "id": 1,
        "url": "http://example.com/api",
        "host": "example.com",
        "method": "GET",
        "status_code": 200,
        "length": 42,
        "timestamp": datetime(2026, 8, 30, 12, 34, 56, tzinfo=timezone.utc).timestamp(),
    }
    base.update(overrides)
    return base


class TestRowToRecord:
    def test_basic_fields(self):
        r = row_to_record(_row())
        # (id, host, method, url, status, size, time)
        assert r[0] == 1
        assert r[1] == "example.com"      # host, no dot/comment pretext
        assert r[2] == "GET"
        assert r[3] == "http://example.com/api"
        assert r[4] == "200"
        assert r[5] == "42"
        assert isinstance(r[6], str) and ":" in r[6]  # HH:MM:SS

    def test_comment_marker_prefixes_host(self):
        r = row_to_record(_row(comment=" note "))
        assert r[1].startswith("💬 ")

    def test_color_dot_prefixes_host(self):
        r = row_to_record(_row(color="green"))
        assert r[1].startswith("🟢 ")

    def test_missing_fields_render_dash(self):
        r = row_to_record(_row(status_code=None, length=None, timestamp=None))
        assert r[4] == "-"
        assert r[5] == "-"
        assert r[6] == "-"

    def test_none_ts_renders_dash(self):
        r = row_to_record(_row(timestamp=None))
        assert r[6] == "-"


class TestRowsToArrow:
    def test_empty_returns_table_with_columns(self):
        tbl = rows_to_arrow([])
        assert isinstance(tbl, pa.Table)
        assert list(tbl.column_names) == COL_NAMES

    def test_one_row(self):
        tbl = rows_to_arrow([_row(id=7)])
        assert tbl.num_rows == 1
        assert tbl.column("ID").to_pylist()[0] == 7

    def test_multiple_rows_preserve_order(self):
        tbl = rows_to_arrow([_row(id=1), _row(id=2)])
        assert tbl.column("ID").to_pylist() == [1, 2]


class TestColNames:
    def test_order_is_stable(self):
        assert COL_NAMES == ["ID", "Host", "Method", "URL", "Status", "Size", "Time"]

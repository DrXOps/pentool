"""Unit tests for SortableTableMixin._sort_table_sql (SQL sorting).

Verifies that _sort_table_sql:
- calls reload_cb with the correct order_by/order_dir
- updates _sort_col / _sort_reverse
- a click on the same column toggles the direction
- falls back to buffer_sort when the column is not in order_by_map
"""

from __future__ import annotations

import asyncio
from unittest.mock import MagicMock

import pytest
from textual_fastdatatable import DataTable

from pentool.tui.widgets.data_table_mixins import SortableTableMixin

# ── Helpers ──────────────────────────────────────────────────────────────────


class _MinimalHost:
    """Minimal stub for a screen that uses SortableTableMixin."""

    def __init__(self) -> None:
        self._sort_col: int | None = None
        self._sort_reverse: bool = False
        self._last_reload: tuple | None = None
        self._sort_table_fallback_called = False

    def run_worker(self, coro) -> None:
        """Stub for run_worker — runs the coroutine synchronously."""
        import asyncio

        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            asyncio.run(coro)
            return
        # Already inside the event loop — create a task and wait for it
        loop.create_task(self._drain(coro))

    async def _drain(self, coro) -> None:
        await coro
        await asyncio.sleep(0)  # give other tasks a chance  # give other tasks a chance

    def _sort_table(self, event, col_names, **kwargs) -> None:
        """Stub for _sort_table — records that the fallback was called."""
        self._sort_table_fallback_called = True
        super()._sort_table(event, col_names, **kwargs)


class _Host(_MinimalHost, SortableTableMixin):
    """Full-fledged host: the mixin plus a minimal stub."""

    pass


def _make_event(column_index: int, table_id: str = "request-list") -> MagicMock:
    """Create a HeaderSelected mock with the given column_index."""
    event = MagicMock(spec=DataTable.HeaderSelected)
    event.column_index = column_index
    table = MagicMock(spec=DataTable)
    table.id = table_id
    event.data_table = table
    return event


# ── Tests for _sort_table_sql ────────────────────────────────────────────────


class TestSortTableSql:
    COL_NAMES = ["ID", "Host", "Method", "Status", "Size", "Time"]
    ORDER_BY_MAP = {
        "ID": "id",
        "Host": "host",
        "Method": "method",
        "Status": "status_code",
        "Size": "length",
        "Time": "timestamp",
    }

    def _reload_cb(self, order_by: str, order_dir: str):
        """Return a coroutine that stores the parameters in _last_reload."""

        async def _inner(host: _Host):
            host._last_reload = (order_by, order_dir)

        return _inner(self._host)

    def _call_sort(self, host: _Host, col_idx: int) -> None:
        """Call _sort_table_sql with the settings of the test class."""
        event = _make_event(column_index=col_idx)
        host._sort_table_sql(event, self.COL_NAMES, self.ORDER_BY_MAP, self._reload_cb)

    @pytest.mark.asyncio
    async def test_calls_reload_cb_with_correct_params(self):
        host = _Host()
        self._host = host
        self._call_sort(host, 1)  # Host
        await asyncio.sleep(0)
        assert host._last_reload == ("host", "asc")

    def test_sets_sort_state_on_first_click(self):
        host = _Host()
        self._host = host
        self._call_sort(host, 0)  # ID
        assert host._sort_col == 0
        assert host._sort_reverse is False

    @pytest.mark.asyncio
    async def test_same_column_toggles_direction(self):
        host = _Host()
        self._host = host
        self._call_sort(host, 2)  # Method, first
        await asyncio.sleep(0)
        assert host._last_reload == ("method", "asc")

        self._call_sort(host, 2)  # Method, second (toggle)
        await asyncio.sleep(0)
        assert host._last_reload == ("method", "desc")

    @pytest.mark.asyncio
    async def test_different_column_resets_direction(self):
        host = _Host()
        self._host = host
        self._call_sort(host, 0)  # ID first
        await asyncio.sleep(0)
        assert host._last_reload == ("id", "asc")

        self._call_sort(host, 3)  # Status second
        await asyncio.sleep(0)
        assert host._last_reload == ("status_code", "asc")

    def test_unknown_column_falls_back_to_sort_table(self):
        host = _Host()
        self._host = host
        col_names = ["ID", "ColX"]
        order_by_map = {"ID": "id"}
        event = _make_event(column_index=1)
        host._sort_table_sql(event, col_names, order_by_map, self._reload_cb)
        assert host._sort_table_fallback_called is True

    @pytest.mark.asyncio
    async def test_ordered_columns_stress_asc_desc(self):
        host = _Host()
        self._host = host
        self._call_sort(host, 4)  # Size, asc
        await asyncio.sleep(0)
        assert host._last_reload == ("length", "asc")

        self._call_sort(host, 4)  # Size, desc
        await asyncio.sleep(0)
        assert host._last_reload == ("length", "desc")

        self._call_sort(host, 4)  # Size, asc again
        await asyncio.sleep(0)
        assert host._last_reload == ("length", "asc")

"""Mixins for screens with a DataTable: sorting.

All project tables inherit from ArrowBackendDataTable and have safe_sort.
The mixin only manages the sorting state and the arrows.

Supports two modes:
- buffer_sort (default) — via in-memory DataTable.sort() (safe_sort)
- sql_sort — via ORDER BY in a storage SQL query (order_by_map is passed in)

Usage::

    class MyScreen(Screen, SortableTableMixin):
        _COL_NAMES = ["ID", "Host", "Method"]

        def on_data_table_header_selected(self, event):
            self._sort_table(event, self._COL_NAMES)
"""

from __future__ import annotations

import logging

from textual_fastdatatable import DataTable

logger = logging.getLogger(__name__)


class SortableTableMixin:
    """Mixin for a screen with a sortable table.

    All tables have safe_sort (ArrowBackendDataTable). The mixin manages
    _sort_col / _sort_reverse and the ▲▼ arrows.

    For SQL sorting (ORDER BY) set order_by_map — a dict
    {column_name: db_field_name}. It is passed via _sort_table_sql().
    """

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._sort_col: int | None = None
        self._sort_reverse: bool = False

    def _sort_table(
        self,
        event: DataTable.HeaderSelected,
        col_names: list[str],
    ) -> None:
        """Sorting via safe_sort (in-memory buffer).

        Args:
            event: HeaderSelected from DataTable
            col_names: column names for the arrows
        """
        idx = event.column_index
        self._sort_reverse = (self._sort_col == idx) and not self._sort_reverse
        self._sort_col = idx

        table = event.data_table
        col_name = col_names[idx] if idx < len(col_names) else ""
        if not col_name:
            return

        if hasattr(table, "safe_sort"):
            table.safe_sort(col_name, "descending" if self._sort_reverse else "ascending")

        self._update_sort_arrows(table, col_names)

    def _sort_table_sql(
        self,
        event: DataTable.HeaderSelected,
        col_names: list[str],
        order_by_map: dict[str, str],
        reload_cb: callable,  # noqa: ANN201
    ) -> None:
        """SQL sorting: reloads the table via ORDER BY from the DB.

        Args:
            event: HeaderSelected from DataTable
            col_names: column names for the arrows
            order_by_map: {column_name: SQL field name}
            reload_cb: async callable(order_by, order_dir) → reload
        """
        idx = event.column_index
        col_name = col_names[idx] if idx < len(col_names) else ""
        if not col_name or col_name not in order_by_map:
            self._sort_table(event, col_names)
            return

        self._sort_reverse = (self._sort_col == idx) and not self._sort_reverse
        self._sort_col = idx

        order_col = order_by_map[col_name]
        order_dir = "desc" if self._sort_reverse else "asc"

        # Reload from the DB with SQL sorting
        self.run_worker(reload_cb(order_by=order_col, order_dir=order_dir))

        # The reload swaps rows, not columns, so the arrows can be set right away.
        # Passing the real table matters: `None` used to reach _update_sort_arrows and
        # the resulting AttributeError was swallowed by a broad except — the arrow never
        # appeared on the SQL-sorted tables (proxy history, intruder results).
        self._update_sort_arrows(event.data_table, col_names)

    def _update_sort_arrows(
        self,
        table: DataTable | None,
        col_names: list[str],
    ) -> None:
        """Show the ▲/▼ arrow on the active sort column."""
        if table is None:
            logger.debug("_update_sort_arrows: no table to update")
            return
        try:
            for i, name in enumerate(col_names):
                col = table.ordered_columns[i]
                base = name.rstrip(" ▲▼")
                if i == self._sort_col:
                    arrow = "▼" if self._sort_reverse else "▲"
                    col.label = f"{base} {arrow}"
                else:
                    col.label = base
            table.refresh()
        except (AttributeError, IndexError) as exc:
            # A table without ordered_columns (a stub in a test) must not break sorting.
            logger.debug("_update_sort_arrows: %s", exc)

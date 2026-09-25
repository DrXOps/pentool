"""Миксины для экранов с DataTable: сортировка.

Все таблицы проекта наследуют ArrowBackendDataTable и имеют safe_sort.
Миксин только управляет состоянием сортировки и стрелками.

Использование::

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
    """Миксин для экрана с сортируемой таблицей.

    Все таблицы имеют safe_sort (ArrowBackendDataTable). Миксин управляет
    _sort_col / _sort_reverse и стрелками ▲▼. Сортировка через safe_sort.
    """

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._sort_col: int | None = None
        self._sort_reverse: bool = False

    def _sort_table(
        self,
        event: DataTable.HeaderSelected,
        col_names: list[str],
        numeric_sort: bool = False,
        numeric_sort_key: callable | None = None,  # noqa: ANN201
    ) -> None:
        """Сортировка через safe_sort + обновление стрелок.

        Args:
            event: HeaderSelected от DataTable
            col_names: имена колонок для стрелок
            numeric_sort: не используется (все таблицы через safe_sort)
            numeric_sort_key: не используется (reserved)
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

    def _update_sort_arrows(
        self,
        table: DataTable,
        col_names: list[str],
    ) -> None:
        """Показать стрелку ▲/▼ на активной колонке сортировки."""
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
        except Exception as exc:
            logger.debug("_update_sort_arrows: %s", exc)
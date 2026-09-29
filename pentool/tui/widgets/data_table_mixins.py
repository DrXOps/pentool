"""Миксины для экранов с DataTable: сортировка.

Все таблицы проекта наследуют ArrowBackendDataTable и имеют safe_sort.
Миксин только управляет состоянием сортировки и стрелками.

Поддерживает два режима:
- buffer_sort (default) — через in-memory DataTable.sort() (safe_sort)
- sql_sort — через ORDER BY в SQL-запросе к хранилищу (передаётся order_by_map)

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
    _sort_col / _sort_reverse и стрелками ▲▼.

    Для SQL-сортировки (ORDER BY) задай order_by_map — словарь
    {имя_колонки: имя_поля_в_БД}. Передаётся через _sort_table_sql().
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
        """Сортировка через safe_sort (in-memory буфер).

        Args:
            event: HeaderSelected от DataTable
            col_names: имена колонок для стрелок
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
        """SQL-сортировка: перегружает таблицу через ORDER BY из БД.

        Args:
            event: HeaderSelected от DataTable
            col_names: имена колонок для стрелок
            order_by_map: {имя_колонки: имя_поля_в_SQL}
            reload_cb: асинхронный callable(order_by, order_dir) → reload
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

        # Перезагружаем из БД с SQL-сортировкой
        self.run_worker(reload_cb(order_by=order_col, order_dir=order_dir))

        # Обновляем стрелки после перезагрузки
        self._update_sort_arrows(None, col_names)

    def _update_sort_arrows(
        self,
        table: DataTable | None,
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
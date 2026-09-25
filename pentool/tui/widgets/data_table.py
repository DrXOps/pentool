"""ArrowBackendDataTable — универсальный DataTable с ArrowBackend.

Объединяет повторяющийся паттерн ``ArrowBackend`` + ``DataTable``,
который дублируется в ProxyScreen (10 мест).

Использование::

    table = ArrowBackendDataTable(columns=["ID", "Host", "Method"])
    table.set_data(arrow_table)  # полностью перестроить
    table.add_rows(rows)         # инкрементально добавить
"""

from __future__ import annotations

from typing import Any

import pyarrow as pa
from rich.text import Text as RichText
from textual_fastdatatable import ArrowBackend, DataTable


def _make_empty_arrow(columns: list[str]) -> pa.Table:
    """Build an empty Arrow table with the given string columns."""
    cols: dict[str, pa.Array] = {}
    for c in columns:
        cols[c] = pa.array([], type=pa.string())
    return pa.table(cols)


class ArrowBackendDataTable(DataTable):
    """DataTable subclass that manages its own ArrowBackend.

    Wraps the ``table.backend = ArrowBackend(arrow)`` pattern so callers
    don't need to import ArrowBackend or pyarrow directly. No seeded rows,
    no magic — data is loaded exclusively via set_data() or add_rows().
    Pass column_widths and columns through kwargs to set header widths.
    """

    def __init__(
        self,
        columns: list[str] | None = None,
        *args: Any,
        **kwargs: Any,
    ) -> None:
        super().__init__(*args, **kwargs)
        self._columns = columns or []
        # Seed backend with empty Arrow so DataTable knows column names
        # and renders headers immediately (column_widths in kwargs sets
        # min column width via DataTable.__init__).
        if self._columns:
            self.backend = ArrowBackend(_make_empty_arrow(self._columns))

    def set_data(self, arrow: pa.Table) -> None:
        """Replace the entire table content with an Arrow table.

        Full cache reset as done in ProxyScreen._reload_table — required
        so DataTable picks up the new column schema and headers render.
        """
        try:
            self.backend = ArrowBackend(arrow)
            self._ordered_columns = None
            self._clear_caches()
            self._require_update_dimensions = True
            self.refresh()
        except Exception as exc:
            from pentool.core.logging import get_logger as _log
            _log().error("ArrowBackendDataTable.set_data failed: %s", exc)

    def add_rows(self, records: list[tuple]) -> None:
        """Add rows via the parent DataTable.add_rows."""
        try:
            result = super().add_rows(records)
            self.refresh()
            return result
        except Exception as exc:
            from pentool.core.logging import get_logger as _log
            _log().error("ArrowBackendDataTable.add_rows failed: %s", exc)
            if self._columns and records:
                typed = list(zip(*records)) if records else []
                data = {}
                for i, col in enumerate(self._columns):
                    data[col] = pa.array(typed[i] if i < len(typed) else [], type=pa.string())
                self.backend = ArrowBackend(pa.table(data))

    def clear_data(self) -> None:
        """Reset to an empty table (columns preserved)."""
        if self._columns:
            self.backend = ArrowBackend(_make_empty_arrow(self._columns))
        else:
            self.clear()
        self.refresh()

    def _get_cell_renderable(self, row_index, column_index, max_width):  # noqa: ANN201
        """Crash-guard: оборачивает заголовки колонок в Text().

        В textual_fastdatatable.DataTable._get_cell_renderable (строка 1832)
        для row_index == -1 вызывается text.plain на column label, который
        может быть str (после ArrowBackend rebuild). Оборачиваем в RichText
        чтобы .plain работал.
        """
        if row_index == -1:  # header row
            from textual_fastdatatable.format import truncate_to_first_line
            label = self.ordered_columns[column_index].label
            if isinstance(label, str):
                label = RichText(label)
            return truncate_to_first_line(label, max_width)
        return super()._get_cell_renderable(row_index, column_index, max_width)

    def _mouse_ready(self) -> bool:
        """Проверка: таблица смонтирована и имеет ненулевой размер."""
        try:
            region = self.region
            return region.width > 0 and region.height > 0
        except Exception:
            return False

    def safe_sort(self, col_name: str, direction: str = "ascending") -> bool:
        """Безопасная сортировка через родной DataTable.sort() с crash-guard.

        Проверяет готовность таблицы и вызывает sort(by=[(col, dir)]).
        Возвращает True при успехе, False при ошибке.
        """
        if not self._mouse_ready():
            return False
        try:
            self.sort(by=[(col_name, direction)])
            return True
        except Exception as exc:
            import logging
            logging.getLogger(__name__).warning("safe_sort failed: %s", exc)
            return False

    def add_column(self, name: str, at: int | None = None) -> None:
        if name in (self._columns or []):
            return
        self._columns.append(name) if at is None else self._columns.insert(at, name)
        self._rebuild_backend()

    def remove_column(self, name: str) -> None:
        if name not in (self._columns or []):
            return
        self._columns.remove(name)
        self._rebuild_backend()

    def _rebuild_backend(self) -> None:
        """Rebuild the Arrow backend, preserving existing row data."""
        if not self._columns:
            self.clear()
            return
        try:
            old = self.backend.arrow_data if hasattr(self.backend, "arrow_data") else None
            if old is not None and isinstance(old, pa.Table) and old.num_rows > 0:
                cols = {}
                for c in self._columns:
                    if c in old.column_names:
                        cols[c] = old.column(c)
                    else:
                        cols[c] = pa.nulls(old.num_rows, type=pa.string())
                new_arrow = pa.table(cols)
            else:
                new_arrow = _make_empty_arrow(self._columns)
            self.backend = ArrowBackend(new_arrow)
            self._clear_caches()
            self._require_update_dimensions = True
            self.refresh()
        except Exception as exc:
            from pentool.core.logging import get_logger as _log
            _log().error("ArrowBackendDataTable._rebuild_backend failed: %s", exc)
            self.backend = ArrowBackend(_make_empty_arrow(self._columns))

    @staticmethod
    def empty_arrow(columns: list[str]) -> pa.Table:
        return _make_empty_arrow(columns)
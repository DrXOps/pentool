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


def _make_seeded_arrow(columns: list[str]) -> pa.Table:
    """Build an Arrow table with one empty string row per column.

    textual_fastdatatable skips rendering column headers when the table
    is truly empty (row_count == 0), because all column widths are 0.
    A single row gives ArrowBackend enough information to calculate
    content_width and render headers immediately.
    """
    cols: dict[str, pa.Array] = {}
    for c in columns:
        cols[c] = pa.array([""], type=pa.string())
    return pa.table(cols)


class ArrowBackendDataTable(DataTable):
    """DataTable subclass that manages its own ArrowBackend.

    Wraps the ``table.backend = ArrowBackend(arrow)`` pattern so callers
    don't need to import ArrowBackend or pyarrow directly.
    """

    def __init__(
        self,
        columns: list[str] | None = None,
        *args: Any,
        **kwargs: Any,
    ) -> None:
        super().__init__(*args, **kwargs)
        self._columns = columns or []
        if self._columns:
            self.backend = ArrowBackend(_make_seeded_arrow(self._columns))

    def set_data(self, arrow: pa.Table) -> None:
        """Replace the entire table content with an Arrow table."""
        # Wrap in try-except: textual_fastdatatable can crash on render with
        # "'str' object has no attribute 'plain'" when ArrowBackend returns
        # StringScalar instead of Rich Text. Fall back to empty table.
        try:
            self.backend = ArrowBackend(arrow)
            self.refresh()
        except Exception as exc:
            from pentool.core.logging import get_logger as _log
            _log().error("ArrowBackendDataTable.set_data failed: %s", exc)
            self.backend = ArrowBackend(_make_seeded_arrow(self._columns))

    def add_rows(self, records: list[tuple]) -> None:
        """Add rows via the parent DataTable.add_rows.

        Wrapped in try-except: textual_fastdatatable crashes on render with
        "'str' object has no attribute 'plain'" when ArrowBackend returns
        StringScalar instead of Rich Text. Fall back to set_data.
        """
        try:
            result = super().add_rows(records)
            self.refresh()
            return result
        except Exception as exc:
            from pentool.core.logging import get_logger as _log
            _log().error("ArrowBackendDataTable.add_rows failed: %s", exc)
            # Convert records to Arrow and do a full set_data instead
            import pyarrow as pa
            cols = self._columns
            if cols:
                typed = list(zip(*records)) if records else []
                data = {}
                for i, col in enumerate(cols):
                    data[col] = pa.array(typed[i] if i < len(typed) else [], type=pa.string())
                self.backend = ArrowBackend(pa.table(data))

    def clear_data(self) -> None:
        """Reset to an empty table (columns preserved)."""
        if self._columns:
            self.backend = ArrowBackend(_make_seeded_arrow(self._columns))
        else:
            self.clear()

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

    @staticmethod
    def empty_arrow(columns: list[str]) -> pa.Table:
        """Create an empty Arrow table with the given string columns."""
        return _make_empty_arrow(columns)
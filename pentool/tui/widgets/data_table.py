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


def _make_seeded_arrow(columns: list[str], column_widths: list[int] | None = None) -> pa.Table:
    """Build an Arrow table with one empty string row per column.

    textual_fastdatatable skips rendering column headers when the table
    is truly empty (row_count == 0), because all column widths are 0.
    A single row gives ArrowBackend enough information to calculate
    content_width and render headers immediately.

    When column_widths is given, the placeholder cells use spaces to
    match the desired min width so headers render legibly.
    """
    cols: dict[str, pa.Array] = {}
    for i, c in enumerate(columns):
        w = (column_widths or [])[i] if column_widths and i < len(column_widths) else 0
        val = " " * w if w else ""
        cols[c] = pa.array([val], type=pa.string())
    return pa.table(cols)


class ArrowBackendDataTable(DataTable):
    """DataTable subclass that manages its own ArrowBackend.

    Wraps the ``table.backend = ArrowBackend(arrow)`` pattern so callers
    don't need to import ArrowBackend or pyarrow directly.

    Column headers are visible even when the table is empty (uses a seeded
    Arrow table with one empty row internally — see _make_seeded_arrow).
    The seeded row is automatically removed when real data is added through
    add_rows().
    """

    def __init__(
        self,
        columns: list[str] | None = None,
        *args: Any,
        **kwargs: Any,
    ) -> None:
        # column_widths stays in kwargs so it reaches DataTable.__init__
        # where it sets min column content width — required for column
        # headers to render at all on an empty table.
        _col_widths: list[int] | None = kwargs.get("column_widths")
        super().__init__(*args, **kwargs)
        self._columns = columns or []
        self._seeded: bool = False
        if self._columns:
            self.backend = ArrowBackend(_make_seeded_arrow(self._columns, _col_widths))
            self._seeded = True

    def set_data(self, arrow: pa.Table) -> None:
        """Replace the entire table content with an Arrow table."""
        try:
            self.backend = ArrowBackend(arrow)
            self._seeded = False
            self.refresh()
        except Exception as exc:
            from pentool.core.logging import get_logger as _log
            _log().error("ArrowBackendDataTable.set_data failed: %s", exc)
            self.backend = ArrowBackend(_make_seeded_arrow(self._columns))
            self._seeded = True

    def add_rows(self, records: list[tuple]) -> None:
        """Add rows via the parent DataTable.add_rows.

        If the table currently holds only a seeded empty row (column headers
        placeholder), that row is silently dropped before adding the real
        records.
        """
        try:
            if self._seeded and records:
                self._seeded = False
                # Remove the seeded row before adding real data
                self.backend = ArrowBackend(_make_empty_arrow(self._columns))
                self._clear_caches()
                self._require_update_dimensions = True
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
                self._seeded = False

    def clear_data(self) -> None:
        """Reset to an empty table (columns preserved, headers visible)."""
        if self._columns:
            self.backend = ArrowBackend(_make_seeded_arrow(self._columns))
            self._seeded = True
        else:
            self.clear()
            self._seeded = False

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
        """Add a column to the table dynamically (rebuilds Arrow backend).

        Columns can only be added — never removed past the initial set
        (use remove_column for dynamically-added ones). The Arrow table
        is rebuilt preserving existing data with nulls for the new column.
        """
        if name in (self._columns or []):
            return
        self._columns.append(name) if at is None else self._columns.insert(at, name)
        self._rebuild_backend()

    def remove_column(self, name: str) -> None:
        """Remove a dynamically-added column (rebuilds Arrow backend)."""
        if name not in (self._columns or []):
            return
        self._columns.remove(name)
        self._rebuild_backend()

    def _rebuild_backend(self) -> None:
        """Rebuild the Arrow backend from scratch using the current _columns list."""
        if not self._columns:
            self.clear()
            return
        try:
            old = self.backend.arrow_data if hasattr(self.backend, "arrow_data") else None
            if old is not None and isinstance(old, pa.Table) and old.num_rows > 0:
                keeping_real_data = not self._seeded or old.num_rows > 1
                cols = {}
                for c in self._columns:
                    if c in old.column_names:
                        cols[c] = old.column(c)
                    else:
                        cols[c] = pa.nulls(old.num_rows, type=pa.string())
                new_arrow = pa.table(cols)
            else:
                new_arrow = _make_seeded_arrow(self._columns, self._col_widths)
                self._seeded = True
                keeping_real_data = False

            self.backend = ArrowBackend(new_arrow)
            self._clear_caches()
            self._require_update_dimensions = True
            self.refresh()
        except Exception as exc:
            from pentool.core.logging import get_logger as _log
            _log().error("ArrowBackendDataTable._rebuild_backend failed: %s", exc)
            self.backend = ArrowBackend(_make_seeded_arrow(self._columns))
            self._seeded = True

    @staticmethod
    def empty_arrow(columns: list[str]) -> pa.Table:
        """Create an empty Arrow table with the given string columns."""
        return _make_empty_arrow(columns)
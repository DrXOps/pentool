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
            self.backend = ArrowBackend(_make_empty_arrow(self._columns))

    def set_data(self, arrow: pa.Table) -> None:
        """Replace the entire table content with an Arrow table."""
        # Wrap in try-except: textual_fastdatatable can crash on render with
        # "'str' object has no attribute 'plain'" when ArrowBackend returns
        # StringScalar instead of Rich Text. Fall back to empty table.
        try:
            self.backend = ArrowBackend(arrow)
        except Exception as exc:
            from pentool.core.logging import get_logger as _log
            _log().error("ArrowBackendDataTable.set_data failed: %s", exc)
            self.backend = ArrowBackend(_make_empty_arrow(self._columns))

    def add_rows(self, records: list[tuple]) -> None:
        """Add rows via the parent DataTable.add_rows.

        Wrapped in try-except: textual_fastdatatable crashes on render with
        "'str' object has no attribute 'plain'" when ArrowBackend returns
        StringScalar instead of Rich Text. Fall back to set_data.
        """
        try:
            super().add_rows(records)
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
            self.backend = ArrowBackend(_make_empty_arrow(self._columns))
        else:
            self.clear()

    @staticmethod
    def empty_arrow(columns: list[str]) -> pa.Table:
        """Create an empty Arrow table with the given string columns."""
        return _make_empty_arrow(columns)
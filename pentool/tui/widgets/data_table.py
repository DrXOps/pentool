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

from pentool.core.logging import get_logger

logger = get_logger(__name__)


def _coerce_value(value: Any, target: pa.DataType) -> Any:
    """Coerce a value to the target column type; None stays None."""
    if value is None:
        return None
    if pa.types.is_integer(target):
        if isinstance(value, str):
            stripped = value.strip()
            if stripped in ("", "-"):
                return None
            try:
                return int(stripped)
            except ValueError:
                return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return None
    if pa.types.is_floating(target):
        try:
            return float(value)
        except (TypeError, ValueError):
            return None
    if pa.types.is_string(target) or pa.types.is_large_string(target):
        return str(value)
    return value


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
        initial_table: pa.Table | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(*args, **kwargs)
        self._columns = columns or []
        # Seed backend with empty Arrow so DataTable knows column names
        # and renders headers immediately (column_widths in kwargs sets
        # min column width via DataTable.__init__).
        #
        # `initial_table` matters: every column used to be declared `string`,
        # so the first `add_rows` carrying numbers (ID, Size) failed with
        # "Expected bytes, got a 'int' object" and proxy rows never appeared.
        # The caller passes an empty table with real types
        # (see proxy_helpers.make_empty_table).
        if initial_table is not None:
            self.backend = ArrowBackend(initial_table)
        elif self._columns:
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
        """Append rows, coercing values to the schema types BEFORE inserting.

        Why not "try first, repair later": when pyarrow fails on a type
        mismatch, the backend is left half-broken — `row_count` is 1 while
        `source_data` is empty, i.e. the previous rows are gone. So coercion
        happens up front.
        """
        try:
            prepared = self._coerce_records(records)
        except Exception:
            logger.error("table: rows not prepared for append", exc_info=True)
            prepared = records

        try:
            result = super().add_rows(prepared)
            self.refresh()
            return result
        except Exception as exc:
            logger.error("table: add_rows failed, retrying with schema coercion", exc_info=True)
            self._append_coerced(prepared, reason=exc)

    def _coerce_records(self, records: list[tuple]) -> list[tuple]:
        """Coerce every value to the current schema column type."""
        if not records:
            return records
        try:
            schema = self.backend.source_data.schema
        except Exception:
            logger.debug("table: schema unavailable, appending as-is", exc_info=True)
            return records

        types = [schema.field(index).type for index in range(len(schema))]
        prepared: list[tuple] = []
        for record in records:
            row = []
            for index, target in enumerate(types):
                value = record[index] if index < len(record) else None
                row.append(_coerce_value(value, target))
            prepared.append(tuple(row))
        return prepared

    def _append_coerced(self, records: list[tuple], *, reason: Exception | None = None) -> None:
        """Append rows, coercing values to the current schema types.

        The previous fallback declared EVERY column as string — numeric ID and
        Size became text, the table lost its types, and the next append failed
        again. Here the schema comes from the already loaded table and only
        mismatched values are coerced.
        """
        if not records:
            return
        try:
            current = self.backend.source_data
            schema = current.schema
        except Exception:
            logger.error("table: schema not available for coercion", exc_info=True)
            return

        columns: dict[str, list] = {name: [] for name in schema.names}
        for record in records:
            for index, name in enumerate(schema.names):
                value = record[index] if index < len(record) else None
                columns[name].append(_coerce_value(value, schema.field(index).type))

        try:
            addition = pa.table(
                {name: pa.array(values, type=schema.field(name).type) for name, values in columns.items()}
            )
            self.set_data(pa.concat_tables([current, addition]))
            logger.warning("table: rows appended after coercion (reason: %s)", reason)
        except Exception:
            logger.error("table: coercion failed — rows lost", exc_info=True)

    def clear_data(self) -> None:
        """Reset to an empty table (columns preserved)."""
        if self._columns:
            self.backend = ArrowBackend(_make_empty_arrow(self._columns))
        else:
            self.clear()
        self.refresh()

    def _get_cell_renderable(self, row_index, column_index):  # noqa: ANN201
        """Crash-guard: оборачивает заголовки колонок в Text().

        В textual_fastdatatable.DataTable._get_cell_renderable (строка 1785)
        для row_index == -1 возвращает label напрямую. Оборачиваем str в
        RichText чтобы .plain работал (после ArrowBackend rebuild).
        """
        if row_index == -1:  # header row
            label = self.ordered_columns[column_index].label
            if isinstance(label, str):
                label = RichText(label)
            return label
        return super()._get_cell_renderable(row_index, column_index)

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

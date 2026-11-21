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
from textual import events as _events
from textual_fastdatatable import ArrowBackend, DataTable
from textual_fastdatatable.column import CELL_X_PADDING

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
        # `DataTable.__init__` builds *and caches* the column list before we
        # install the backend above, so the cache holds an empty list and the
        # header row never renders until the first `set_data` (which drops the
        # cache). On an empty project — or on a screen mounted without a data
        # reload — that meant a table with no visible column names at all.
        if initial_table is not None or self._columns:
            self._ordered_columns = None
            self._require_update_dimensions = True

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
            self._schedule_fit()
        except Exception as exc:
            from pentool.core.logging import get_logger as _log

            _log().error("ArrowBackendDataTable.set_data failed: %s", exc)

    # ── Header affordance: sortable columns must look clickable ───────────

    #: Column under the mouse while it is over the header row, else None.
    _header_hover_column: int | None = None

    def watch_hover_coordinate(self, old_value: Any, new_value: Any) -> None:
        """Keep the mouse cursor honest over the header row.

        Sorting is bound to clicking a header (`HeaderSelected`), but nothing on
        screen said so: the cursor stayed an arrow everywhere, so a sortable
        header was indistinguishable from a label. Textual picks the cursor
        shape from the *widget* under the pointer (it walks `styles.pointer` up
        the DOM), so a per-cell pointer has to be switched here rather than in
        CSS. Row `-1` is the header row — that is also how the base class tells
        "hover over header" when it builds the cell tooltip.

        Lives in the shared table base on purpose: every module's table gets it,
        not just Proxy.
        """
        super().watch_hover_coordinate(old_value, new_value)
        over_header = getattr(new_value, "row", 0) == -1
        if over_header == (self._header_hover_column is not None):
            return  # nothing changed — don't touch styles on every pixel
        self._header_hover_column = getattr(new_value, "column", None) if over_header else None
        self.styles.pointer = "pointer" if over_header else "default"
        if self.is_mounted:
            self.screen.update_pointer_shape()

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
            # Rows change whether the vertical scrollbar is drawn, and that
            # takes two cells away from the columns.
            self._schedule_fit()
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

    # ── Column widths: flexible columns that share the leftover space ─────
    #
    # DataTable has no `fr` column widths (`Column.width` is a cell count), so
    # "let URL take the rest" has to be measured and pinned. The mechanism lives
    # here, in the shared base, and is off by default: a screen opts in by
    # declaring SPARE_COLUMNS, which keeps every module's table one attribute
    # away from the same behaviour instead of one more copy of the maths.

    #: Columns that share whatever the fixed ones leave over:
    #: ``{label: (min_width, max_width)}``. Exactly one entry may use ``None``
    #: as ``max_width`` — that column absorbs the remainder; the others are
    #: clamped so a long host name cannot squeeze everything else out.
    SPARE_COLUMNS: dict[str, tuple[int, int | None]] = {}

    #: Cell padding `Column.render_width` adds to a configured width.
    _CELL_X_PADDING = CELL_X_PADDING

    _fit_pending: bool = False

    def on_mount(self) -> None:
        self._schedule_fit()

    def on_resize(self, event: _events.Resize) -> None:
        self._schedule_fit()

    def _schedule_fit(self) -> None:
        """Coalesce fits: a burst of appends must not queue one fit each."""
        if self._fit_pending or not self.is_mounted or not self.SPARE_COLUMNS:
            return
        self._fit_pending = True
        self.call_after_refresh(self._run_fit)

    def _run_fit(self) -> None:
        self._fit_pending = False
        self.fit_columns()

    def fit_columns(self) -> None:
        """Share the table width between the fixed columns and SPARE_COLUMNS.

        Called on mount, on resize and after new data — the moments the table's
        width or its column set can change. When there is not even room for the
        minimums, the columns keep their minimums and the table scrolls
        horizontally, which is the honest fallback.
        """
        if not self.SPARE_COLUMNS:
            return
        columns = self.ordered_columns
        if not columns:
            return
        by_label = {str(col.label).strip(): index for index, col in enumerate(columns)}
        spare: list[tuple[int, int, int | None]] = [
            (by_label[label], low, high) for label, (low, high) in self.SPARE_COLUMNS.items() if label in by_label
        ]
        if not spare:
            return
        budget = self.content_size.width - self._row_label_column_width
        if budget <= 0:
            return
        spare_indexes = {index for index, _low, _high in spare}
        fixed = sum(col.render_width for index, col in enumerate(columns) if index not in spare_indexes)
        # Every spare column pays cell padding on top of its width.
        free = budget - fixed - self._CELL_X_PADDING * len(spare)

        absorbers = [item for item in spare if item[2] is None]
        clamped = [item for item in spare if item[2] is not None]
        widths: dict[int, int] = {}
        # The absorbing column's minimum is reserved first: it must never end up
        # below it just because the clamped columns grabbed the space.
        reserved = sum(low for _index, low, _high in absorbers)
        share = free - reserved
        share //= 2 * len(clamped) if clamped else 1
        for index, low, high in clamped:
            widths[index] = min(high, max(low, share))  # type: ignore[arg-type]
        taken = sum(widths.values())
        for index, low, _high in absorbers:
            widths[index] = max(low, (free - taken) // max(len(absorbers), 1))
        self._apply_widths(widths)

    def _apply_widths(self, widths: dict[int, int]) -> None:
        """Pin column widths and remember them for the next column rebuild.

        `ordered_columns` is rebuilt from `_column_widths` whenever the table is
        reloaded, so writing only the `Column` objects loses the fit on the next
        `set_data`.
        """
        columns = self.ordered_columns
        stored = self._column_widths
        changed = False
        for index, width in widths.items():
            column = columns[index]
            if column.width == width and not column.auto_width:
                continue
            column.width = width
            column.auto_width = False
            if stored is not None and index < len(stored):
                stored[index] = width
            changed = True
        if not changed:
            return
        self._require_update_dimensions = True
        self.refresh()

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

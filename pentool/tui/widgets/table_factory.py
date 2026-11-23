"""One factory for every data table in the TUI (T-029).

Seven `DataTable(...)` constructions repeated the same arguments with small drift:
hard-coded `column_widths` per screen, `max_column_content_width` only in Proxy,
flexible columns (`SPARE_COLUMNS`) only in Proxy. `make_table` keeps the shared
policy in one place so a new table cannot lose it silently:

* row cursor by default — these tables are read, not edited;
* zebra stripes, single-line header;
* the first column stays visible while scrolling (it is the row key everywhere);
* column content is capped so one long URL cannot squeeze the other columns out;
* flexible columns are declared by label and absorb the leftover width, so a
  table never needs a horizontal scrollbar.

Sorting is deliberately **not** here: it lives on the screen (`SortableTableMixin`
re-sorts and draws ▲/▼ in the header), and a widget cannot decide for a screen.
"""

from __future__ import annotations

import pyarrow as pa

from pentool.tui.widgets.data_table import ArrowBackendDataTable

#: Content cap for a single column: long URLs/bodies are truncated with an
#: ellipsis instead of pushing the other columns out of the row.
DEFAULT_MAX_COLUMN_CONTENT_WIDTH = 120


def make_table(
    columns: list[str],
    *,
    table_id: str,
    widths: list[int] | None = None,
    spare: dict[str, tuple[int, int | None]] | None = None,
    initial_table: pa.Table | None = None,
    cursor_type: str = "row",
    table_class: type[ArrowBackendDataTable] = ArrowBackendDataTable,
    classes: str | None = None,
) -> ArrowBackendDataTable:
    """Build a table with the project-wide defaults.

    Args:
        columns: header labels, in display order.
        table_id: DOM id (screens and tests look the table up by it).
        widths: fixed column widths; must match ``columns`` when given.
        spare: columns that share the leftover width, ``{label: (min, max)}``.
            ``None`` (the max) means "as wide as the rest allows".
        initial_table: pre-built Arrow table (empty skeleton by default).
        cursor_type: ``"row"`` (default) — tables here are read, not edited.
        table_class: subclass to instantiate — Proxy passes its own table, which
            adds the context menu and the "load older page" scroll message.
        classes: extra CSS classes for the widget.
    """
    kwargs: dict[str, object] = {
        "columns": columns,
        "id": table_id,
        "cursor_type": cursor_type,
        "zebra_stripes": True,
        "header_height": 1,
        "fixed_columns": 1 if widths else 0,
        "max_column_content_width": DEFAULT_MAX_COLUMN_CONTENT_WIDTH,
    }
    if widths is not None:
        kwargs["column_widths"] = widths
    if initial_table is not None:
        kwargs["initial_table"] = initial_table
    if classes is not None:
        kwargs["classes"] = classes

    table = table_class(**kwargs)  # type: ignore[arg-type]
    if spare:
        # `SPARE_COLUMNS` is a class attribute on ArrowBackendDataTable; setting it
        # per instance keeps the factory from generating widget subclasses at
        # runtime (Textual is picky about dynamically created classes).
        table.SPARE_COLUMNS = dict(spare)
    return table

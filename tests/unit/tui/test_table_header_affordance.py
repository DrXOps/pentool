"""Sortable table headers must look clickable.

Sorting is bound to clicking a column header (`DataTable.HeaderSelected`), but
before this the header looked like a plain label: no cursor change, and Textual's
own `$secondary 30%` hover tint sat on top of a `$primary` header, where it is
invisible. Hovering a header did nothing at all — reported by the user while
reviewing the cards UI — so the behaviour is pinned here. It lives in the shared
table base because every module's table is sortable, not just Proxy's history.
"""

from __future__ import annotations

from pathlib import Path

import pyarrow as pa
import pytest
from textual.app import App, ComposeResult
from textual_fastdatatable.data_table import Coordinate

from pentool.tui.widgets.data_table import ArrowBackendDataTable

_TUI = Path(__file__).resolve().parents[3] / "pentool" / "tui"
_APP_CSS = (_TUI / "app.tcss").read_text(encoding="utf-8")

_COLUMNS = ["ID", "Host", "URL"]


def _table_arrow(rows: int = 3) -> pa.Table:
    return pa.table(
        {
            "ID": pa.array(range(rows), type=pa.int64()),
            "Host": pa.array(["example.com"] * rows, type=pa.string()),
            "URL": pa.array(["/api"] * rows, type=pa.string()),
        }
    )


class _Host(App[None]):
    CSS = _APP_CSS

    def compose(self) -> ComposeResult:
        yield ArrowBackendDataTable(columns=_COLUMNS, id="table", cursor_type="row", column_widths=[4, 12, 12])


@pytest.mark.asyncio
async def test_pointer_over_header_and_default_over_rows() -> None:
    app = _Host()
    async with app.run_test(size=(80, 20)) as pilot:
        await pilot.pause()
        table = app.query_one("#table", ArrowBackendDataTable)
        table.set_data(_table_arrow())
        await pilot.pause()
        assert table.styles.pointer == "default"

        table.hover_coordinate = Coordinate(row=-1, column=1)  # header row
        await pilot.pause()
        assert table.styles.pointer == "pointer"
        assert table._header_hover_column == 1

        table.hover_coordinate = Coordinate(row=0, column=1)  # data row
        await pilot.pause()
        assert table.styles.pointer == "default"
        assert table._header_hover_column is None


def test_header_hover_is_visible_in_the_stylesheet() -> None:
    """The pointer is only half the affordance: the cell must light up too.

    Textual's default `$secondary 30%` on a `$primary` header is invisible, so
    the app stylesheet has to override it with something readable in both themes.
    """
    rule = next(
        (line for line in _APP_CSS.splitlines() if ".datatable--header-hover" in line),
        None,
    )
    assert rule is not None, "no .datatable--header-hover rule — hovering a sortable header shows nothing"
    block = _APP_CSS.split(rule, 1)[1].split("}", 1)[0]
    assert "$accent" in block

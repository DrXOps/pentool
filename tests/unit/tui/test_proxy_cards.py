"""Cards for the Proxy history: the request table has to fit inside its card.

Step 3 of the cards plan wraps the table and the "showing N of M" strip in a
card. Textual's DataTable only understands fixed column widths, so "URL → 1fr"
is implemented by :meth:`ProxyDataTable.fit_columns` — the guard here mounts the
table the way the Proxy screen does and checks that it never comes out wider
than the card, which is what used to put the right-hand columns behind a
horizontal scrollbar.
"""

from __future__ import annotations

import inspect
from pathlib import Path

import pyarrow as pa
import pytest
from textual.app import App, ComposeResult
from textual.containers import Vertical

from pentool.tui.screens.proxy.screen import ProxyScreen
from pentool.tui.widgets.proxy_data_table import ProxyDataTable
from pentool.tui.widgets.proxy_helpers import COL_NAMES, make_empty_table

_TUI = Path(__file__).resolve().parents[3] / "pentool" / "tui"
_APP_CSS = (_TUI / "app.tcss").read_text(encoding="utf-8")
_PROXY_CSS = (_TUI / "screens" / "proxy" / "screen.tcss").read_text(encoding="utf-8")

_ROW_COUNT = 30


def _rows(count: int = _ROW_COUNT) -> pa.Table:
    """A page of history: long hosts and URLs, so no column can be auto-sized."""
    return pa.table(
        {
            "ID": pa.array(range(count), type=pa.int64()),
            "Host": pa.array(["very-long-hostname.example.com"] * count, type=pa.string()),
            "Method": pa.array(["GET"] * count, type=pa.string()),
            "URL": pa.array(["/api/v1/some/really/long/path/that/keeps/going?with=query"] * count, type=pa.string()),
            "Status": pa.array(["200"] * count, type=pa.string()),
            "Size": pa.array([1234] * count, type=pa.int64()),
            "Time": pa.array(["12:00:00"] * count, type=pa.string()),
        }
    )


def _host_app(width: int) -> App:
    """The table inside the same container chain the screen builds."""

    class _Host(App):
        CSS = (
            _APP_CSS
            + _PROXY_CSS
            + """
        Screen { padding: 0; }
        #table-area { height: 1fr; width: 1fr; }
        #filter-bar { height: 1; }
        """
        )

        def compose(self) -> ComposeResult:
            with Vertical(id="table-area"):
                with Vertical(id="history-card", classes="card"):
                    yield ProxyDataTable(
                        columns=COL_NAMES,
                        initial_table=make_empty_table(),
                        id="request-list",
                        cursor_type="row",
                        zebra_stripes=True,
                        max_column_content_width=120,
                        column_widths=[5, 24, 8, 24, 6, 8, 8],
                    )

    app = _Host()
    app.size_hint = width  # type: ignore[attr-defined]
    return app


@pytest.mark.asyncio
@pytest.mark.parametrize("width", [120, 100, 90])
async def test_table_fits_the_card_without_a_horizontal_scrollbar(width: int) -> None:
    """The whole point of the flexible URL column: no sideways scrolling."""
    app = _host_app(width)
    async with app.run_test(size=(width, 24)) as pilot:
        await pilot.pause()
        table = app.query_one("#request-list", ProxyDataTable)
        table.set_data(_rows())
        await pilot.pause()
        await pilot.pause()
        overflow = table.virtual_size.width - table.content_size.width
        widths = {str(column.label).strip(): column.width for column in table.ordered_columns}
    assert overflow <= 0, f"table is {overflow} cells wider than the card at {width} columns: {widths}"
    host_low, host_high = ProxyDataTable.SPARE_COLUMNS["Host"]
    url_low, _ = ProxyDataTable.SPARE_COLUMNS["URL"]
    assert host_low <= widths["Host"] <= (host_high or host_low)
    assert widths["URL"] >= url_low


@pytest.mark.asyncio
async def test_wide_terminal_gives_the_url_column_the_extra_room() -> None:
    """Host is clamped, so the space a wide terminal adds goes to URL."""

    async def url_width(width: int) -> int:
        app = _host_app(width)
        async with app.run_test(size=(width, 24)) as pilot:
            await pilot.pause()
            table = app.query_one("#request-list", ProxyDataTable)
            table.set_data(_rows())
            await pilot.pause()
            await pilot.pause()
            widths = {str(column.label).strip(): column.width for column in table.ordered_columns}
        return widths["URL"]

    assert await url_width(120) > await url_width(90)


def test_card_class_is_defined_once_in_app_css() -> None:
    """`.card` has to exist or tools/check_tui_css.py rejects the class."""
    assert ".card {" in _APP_CSS
    assert ".card-host {" in _APP_CSS


def test_history_tabs_wrap_table_and_counter_in_a_card() -> None:
    """The card is built in compose, so check the structure the screen emits."""
    source = inspect.getsource(ProxyScreen._compose_history_tab) + inspect.getsource(ProxyScreen._compose_ws_tab)
    assert 'id="history-card", classes="card"' in source
    assert 'id="ws-history-card", classes="card"' in source
    assert "ProxyScreen #history-card," in _PROXY_CSS


def test_every_proxy_panel_block_is_a_card() -> None:
    """Step 4: Request/Response, Intercept and WS panels sit in the same card."""
    source = (
        inspect.getsource(ProxyScreen._compose_intercept_tab)
        + inspect.getsource(ProxyScreen._compose_history_tab)
        + inspect.getsource(ProxyScreen._compose_ws_tab)
    )
    expected = [
        'id="req-panel", classes="card"',
        'id="resp-panel", classes="card"',
        'id="intercept-panel",',  # the panel itself is the card, see below
        'id="intercept-sent-panel", classes="card"',
        'id="intercept-resp-panel", classes="card"',
        'id="ws-req-panel", classes="card"',
        'id="ws-resp-panel", classes="card"',
        'id="ws-msg-panel",',
    ]
    for marker in expected:
        assert marker in source, f"a Proxy panel block lost its card class: {marker}"
    # ContentPanels take the card on the widget itself, not on a wrapper.
    assert source.count('classes="card"') >= 7

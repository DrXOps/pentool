"""Intruder Grep-Extract column — now uses ArrowBackendDataTable.add_column/remove_column API.

The "Extract" result was written into rows without a declared column, which
Textual's DataTable rejects with 'More values provided than there are columns'.
Now ArrowBackendDataTable.add_column() dynamically rebuilds the Arrow backend
to include the extra column.
"""

from __future__ import annotations

import pytest
from textual.app import App, ComposeResult

from pentool.tui.widgets.data_table import ArrowBackendDataTable


class _Host(App[None]):
    def __init__(self):
        super().__init__()
        self.table = ArrowBackendDataTable(
            columns=["#", "Payload", "Status", "Length", "Time", "Error"]
        )

    def compose(self) -> ComposeResult:
        yield self.table


@pytest.mark.asyncio
async def test_extract_column_added_once_when_pattern_active():
    app = _Host()
    async with app.run_test() as pilot:
        await pilot.pause()
        app.table.add_column("Extract")
        await pilot.pause()
        names = app.table._columns
        assert "Extract" in names, "Extract column must be registered"
        # now a 7-cell row must be accepted (no ValueError)
        app.table.add_rows([("1", "p", "200", "100", "5", "", "extracted")])
        assert app.table.row_count > 0


@pytest.mark.asyncio
async def test_extract_column_not_added_without_pattern():
    app = _Host()
    async with app.run_test() as pilot:
        await pilot.pause()
        names = app.table._columns
        assert "Extract" not in names


@pytest.mark.asyncio
async def test_remove_extract_column_restores_plain():
    app = _Host()
    async with app.run_test() as pilot:
        await pilot.pause()
        app.table.add_column("Extract")
        await pilot.pause()
        assert "Extract" in app.table._columns

        # now remove it
        app.table.remove_column("Extract")
        await pilot.pause()
        assert "Extract" not in app.table._columns
        assert len(app.table._columns) == 6


@pytest.mark.asyncio
async def test_remove_extract_column_idempotent():
    app = _Host()
    async with app.run_test() as pilot:
        await pilot.pause()
        app.table.remove_column("Extract")  # no Extract column -> no-op
        await pilot.pause()
        assert "Extract" not in app.table._columns
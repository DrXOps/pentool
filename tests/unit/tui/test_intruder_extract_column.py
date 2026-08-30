"""Intruder Grep-Extract column (variant A fix).

The "Extract" result was written into rows without a declared column, which
Textual's DataTable rejects with 'More values provided than there are columns'
(silently swallowed -> the column never appeared). Now _ensure_extract_column
adds the column once when a grep-extract pattern is active.
"""

from __future__ import annotations

import asyncio
import types

import pytest
from textual.app import App, ComposeResult
from textual.widgets import DataTable

from pentool.tui.screens.intruder.screen import IntruderScreen


class _Host(App[None]):
    def __init__(self):
        super().__init__()
        self.table = DataTable()

    def compose(self) -> ComposeResult:
        for c in ["#", "Payload", "Status", "Length", "Time", "Error"]:
            self.table.add_column(c)
        yield self.table


async def _with_pattern(active):
    app = _Host()
    screen = object.__new__(IntruderScreen)
    screen._grep_extract_patterns = ["(user)"] if active else []
    async with app.run_test() as pilot:
        await pilot.pause()
        screen._ensure_extract_column(app.table)
        await pilot.pause()
        names = [str(c.label).strip() for c in app.table.ordered_columns]
        return app.table, names


@pytest.mark.asyncio
async def test_extract_column_added_once_when_pattern_active():
    table, names = await _with_pattern(active=True)
    assert any(n.startswith("Extract") for n in names), "Extract column must be registered"
    # now a 7-cell row must be accepted (no ValueError)
    table.add_row("1", "p", "200", "100", "5", "", "extracted")
    assert table.row_count == 1


@pytest.mark.asyncio
async def test_extract_column_not_added_without_pattern():
    table, names = await _with_pattern(active=False)
    assert not any(n.startswith("Extract") for n in names)


@pytest.mark.asyncio
async def test_remove_extract_column_restores_plain():
    app = _Host()
    screen = object.__new__(IntruderScreen)
    screen._grep_extract_patterns = ["(user)"]
    async with app.run_test() as pilot:
        await pilot.pause()
        screen._ensure_extract_column(app.table)
        await pilot.pause()
        assert any(str(c.label).strip().startswith("Extract") for c in app.table.ordered_columns)

        # now "clear" the pattern and remove the column
        screen._grep_extract_patterns = []
        screen._remove_extract_column(app.table)
        await pilot.pause()
        names = [str(c.label).strip() for c in app.table.ordered_columns]
        assert not any(n.startswith("Extract") for n in names)
        assert len(names) == 6


@pytest.mark.asyncio
async def test_remove_extract_column_idempotent():
    app = _Host()
    screen = object.__new__(IntruderScreen)
    screen._grep_extract_patterns = []
    async with app.run_test() as pilot:
        await pilot.pause()
        screen._remove_extract_column(app.table)  # no Extract column -> no-op
        await pilot.pause()
        names = [str(c.label).strip() for c in app.table.ordered_columns]
        assert not any(n.startswith("Extract") for n in names)

"""The Extract column follows the grep-extract pattern — both ways.

``on_intruder_filter_bar_changed`` compares the new pattern set against the
previous one and only touches the table's columns when the answer changes.
The "previous" value was read *after* ``tab.grep_extract_patterns`` had
already been cleared, so ``had_extract`` was hard-coded False: adding the
pattern grew the column, clearing the filter never removed it. The column
stayed in the table with nothing to fill it.

A test that only adds the pattern passes against that bug, so both directions
are checked here, in one session, on the same table.
"""

from __future__ import annotations

from textual.app import App, ComposeResult

from pentool.collections.filter_predicate import FilterOp, FilterPredicate, FilterSpec
from pentool.tui.screens.intruder.screen import IntruderScreen
from pentool.tui.widgets.intruder_filter_bar import IntruderFilterBar as _IntruderFilterBar


class _App(App):
    def compose(self) -> ComposeResult:
        yield IntruderScreen()


def _spec(*predicates: FilterPredicate) -> FilterSpec:
    return FilterSpec(predicates=list(predicates))


async def _settle(pilot, cycles: int = 4) -> None:
    for _ in range(cycles):
        await pilot.pause()


def _columns(screen: IntruderScreen) -> list[str]:
    table = screen._results_table()
    assert table is not None, "the active tab has no results table"
    return list(table._columns)


class TestExtractColumnFollowsThePattern:
    async def test_adding_then_clearing_the_pattern_adds_then_removes_the_column(self) -> None:
        app = _App()
        async with app.run_test(size=(200, 60)) as pilot:
            await _settle(pilot)
            screen = pilot.app.query_one(IntruderScreen)
            await _settle(pilot)
            assert "Extract" not in _columns(screen), "a fresh tab must not show an Extract column"

            screen.on_intruder_filter_bar_changed(
                _IntruderFilterBar.FilterChanged(_spec(FilterPredicate("grep_extract", FilterOp.EQ, r"token=(\w+)")))
            )
            await _settle(pilot)
            assert "Extract" in _columns(screen), "the pattern is set but the column was never added"
            assert screen._active_tab.grep_extract_patterns == [r"token=(\w+)"]

            screen.on_intruder_filter_bar_changed(_IntruderFilterBar.FilterChanged(_spec()))
            await _settle(pilot)
            assert screen._active_tab.grep_extract_patterns == []
            assert "Extract" not in _columns(screen), (
                "the pattern is gone but the Extract column stays — `had_extract` was read after "
                f"the state was cleared, so it was always False. Columns: {_columns(screen)}"
            )

    async def test_a_second_apply_does_not_duplicate_the_column(self) -> None:
        """``add_column`` early-returns on a duplicate; pin it so a rewrite keeps it."""
        app = _App()
        async with app.run_test(size=(200, 60)) as pilot:
            await _settle(pilot)
            screen = pilot.app.query_one(IntruderScreen)
            spec = _spec(FilterPredicate("grep_extract", FilterOp.EQ, "x"))
            for _ in range(3):
                screen.on_intruder_filter_bar_changed(_IntruderFilterBar.FilterChanged(spec))
            await _settle(pilot)
            assert _columns(screen).count("Extract") == 1

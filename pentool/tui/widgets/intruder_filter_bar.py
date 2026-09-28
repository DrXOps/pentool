"""IntruderFilterBar — фильтр результатов атак Intruder.

Одна строка: Status, Length, Grep, Extract, Only-matches, Apply/Reset/Clear.
"""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.widgets import Button, Input, Label

from pentool.collections.filter_predicate import (
    FilterOp,
    FilterPredicate,
    FilterSpec,
)
from pentool.tui.widgets.toolbar_button import ToolbarButton
from pentool.tui.widgets.filter_bar_widget import (
    FilterBarWidget,
)

_INTRUDER_CSS = """
IntruderFilterBar #filter-row {
    height: 1;
    layout: horizontal;
    padding: 0 1;
    background: $surface;
}
IntruderFilterBar .fb-label {
    width: auto;
    color: $text-muted;
    padding: 0 1 0 0;
}
IntruderFilterBar Input {
    height: 1;
    width: 8;
    border-left: solid $primary-darken-1;
    border-right: solid $primary-darken-1;
    background: $surface-lighten-1;
    padding: 0 1;
    color: $text;
}
IntruderFilterBar Input:focus {
    border-left: solid $primary;
    border-right: solid $primary;
    background: $surface-lighten-2;
}
IntruderFilterBar Button {
    height: 1;
    min-width: 6;
    background: $primary-darken-1;
    border: none;
    padding: 0 1;
}
IntruderFilterBar #btn-filter-reset,
IntruderFilterBar #btn-grep-clear {
    background: $panel;
}
IntruderFilterBar ToolbarButton {
    height: 1;
    width: auto;
    padding: 0 1;
    background: $panel;
    color: $text-muted;
    pointer: pointer;
}
IntruderFilterBar ToolbarButton:hover {
    background: $primary-darken-1;
}
IntruderFilterBar ToolbarButton.-active {
    color: $success;
    background: $success-darken-3;
}
"""


class IntruderFilterBar(FilterBarWidget):
    """Filter bar for Intruder results: status/length/grep — one row."""

    class FilterChanged(FilterBarWidget.FilterChanged):
        pass

    DEFAULT_CSS = _INTRUDER_CSS

    def compose(self) -> ComposeResult:
        with Horizontal(id="filter-row"):
            yield Label("Status:", classes="fb-label")
            yield Input(id="filter-status", placeholder="200", compact=True)
            yield Label("Length >", classes="fb-label")
            yield Input(id="filter-len-gt", placeholder="0", type="integer", compact=True)
            yield Label("<", classes="fb-label")
            yield Input(id="filter-len-lt", placeholder="∞", type="integer", compact=True)
            yield Label("Grep:", classes="fb-label")
            yield Input(id="grep-match-input", placeholder="regex", compact=True)
            yield Label("Extract:", classes="fb-label")
            yield Input(id="grep-extract-input", placeholder="regex", compact=True)
            yield ToolbarButton("○ Only matches", "grep-only-toggle")
            yield Button("Apply", id="btn-filter-apply")
            yield Button("Reset", id="btn-filter-reset")

    def collect(self) -> list[FilterPredicate]:
        predicates: list[FilterPredicate] = []
        status = self._read("#filter-status")
        if status:
            predicates.append(FilterPredicate("status", FilterOp.EQ, status))
        gt = self._read_int("#filter-len-gt")
        lt = self._read_int("#filter-len-lt")
        if gt is not None:
            predicates.append(FilterPredicate("length", FilterOp.GT, gt))
        if lt is not None:
            predicates.append(FilterPredicate("length", FilterOp.LT, lt))
        grep = self._read("#grep-match-input")
        if grep:
            predicates.append(FilterPredicate("grep_match", FilterOp.REGEX, grep))
        extract = self._read("#grep-extract-input")
        if extract:
            predicates.append(FilterPredicate("grep_extract", FilterOp.REGEX, extract))
        self._maybe_only_matches(predicates)
        return predicates

    def _read(self, sel: str) -> str:
        try:
            return self.query_one(sel, Input).value.strip()
        except Exception:
            return ""

    def _read_int(self, sel: str) -> int | None:
        try:
            v = self.query_one(sel, Input).value.strip()
            return int(v) if v else None
        except Exception:
            return None

    def _maybe_only_matches(self, predicates: list[FilterPredicate]) -> None:
        try:
            tb = self.query_one("#grep-only-toggle", ToolbarButton)
            if tb.has_class("active"):
                predicates.append(FilterPredicate("grep_only_match", FilterOp.EQ, True))
        except Exception:
            pass

    def _apply(self) -> None:
        self._emit(FilterSpec(predicates=self.collect()))

    def _reset(self) -> None:
        self.query_one("#filter-status", Input).value = ""
        self.query_one("#filter-len-gt", Input).value = ""
        self.query_one("#filter-len-lt", Input).value = ""
        self.query_one("#grep-match-input", Input).value = ""
        self.query_one("#grep-extract-input", Input).value = ""
        try:
            tb = self.query_one("#grep-only-toggle", ToolbarButton)
            tb.remove_class("active")
            tb.label = "○ Only matches"
        except Exception:
            pass
        self._emit(FilterSpec())

    def on_button_pressed(self, event: Button.Pressed) -> None:
        bid = event.button.id
        if bid == "btn-filter-apply":
            self._apply()
        elif bid == "btn-filter-reset":
            self._reset()

    def on_toolbar_button_pressed(self, event: ToolbarButton.Pressed) -> None:
        if event.button.id == "grep-only-toggle":
            toggle = not event.button.has_class("active")
            event.button.set_class(toggle, "active")
            event.button.label = "● Only matches" if toggle else "○ Only matches"
            self._apply()
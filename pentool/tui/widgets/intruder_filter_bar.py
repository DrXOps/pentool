"""IntruderFilterBar — фильтр результатов атак Intruder.

Два ряда: filter-row (status/length) и grep-row (grep/extract/only-matches).
"""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.widgets import Button, Input, Label

from pentool.collections.filter_predicate import (
    FilterField,
    FilterFieldType,
    FilterOp,
    FilterPredicate,
    FilterSpec,
)
from pentool.tui.widgets.filter_bar_widget import (
    FilterBarWidget,
    ToggleButton,
)

_INTRUDER_CSS = """
IntruderFilterBar {
    height: auto;
    layout: vertical;
}
IntruderFilterBar #filter-row,
IntruderFilterBar #grep-row {
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
    width: 10;
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
IntruderFilterBar #btn-filter-apply,
IntruderFilterBar #btn-grep-apply {
    height: 1;
    min-width: 7;
    background: $primary-darken-1;
    border: none;
    padding: 0 1;
}
IntruderFilterBar #btn-filter-reset,
IntruderFilterBar #btn-grep-clear {
    height: 1;
    min-width: 7;
    background: $panel;
    border: none;
    padding: 0 1;
}
IntruderFilterBar ToggleButton {
    height: 1;
    width: auto;
    padding: 0 1;
    background: $panel;
    color: $text-muted;
    pointer: pointer;
}
IntruderFilterBar ToggleButton:hover {
    background: $primary-darken-1;
}
IntruderFilterBar ToggleButton.-active {
    color: $success;
    background: $success-darken-3;
}
"""


class IntruderFilterBar(FilterBarWidget):
    """Filter bar for Intruder results: status/length range + grep section."""

    class FilterChanged(FilterBarWidget.FilterChanged):
        pass

    DEFAULT_CSS = _INTRUDER_CSS

    def configure(self) -> list[FilterField]:
        return [
            FilterField("filter-status", "Status:", FilterFieldType.TEXT, "status",
                        FilterOp.EQ, placeholder="200"),
            FilterField("filter-len-gt", "Length >", FilterFieldType.NUMBER, "length",
                        FilterOp.GT, placeholder="0"),
            FilterField("filter-len-lt", "<", FilterFieldType.NUMBER, "length",
                        FilterOp.LT, placeholder="∞"),
        ]

    def compose(self) -> ComposeResult:
        with Horizontal(id="filter-row"):
            yield Label("Status:", classes="fb-label")
            yield Input(id="filter-status", placeholder="e.g. 200")
            yield Label("Length >", classes="fb-label")
            yield Input(id="filter-len-gt", placeholder="0", type="integer")
            yield Label("<", classes="fb-label")
            yield Input(id="filter-len-lt", placeholder="∞", type="integer")
            yield Button("Apply", id="btn-filter-apply")
            yield Button("Reset", id="btn-filter-reset")
        with Horizontal(id="grep-row"):
            yield Label("Grep:", classes="fb-label")
            yield Input(id="grep-match-input", placeholder="regex — highlight rows")
            yield Label("Extract:", classes="fb-label")
            yield Input(id="grep-extract-input", placeholder="regex — extract value")
            yield ToggleButton("● Only matches", id="grep-only-toggle")
            yield Button("Apply", id="btn-grep-apply")
            yield Button("Clear", id="btn-grep-clear")

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
        try:
            toggle = self.query_one("#grep-only-toggle", ToggleButton)
            if toggle.is_active():
                predicates.append(FilterPredicate("grep_only_match", FilterOp.EQ, True))
        except Exception:
            pass
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

    def _apply(self) -> None:
        self._emit(FilterSpec(predicates=self.collect()))

    def _reset(self) -> None:
        self.query_one("#filter-status", Input).value = ""
        self.query_one("#filter-len-gt", Input).value = ""
        self.query_one("#filter-len-lt", Input).value = ""
        try:
            self.query_one("#grep-only-toggle", ToggleButton).reset()
        except Exception:
            pass
        self._emit(FilterSpec())

    def _clear_grep(self) -> None:
        self.query_one("#grep-match-input", Input).value = ""
        self.query_one("#grep-extract-input", Input).value = ""
        try:
            self.query_one("#grep-only-toggle", ToggleButton).reset()
        except Exception:
            pass
        self._emit(FilterSpec())

    def on_button_pressed(self, event: Button.Pressed) -> None:
        bid = event.button.id
        if bid in ("btn-filter-apply", "btn-grep-apply"):
            self._apply()
        elif bid == "btn-filter-reset":
            self._reset()
        elif bid == "btn-grep-clear":
            self._clear_grep()
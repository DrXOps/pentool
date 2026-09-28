"""IntruderFilterBar — фильтр результатов атак Intruder.

Заменяет старый IntruderFilterBar. Отличия:
- Унаследован от FilterBarWidget
- Grep-секция (grep-match, grep-extract, only-matches toggle) отдельно
- Immediate apply
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

_GREP_CSS = """
IntruderFilterBar {
    height: auto;
    layout: vertical;
}
IntruderFilterBar #results-filter-bar,
IntruderFilterBar #grep-bar {
    height: auto;
    layout: horizontal;
    padding: 0;
}
IntruderFilterBar Label {
    width: auto;
    margin: 0 1;
    color: $text-muted;
}
IntruderFilterBar Input {
    width: 12;
    margin: 0 1;
}
IntruderFilterBar Button {
    margin: 0 1;
}
"""


class IntruderFilterBar(FilterBarWidget):
    """Filter bar for Intruder results: status/length range + grep section."""

    class FilterChanged(FilterBarWidget.FilterChanged):
        pass

    DEFAULT_CSS = FilterBarWidget.DEFAULT_CSS + _GREP_CSS

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
        with Horizontal(id="results-filter-bar"):
            yield Label("Status:")
            yield Input(id="filter-status", placeholder="e.g. 200")
            yield Label("Length >")
            yield Input(id="filter-len-gt", placeholder="0", type="integer")
            yield Label("<")
            yield Input(id="filter-len-lt", placeholder="∞", type="integer")
            yield Button("Apply", id="btn-filter-apply")
            yield Button("Reset", id="btn-filter-reset")
        with Horizontal(id="grep-bar"):
            yield Label("Grep:")
            yield Input(id="grep-match-input", placeholder="regex — highlight rows")
            yield Label("Extract:")
            yield Input(id="grep-extract-input", placeholder="regex — extract value")
            yield ToggleButton("● Only matches", id="grep-only-toggle")
            yield Button("Apply", id="btn-grep-apply")
            yield Button("Clear", id="btn-grep-clear")

    def collect(self) -> list[FilterPredicate]:
        """Collect filter predicates + grep predicates."""
        predicates: list[FilterPredicate] = []

        # Status
        status = self._qs("#filter-status")
        if status:
            predicates.append(FilterPredicate("status", FilterOp.EQ, status))

        # Length range
        gt = self._qn("#filter-len-gt")
        lt = self._qn("#filter-len-lt")
        if gt is not None:
            predicates.append(FilterPredicate("length", FilterOp.GT, gt))
        if lt is not None:
            predicates.append(FilterPredicate("length", FilterOp.LT, lt))

        # Grep-match
        grep = self._qs("#grep-match-input")
        if grep:
            predicates.append(FilterPredicate("grep_match", FilterOp.REGEX, grep))

        # Grep-extract
        extract = self._qs("#grep-extract-input")
        if extract:
            predicates.append(FilterPredicate("grep_extract", FilterOp.REGEX, extract))

        # Grep-only-match флаг
        try:
            toggle = self.query_one("#grep-only-toggle", ToggleButton)
            if toggle.is_active():
                predicates.append(FilterPredicate("grep_only_match", FilterOp.EQ, True))
        except Exception:
            pass

        return predicates

    def _qs(self, sel: str) -> str:
        return self.query_one(sel, Input).value.strip()

    def _qn(self, sel: str) -> int | None:
        try:
            val = self.query_one(sel, Input).value.strip()
            return int(val) if val else None
        except Exception:
            return None

    # ── Handlers ───────────────────────────────────────────────────────────

    def on_button_pressed(self, event: Button.Pressed) -> None:
        bid = event.button.id
        if bid == "btn-filter-apply":
            self._apply()
        elif bid == "btn-filter-reset":
            self._reset()
        elif bid == "btn-grep-apply":
            self._apply()
        elif bid == "btn-grep-clear":
            self._clear_grep()

    def _clear_grep(self) -> None:
        self.query_one("#grep-match-input", Input).value = ""
        self.query_one("#grep-extract-input", Input).value = ""
        try:
            self.query_one("#grep-only-toggle", ToggleButton).reset()
        except Exception:
            pass
        self._emit(FilterSpec())

    def _reset(self) -> None:
        self.query_one("#filter-status", Input).value = ""
        self.query_one("#filter-len-gt", Input).value = ""
        self.query_one("#filter-len-lt", Input).value = ""
        try:
            self.query_one("#grep-only-toggle", ToggleButton).reset()
        except Exception:
            pass
        self._emit(FilterSpec())
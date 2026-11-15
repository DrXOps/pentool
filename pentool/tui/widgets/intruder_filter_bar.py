"""IntruderFilterBar — фильтр результатов атак Intruder.

Одна строка: Status, Length, Grep, Extract, Only-matches, Apply/Reset/Clear.
"""

from __future__ import annotations

from pathlib import Path

from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.widgets import Input, Label

from pentool.collections.filter_predicate import FilterOp, FilterPredicate, FilterSpec
from pentool.core.logging import get_logger
from pentool.tui.widgets.filter_bar_widget import FilterBarWidget
from pentool.tui.widgets.toolbar_button import ToolbarButton

logger = get_logger(__name__)

_CSS = (Path(__file__).parent / "intruder_filter_bar.tcss").read_text(encoding="utf-8")


class IntruderFilterBar(FilterBarWidget):
    """Filter bar for Intruder results: status/length/grep — one row."""

    class FilterChanged(FilterBarWidget.FilterChanged):
        pass

    DEFAULT_CSS = _CSS

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
            yield ToolbarButton("Apply", "btn-filter-apply")
            yield ToolbarButton("Reset", "btn-filter-reset")

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
        except Exception as exc:
            # «Only matches» включён, но предикат не добавлен — таблица
            # покажет все строки, хотя переключатель говорит обратное.
            logger.debug("intruder filter: only-matches predicate not applied: %s", exc)

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
        except Exception as exc:
            # После Reset переключатель остаётся в позиции «включён», а фильтр
            # уже сброшен — следующее Apply вернёт прежнее поведение.
            logger.debug("intruder filter: only-matches toggle not reset: %s", exc)
        self._emit(FilterSpec())

    def on_toolbar_button_pressed(self, event: ToolbarButton.Pressed) -> None:
        bid = event.button.id
        if bid == "btn-filter-apply":
            self._apply()
        elif bid == "btn-filter-reset":
            self._reset()
        elif bid == "grep-only-toggle":
            toggle = not event.button.has_class("active")
            event.button.set_class(toggle, "active")
            event.button.label = "● Only matches" if toggle else "○ Only matches"
            self._apply()

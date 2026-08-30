"""Intruder results filter bar (Этап 6, extracted from IntruderScreen).

A self-contained filter bar for the Intruder results table: status / length
range / grep inputs, posting a FilterChanged message on Apply/Reset. Lives
here so the IntruderScreen mega-file is thinner and the bar is reusable /
unit-testable in isolation (a step toward unifying with the proxy FilterBar).
"""

from __future__ import annotations

from textual.app import ComposeResult
from textual.message import Message
from textual.containers import Horizontal
from textual.widget import Widget
from textual.widgets import Button, Input, Label


class GrepOnlyToggle(Widget):
    """Toggle button for 'Only matches' — a non-filtering grep a row must hit.

    Mirrors the proxy ScopeToggle UX: one click toggles active/inactive. When
    active, the Intruder results table shows rows that match the Grep-Match
    pattern and hides the rest (highlighting already colors them).
    """

    DEFAULT_CSS = """
    GrepOnlyToggle {
        width: auto;
        margin: 0 1;
    }
    GrepOnlyToggle.flash {
        text-style: bold;
    }
    """

    class Toggled(Message):
        def __init__(self, active: bool) -> None:
            super().__init__()
            self.active = active

    def __init__(self, **kwargs) -> None:
        super().__init__("○ Only matches", **kwargs)
        self._active: bool = False

    @property
    def active(self) -> bool:
        return self._active

    def on_click(self) -> None:
        self._active = not self._active
        self.update("● Only matches" if self._active else "○ Only matches")
        self.set_class(self._active, "flash")
        self.post_message(self.Toggled(self._active))

    def reset(self) -> None:
        self._active = False
        self.update("○ Only matches")
        self.remove_class("flash")

DEFAULT_CSS = """
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


class IntruderFilterBar(Widget):
    """Filter bar for the Intruder results table.

    Encapsulates status / length-range / grep inputs that were previously
    scattered as inline widgets inside IntruderScreen._compose_results.
    Posts FilterChanged when the user applies or resets filters.
    """

    class FilterChanged(Message):
        """Emitted when the user clicks Apply or Reset."""

        def __init__(self, filters: dict) -> None:
            super().__init__()
            self.filters = filters

    DEFAULT_CSS = DEFAULT_CSS

    def compose(self) -> ComposeResult:
        with Horizontal(id="results-filter-bar"):
            yield Label("Status:")
            yield Input(id="filter-status", placeholder="e.g. 200", compact=True)
            yield Label("Length >")
            yield Input(id="filter-len-gt", placeholder="0", compact=True)
            yield Label("<")
            yield Input(id="filter-len-lt", placeholder="∞", compact=True)
            yield Button("Apply", id="btn-filter-apply")
            yield Button("Reset filters", id="btn-filter-reset")
        with Horizontal(id="grep-bar"):
            yield Label("Grep:")
            yield Input(id="grep-match-input", placeholder="regex — highlight matching rows", compact=True)
            yield Label("Extract:")
            yield Input(id="grep-extract-input", placeholder="regex — add column with extracted value", compact=True)
            yield GrepOnlyToggle(id="grep-only-toggle")
            yield Button("Apply", id="btn-grep-apply")
            yield Button("Clear grep", id="btn-grep-clear")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        bid = event.button.id
        if bid == "btn-filter-apply":
            self._emit_filters()
        elif bid == "btn-filter-reset":
            self._reset()
        elif bid == "btn-grep-apply":
            self._emit_grep()
        elif bid == "btn-grep-clear":
            self._clear_grep()

    def _emit_filters(self) -> None:
        """Build filter dict from current Input values and emit FilterChanged."""
        filters: dict = {}
        try:
            status = self.query_one("#filter-status", Input).value.strip()
            if status:
                filters["status"] = status
        except Exception:
            pass
        try:
            gt = self.query_one("#filter-len-gt", Input).value.strip()
            if gt:
                filters["len_gt"] = int(gt)
        except Exception:
            pass
        try:
            lt = self.query_one("#filter-len-lt", Input).value.strip()
            if lt:
                filters["len_lt"] = int(lt)
        except Exception:
            pass
        self.post_message(self.FilterChanged(filters))

    def _reset(self) -> None:
        try:
            self.query_one("#filter-status", Input).value = ""
            self.query_one("#filter-len-gt", Input).value = ""
            self.query_one("#filter-len-lt", Input).value = ""
        except Exception:
            pass
        try:
            self.query_one("#grep-only-toggle", GrepOnlyToggle).reset()
        except Exception:
            pass
        self.post_message(self.FilterChanged({}))

    def _emit_grep(self) -> None:
        filters: dict = {}
        try:
            match = self.query_one("#grep-match-input", Input).value.strip()
            if match:
                filters["grep_match"] = match
        except Exception:
            pass
        try:
            extract = self.query_one("#grep-extract-input", Input).value.strip()
            if extract:
                filters["grep_extract"] = extract
        except Exception:
            pass
        try:
            toggle = self.query_one("#grep-only-toggle", GrepOnlyToggle)
            if toggle.active:
                filters["grep_only_match"] = True
        except Exception:
            pass
        self.post_message(self.FilterChanged(filters))

    def _clear_grep(self) -> None:
        try:
            self.query_one("#grep-match-input", Input).value = ""
            self.query_one("#grep-extract-input", Input).value = ""
        except Exception:
            pass
        try:
            self.query_one("#grep-only-toggle", GrepOnlyToggle).reset()
        except Exception:
            pass
        self.post_message(self.FilterChanged({}))

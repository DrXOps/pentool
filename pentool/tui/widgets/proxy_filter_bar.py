"""ProxyFilterBar — фильтр HTTP/WS истории прокси.

Порядок элементов (слева направо):
  Host:[____] | Method:[GET ▼] | Status:[200]→[∞] | Mark:[Any ▼] |
  Search:[________] | ★ Scope | [Filter] [Clear]

Загружает CSS из proxy_filter_bar.tcss (как старый FilterBar загружал filter_bar.tcss).
"""

from __future__ import annotations

from pathlib import Path

from textual.app import ComposeResult
from textual.widgets import Button, Label

from pentool.collections.filter_predicate import (
    FilterField,
    FilterFieldType,
    FilterOp,
    FilterPredicate,
    FilterSpec,
)
from pentool.tui.widgets.filter_bar_widget import (
    Cycler,
    FilterBarWidget,
    ToggleButton,
)

_COLORS: list[tuple[str, str]] = [
    ("Any", ""),
    ("🔴", "red"),
    ("🟠", "orange"),
    ("🟡", "yellow"),
    ("🟢", "green"),
    ("🔵", "blue"),
    ("🟣", "purple"),
]

_METHODS: list[tuple[str, str]] = [
    ("Any", ""),
    ("GET", "GET"),
    ("POST", "POST"),
    ("PUT", "PUT"),
    ("DELETE", "DELETE"),
    ("PATCH", "PATCH"),
    ("HEAD", "HEAD"),
    ("OPTIONS", "OPTIONS"),
]


class ProxyFilterBar(FilterBarWidget):
    """Filter row: Host, Method, Status, Mark, Search, Scope + Apply/Reset."""

    class FilterChanged(FilterBarWidget.FilterChanged):
        pass

    DEFAULT_CSS = (Path(__file__).parent / "proxy_filter_bar.tcss").read_text(encoding="utf-8")

    def configure(self) -> list[FilterField]:
        return [
            FilterField("fb-host", "Host:", FilterFieldType.TEXT, "host",
                        FilterOp.LIKE, placeholder="example.com"),
            FilterField("fb-method", "Method:", FilterFieldType.CYCLER, "method",
                        FilterOp.IN, options=_METHODS),
            FilterField("fb-status", "Status:", FilterFieldType.RANGE, "status_code",
                        FilterOp.BETWEEN, placeholder="200"),
            FilterField("fb-color", "Mark:", FilterFieldType.CYCLER, "color",
                        FilterOp.EQ, options=_COLORS),
            FilterField("fb-search", "Search:", FilterFieldType.TEXT, "fts",
                        FilterOp.FTS, placeholder="FTS5 query..."),
        ]

    def compose(self) -> ComposeResult:
        for f in self.configure():
            yield Label(f.label, classes="fb-label")
            yield from self._render_field(f)
            yield Label(" ", classes="fb-sep")
        yield ToggleButton("★ Scope", active_label="★ In Scope", id="fb-scope")
        yield Label(" ", classes="fb-sep")
        yield Button("Filter", id="fb-apply", variant="primary")
        yield Button("Clear", id="fb-reset")

    def collect(self) -> list[FilterPredicate]:
        predicates = super().collect()
        try:
            scope = self.query_one("#fb-scope", ToggleButton)
            if scope.is_active():
                predicates.append(FilterPredicate("scope_only", FilterOp.EQ, True))
        except Exception:
            pass
        return predicates

    def _reset(self) -> None:
        super()._reset()
        try:
            self.query_one("#fb-scope", ToggleButton).reset()
        except Exception:
            pass
        self._emit(FilterSpec())

    def _clear_fields(self) -> None:
        super()._clear_fields()
        try:
            self.query_one("#fb-scope", ToggleButton).reset()
        except Exception:
            pass

    # ── Immediate apply ────────────────────────────────────────────────────

    def on_cycler_changed(self, event: Cycler.Changed) -> None:
        self._apply()

    def on_toggle_button_toggled(self, event: ToggleButton.Toggled) -> None:
        self._apply()
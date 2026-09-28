"""ProxyFilterBar — фильтр HTTP/WS истории прокси.

Заменяет старый FilterBar (filter_bar.py). Отличия:
- Унаследован от FilterBarWidget
- Свои Cycler/ToggleButton из filter_bar_widget (не старые MethodCycler/ScopeToggle)
- Scope toggle добавляется отдельно (не через configure)
- Immediate apply: изменение любого контрола → сразу фильтрует
"""

from __future__ import annotations

from textual.app import ComposeResult

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
    """Filter row: Host, Method, Status, Mark, Search, Scope + Apply/Reset.

    Scope toggle is rendered as a regular ToggleButton (replaces old ScopeToggle).
    """

    class FilterChanged(FilterBarWidget.FilterChanged):
        pass

    DEFAULT_CSS = (FilterBarWidget.DEFAULT_CSS + """
    ProxyFilterBar ToggleButton {
        height: 1;
        width: auto;
        padding: 0 1;
        background: $panel;
        color: $text-muted;
        pointer: pointer;
    }
    ProxyFilterBar ToggleButton:hover {
        background: $primary-darken-1;
    }
    ProxyFilterBar ToggleButton.-active {
        color: $success;
        background: $success-darken-3;
    }
    """)

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
        yield from super().compose()
        yield ToggleButton("★ Scope", id="fb-scope")

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
        """Method or color change → immediate filter."""
        self._apply()

    def on_toggle_button_toggled(self, event: ToggleButton.Toggled) -> None:
        """Scope toggle → immediate filter."""
        self._apply()
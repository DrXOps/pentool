"""ProxyFilterBar и WsFilterBar — фильтры HTTP/WS истории прокси.

Порядок элементов ProxyFilterBar (слева направо):
  Host:[____] | Method:[GET ▼] | Status:[200]→[∞] | Mark:[Any ▼] |
  Search:[________] | ★ Scope | [Filter] [Clear]

WsFilterBar:
  Host:[____] | URL:[________] | ★ Scope | [Filter] [Clear]
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
)
from pentool.tui.widgets.toolbar_button import ToolbarButton

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
    """HTTP History filter bar: Host, Method, Status, Mark, Search, Scope."""

    class FilterChanged(FilterBarWidget.FilterChanged):
        pass

    DEFAULT_CSS = (Path(__file__).parent / "proxy_filter_bar.tcss").read_text(encoding="utf-8")

    def configure(self) -> list[FilterField]:
        return [
            FilterField("fb-host", "Host:", FilterFieldType.TEXT, "host",
                        FilterOp.LIKE, placeholder="example.com"),
            FilterField("fb-method", "Method:", FilterFieldType.CYCLER, "method",
                        FilterOp.IN, options=_METHODS),
            FilterField("fb-status", "Status:", FilterFieldType.TEXT, "status_code",
                        FilterOp.BETWEEN, placeholder="200-299"),
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
        yield ToolbarButton("★ Scope", "fb-scope")
        yield Label(" ", classes="fb-sep")
        yield Button("Filter", id="fb-apply", variant="primary")
        yield Button("Clear", id="fb-reset")

    def collect(self) -> list[FilterPredicate]:
        predicates = super().collect()
        # Status: парсим "200" или "200-299"
        predicates = [self._normalize_status(p) for p in predicates]
        self._maybe_add_scope(predicates)
        return predicates

    def _reset(self) -> None:
        super()._reset()
        self._reset_scope()
        self._emit(FilterSpec())

    def _clear_fields(self) -> None:
        super()._clear_fields()
        self._reset_scope()

    @staticmethod
    def _normalize_status(p: FilterPredicate) -> FilterPredicate:
        if p.field != "status_code" or p.operator != FilterOp.BETWEEN:
            return p
        raw = str(p.value)
        if "-" in raw:
            parts = raw.split("-", 1)
            try:
                return FilterPredicate("status_code", FilterOp.BETWEEN, (int(parts[0]), int(parts[1])))
            except ValueError:
                pass
        try:
            return FilterPredicate("status_code", FilterOp.EQ, int(raw))
        except ValueError:
            pass
        return p

    def _maybe_add_scope(self, predicates: list[FilterPredicate]) -> None:
        try:
            scope = self.query_one("#fb-scope", ToolbarButton)
            if scope.has_class("active"):
                predicates.append(FilterPredicate("scope_only", FilterOp.EQ, True))
        except Exception:
            pass

    def _reset_scope(self) -> None:
        try:
            scope = self.query_one("#fb-scope", ToolbarButton)
            scope.remove_class("active")
            scope.label = "★ Scope"
        except Exception:
            pass

    def on_cycler_changed(self, event: Cycler.Changed) -> None:
        self._apply()

    def on_toolbar_button_pressed(self, event: ToolbarButton.Pressed) -> None:
        if event.button.id == "fb-scope":
            toggle = not event.button.has_class("active")
            event.button.set_class(toggle, "active")
            event.button.label = "★ In Scope" if toggle else "★ Scope"
            self._apply()


class WsFilterBar(FilterBarWidget):
    """WS History filter bar: Host, URL, Status, Search, Scope."""

    class FilterChanged(FilterBarWidget.FilterChanged):
        pass

    DEFAULT_CSS = (Path(__file__).parent / "proxy_filter_bar.tcss").read_text(
        encoding="utf-8"
    ).replace("ProxyFilterBar", "WsFilterBar")

    def configure(self) -> list[FilterField]:
        return [
            FilterField("ws-host", "Host:", FilterFieldType.TEXT, "host",
                        FilterOp.LIKE, placeholder="example.com"),
            FilterField("ws-url", "URL:", FilterFieldType.TEXT, "url",
                        FilterOp.LIKE, placeholder="/ws-endpoint"),
            FilterField("ws-status", "Status:", FilterFieldType.TEXT, "status_code",
                        FilterOp.BETWEEN, placeholder="200-299"),
            FilterField("ws-search", "Search:", FilterFieldType.TEXT, "fts",
                        FilterOp.FTS, placeholder="FTS5 query..."),
        ]

    def compose(self) -> ComposeResult:
        for f in self.configure():
            yield Label(f.label, classes="fb-label")
            yield from self._render_field(f)
            yield Label(" ", classes="fb-sep")
        yield ToolbarButton("★ Scope", "fb-scope")
        yield Label(" ", classes="fb-sep")
        yield Button("Filter", id="fb-apply", variant="primary")
        yield Button("Clear", id="fb-reset")

    def collect(self) -> list[FilterPredicate]:
        predicates = super().collect()
        predicates.append(FilterPredicate("is_websocket", FilterOp.EQ, True))
        self._maybe_add_scope(predicates)
        return predicates

    def _reset(self) -> None:
        super()._reset()
        self._reset_scope()
        self._emit(FilterSpec())

    def _clear_fields(self) -> None:
        super()._clear_fields()
        self._reset_scope()

    def _maybe_add_scope(self, predicates: list[FilterPredicate]) -> None:
        try:
            scope = self.query_one("#fb-scope", ToolbarButton)
            if scope.has_class("active"):
                predicates.append(FilterPredicate("scope_only", FilterOp.EQ, True))
        except Exception:
            pass

    def _reset_scope(self) -> None:
        try:
            scope = self.query_one("#fb-scope", ToolbarButton)
            scope.remove_class("active")
            scope.label = "★ Scope"
        except Exception:
            pass

    def on_toolbar_button_pressed(self, event: ToolbarButton.Pressed) -> None:
        if event.button.id == "fb-scope":
            toggle = not event.button.has_class("active")
            event.button.set_class(toggle, "active")
            event.button.label = "★ In Scope" if toggle else "★ Scope"
            self._apply()
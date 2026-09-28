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
)
from pentool.tui.widgets.toolbar_button import ToolbarButton
from pentool.core.logging import get_logger

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


logger = get_logger(__name__)


class _ProxyFilterBarBase(FilterBarWidget):
    """Base for HTTP and WS filter bars — shared logic.

    Each subclass declares its own FilterChanged Message (Textual handler naming).
    """

    class FilterChanged(FilterBarWidget.FilterChanged):
        pass

    def _emit(self, spec: FilterSpec) -> None:
        """Override: post the SUBCLASS's own FilterChanged, not the base one.

        Each subclass (ProxyFilterBar, WsFilterBar) has its own nested Message
        class. This method discovers the right one at runtime.
        """
        cls = type(self)
        if hasattr(cls, 'FilterChanged'):
            self.post_message(cls.FilterChanged(spec))
        else:
            super()._emit(spec)

    # CSS задаётся каждым наследником (ProxyFilterBar, WsFilterBar)
    # через свои DEFAULT_CSS, чтобы селекторы совпадали с классами.

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
        predicates = [self._normalize_status(p) for p in predicates]
        try:
            scope = self.query_one("#fb-scope", ToolbarButton)
            if scope.has_class("active"):
                predicates.append(FilterPredicate("scope_only", FilterOp.EQ, True))
        except Exception:
            pass
        return predicates

    def _reset(self) -> None:
        super()._reset()
        try:
            scope = self.query_one("#fb-scope", ToolbarButton)
            scope.remove_class("active")
            scope.label = "★ Scope"
        except Exception:
            pass
        self._emit(FilterSpec())

    def _clear_fields(self) -> None:
        super()._clear_fields()
        try:
            scope = self.query_one("#fb-scope", ToolbarButton)
            scope.remove_class("active")
            scope.label = "★ Scope"
        except Exception:
            pass

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

    # ── Handlers ───────────────────────────────────────────────────────────

    def on_cycler_changed(self, event: Cycler.Changed) -> None:
        self._apply()

    def on_toolbar_button_pressed(self, event: ToolbarButton.Pressed) -> None:
        if event.button.id == "fb-scope":
            toggle_class = not event.button.has_class("active")
            if toggle_class:
                event.button.add_class("active")
                event.button.label = "★ In Scope"
            else:
                event.button.remove_class("active")
                event.button.label = "★ Scope"
            self._apply()


class ProxyFilterBar(_ProxyFilterBarBase):
    """HTTP History filter bar — full set: Host, Method, Status, Mark, Search, Scope."""

    class FilterChanged(_ProxyFilterBarBase.FilterChanged):
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


class WsFilterBar(_ProxyFilterBarBase):
    """WS History filter bar — slimmed: Host, URL, Scope."""

    class FilterChanged(_ProxyFilterBarBase.FilterChanged):
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
        ]

    def collect(self) -> list[FilterPredicate]:
        # Fields from configure() + is_websocket=True always
        predicates = super().collect()
        predicates.append(FilterPredicate("is_websocket", FilterOp.EQ, True))
        # Scope toggle
        try:
            scope = self.query_one("#fb-scope", ToolbarButton)
            if scope.has_class("active"):
                predicates.append(FilterPredicate("scope_only", FilterOp.EQ, True))
        except Exception:
            pass
        return predicates

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

    def collect(self) -> list[FilterPredicate]:
        predicates = super().collect()
        try:
            scope = self.query_one("#fb-scope", ToolbarButton)
            if scope.has_class("active"):
                predicates.append(FilterPredicate("scope_only", FilterOp.EQ, True))
        except Exception:
            pass
        return predicates

    def _reset(self) -> None:
        super()._reset()
        try:
            scope = self.query_one("#fb-scope", ToolbarButton)
            scope.remove_class("active")
            scope.label = "★ Scope"
        except Exception:
            pass
        self._emit(FilterSpec())

    def _clear_fields(self) -> None:
        super()._clear_fields()
        try:
            scope = self.query_one("#fb-scope", ToolbarButton)
            scope.remove_class("active")
            scope.label = "★ Scope"
        except Exception:
            pass

    # ── Immediate apply ────────────────────────────────────────────────────

    def on_cycler_changed(self, event: Cycler.Changed) -> None:
        self._apply()

    def on_toggle_button_toggled(self, event: ToggleButton.Toggled) -> None:
        self._apply()

    def on_toolbar_button_pressed(self, event: ToolbarButton.Pressed) -> None:
        """Scope toggle via ToolbarButton click."""
        if event.button.id == "fb-scope":
            toggle_class = not event.button.has_class("active")
            if toggle_class:
                event.button.add_class("active")
                event.button.label = "★ In Scope"
            else:
                event.button.remove_class("active")
                event.button.label = "★ Scope"
            self._apply()
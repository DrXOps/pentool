"""ProxyFilterBar и WsFilterBar — фильтры HTTP/WS истории прокси.

Порядок элементов ProxyFilterBar (слева направо):
  Host:[____] | Method:[GET ▼] | Status:[200]→[∞] | Mark:[Any ▼] |
  Search:[________] | ★ Scope | [Filter] [Clear]

WsFilterBar:
  Host:[____] | URL:[________] | Status:[200]→[∞] | Search:[________] |
  ★ Scope | [Filter] [Clear]

Обе полосы — наследники ``HistoryFilterBar``: общая композиция, общие тоглы
Scope/Comments и общий CSS. Раньше ``WsFilterBar.DEFAULT_CSS`` получался
строковой заменой ``.replace("ProxyFilterBar", "WsFilterBar")`` по файлу
``proxy_filter_bar.tcss`` — переименование класса молча ломало вторую полосу.
"""

from __future__ import annotations

from pathlib import Path

from textual.app import ComposeResult
from textual.widgets import Label

from pentool.collections.filter_predicate import FilterField, FilterFieldType, FilterOp, FilterPredicate
from pentool.tui.widgets.filter_bar_widget import FilterBarWidget
from pentool.tui.widgets.toolbar_button import ToolbarButton

_CSS = (Path(__file__).parent / "proxy_filter_bar.tcss").read_text(encoding="utf-8")

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

_SCOPE_LABEL = "★ Scope"
_SCOPE_ON_LABEL = "★ In Scope"
_COMMENTS_LABEL = "📝 Comments"
_COMMENTS_ON_LABEL = "📝 Comments: ON"


class HistoryFilterBar(FilterBarWidget):
    """Общая часть фильтров истории: Scope/Comments-тоглы и их сброс.

    Наследник задаёт только ``configure()`` и, при необходимости,
    ``collect()`` — композиция и обработка тоглов здесь.
    """

    DEFAULT_CSS = _CSS

    def compose(self) -> ComposeResult:
        yield from self._compose_fields()
        yield ToolbarButton(_SCOPE_LABEL, "fb-scope")
        yield ToolbarButton(_COMMENTS_LABEL, "fb-comments")
        yield Label(" ", classes="fb-sep")
        yield from self._compose_actions()

    def collect(self) -> list[FilterPredicate]:
        predicates = super().collect()
        self._maybe_add_scope(predicates)
        self._maybe_add_comments(predicates)
        return predicates

    def _clear_fields(self) -> None:
        super()._clear_fields()
        self._reset_scope()
        self._reset_comments()

    # ── Тоглы ──────────────────────────────────────────────────────────────

    def _maybe_add_scope(self, predicates: list[FilterPredicate]) -> None:
        if self._toggle_active("fb-scope"):
            predicates.append(FilterPredicate("scope_only", FilterOp.EQ, True))

    def _maybe_add_comments(self, predicates: list[FilterPredicate]) -> None:
        if self._toggle_active("fb-comments"):
            predicates.append(FilterPredicate("comment", FilterOp.NOT_NULL, None))

    def _reset_scope(self) -> None:
        self._set_toggle("fb-scope", False, _SCOPE_LABEL)

    def _reset_comments(self) -> None:
        self._set_toggle("fb-comments", False, _COMMENTS_LABEL)

    def _toggle_active(self, toggle_id: str) -> bool:
        try:
            return self.query_one(f"#{toggle_id}", ToolbarButton).has_class("active")
        except Exception:
            return False

    def _set_toggle(self, toggle_id: str, active: bool, label: str) -> None:
        try:
            button = self.query_one(f"#{toggle_id}", ToolbarButton)
        except Exception:
            return
        button.set_class(active, "active")
        button.label = label

    def _flip_toggle(self, toggle_id: str, label: str, on_label: str) -> None:
        active = not self._toggle_active(toggle_id)
        self._set_toggle(toggle_id, active, on_label if active else label)
        self._apply()

    def on_toolbar_button_pressed(self, event: ToolbarButton.Pressed) -> None:
        match event.button.id:
            case "fb-scope":
                self._flip_toggle("fb-scope", _SCOPE_LABEL, _SCOPE_ON_LABEL)
            case "fb-comments":
                self._flip_toggle("fb-comments", _COMMENTS_LABEL, _COMMENTS_ON_LABEL)


class ProxyFilterBar(HistoryFilterBar):
    """HTTP History filter bar: Host, Method, Status, Mark, Search, Scope."""

    class FilterChanged(HistoryFilterBar.FilterChanged):
        pass

    def configure(self) -> list[FilterField]:
        return [
            FilterField(
                "fb-host",
                "Host:",
                FilterFieldType.TEXT,
                "host",
                FilterOp.LIKE,
                placeholder="example.com",
            ),
            FilterField(
                "fb-method",
                "Method:",
                FilterFieldType.CYCLER,
                "method",
                FilterOp.IN,
                options=_METHODS,
            ),
            FilterField(
                "fb-status",
                "Status:",
                FilterFieldType.TEXT,
                "status_code",
                FilterOp.BETWEEN,
                placeholder="200-299",
            ),
            FilterField("fb-color", "Mark:", FilterFieldType.CYCLER, "color", FilterOp.EQ, options=_COLORS),
            FilterField(
                "fb-search",
                "Search:",
                FilterFieldType.TEXT,
                "fts",
                FilterOp.FTS,
                placeholder="FTS5 query...",
            ),
        ]

    def collect(self) -> list[FilterPredicate]:
        predicates = super().collect()
        # Status: парсим "200" или "200-299"
        return [self._normalize_status(p) for p in predicates]

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


class WsFilterBar(HistoryFilterBar):
    """WS History filter bar: Host, URL, Status, Search, Scope."""

    class FilterChanged(HistoryFilterBar.FilterChanged):
        pass

    def configure(self) -> list[FilterField]:
        return [
            FilterField(
                "fb-host",
                "Host:",
                FilterFieldType.TEXT,
                "host",
                FilterOp.LIKE,
                placeholder="example.com",
            ),
            FilterField(
                "fb-url",
                "URL:",
                FilterFieldType.TEXT,
                "url",
                FilterOp.LIKE,
                placeholder="/ws-endpoint",
            ),
            FilterField(
                "fb-status",
                "Status:",
                FilterFieldType.TEXT,
                "status_code",
                FilterOp.BETWEEN,
                placeholder="200-299",
            ),
            FilterField(
                "fb-search",
                "Search:",
                FilterFieldType.TEXT,
                "fts",
                FilterOp.FTS,
                placeholder="FTS5 query...",
            ),
        ]

    def collect(self) -> list[FilterPredicate]:
        predicates = super().collect()
        predicates.append(FilterPredicate("is_websocket", FilterOp.EQ, True))
        return predicates

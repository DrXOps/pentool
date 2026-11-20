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
from textual.containers import Horizontal
from textual.css.query import NoMatches

from pentool.collections.filter_predicate import FilterField, FilterFieldType, FilterOp, FilterPredicate
from pentool.core.logging import get_logger
from pentool.tui.widgets.filter_bar_widget import FilterBarWidget
from pentool.tui.widgets.toolbar_button import ToolbarButton

logger = get_logger(__name__)

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

#: Toggles spell their state out — the word changes on click, so nobody has to
#: remember what a glyph meant. Said as words they are wider, which is why the
#: bar switches to two rows when one row cannot hold them (see
#: ``SINGLE_ROW_MIN_WIDTH``).
_SCOPE_LABEL = "Scope"
_SCOPE_ON_LABEL = "In scope"
_COMMENTS_LABEL = "Comments"
_COMMENTS_ON_LABEL = "Commented"


class HistoryFilterBar(FilterBarWidget):
    """Общая часть фильтров истории: Scope/Comments-тоглы и их сброс.

    Наследник задаёт только ``configure()`` и, при необходимости,
    ``collect()`` — композиция и обработка тоглов здесь.
    """

    DEFAULT_CSS = _CSS

    #: Bar width below which the two logical rows stack instead of sitting side
    #: by side. Measured, not guessed: the fields row plus the actions row (five
    #: labelled fields, two spelled-out toggles, Filter/Clear) need this much.
    #: At 120 columns the screen hands the bar 114 cells, so it stays one row;
    #: at 100 (and below) it stacks.
    SINGLE_ROW_MIN_WIDTH = 113

    is_two_rows: bool = False

    def compose(self) -> ComposeResult:
        # Two rows in the DOM that lie side by side while they fit and stack when
        # they don't — `layout: horizontal` here, `vertical` under `.-two-rows`.
        # Same widgets either way, so switching costs a re-layout, not a remount.
        with Horizontal(id="fb-fields", classes="fb-row"):
            yield from self._compose_fields()
        with Horizontal(id="fb-actions", classes="fb-row"):
            yield ToolbarButton(
                _SCOPE_LABEL,
                "fb-scope",
                tooltip="Show only requests that fall inside Scope",
            )
            yield ToolbarButton(
                _COMMENTS_LABEL,
                "fb-comments",
                tooltip="Show only requests with a comment",
            )
            yield from self._compose_actions()

    def collect(self) -> list[FilterPredicate]:
        predicates = super().collect()
        self._maybe_add_scope(predicates)
        self._maybe_add_comments(predicates)
        return predicates

    # ── One row while it fits, two rows when it does not ──────────────────

    def on_resize(self, event) -> None:
        """Decide the row count from the bar's own width.

        Not from the terminal width: the inspector panel or a dragged resize
        handle can take columns away while the screen stays wide, and it is the
        bar that overflows.
        """
        self.set_two_rows(event.size.width < self.SINGLE_ROW_MIN_WIDTH)

    def set_two_rows(self, two_rows: bool) -> None:
        if two_rows == self.is_two_rows:
            return
        self.is_two_rows = two_rows
        self.set_class(two_rows, "-two-rows")

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
        except NoMatches as exc:
            # Тогл считается выключенным — «★ Scope»/«Comments» на экране
            # горят, а фильтр их не учитывает.
            logger.debug("proxy filter: toggle %s not found: %s", toggle_id, exc)
            return False

    def _set_toggle(self, toggle_id: str, active: bool, label: str) -> None:
        try:
            button = self.query_one(f"#{toggle_id}", ToolbarButton)
        except NoMatches as exc:
            # Положение тогла не обновилось — подпись расходится с фильтром.
            logger.debug("proxy filter: toggle %s not set: %s", toggle_id, exc)
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
                placeholder="FTS5...",
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

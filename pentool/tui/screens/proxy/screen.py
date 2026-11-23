"""Full-featured proxy server screen."""

from __future__ import annotations

import asyncio
import json
import os
import time
from pathlib import Path
from urllib.parse import urlparse

from textual import on
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.css.query import NoMatches
from textual.widget import Widget
from textual.widgets import Label, Static, TabbedContent, TabPane

from pentool.api.proxy_api import InterceptedRequest, MatchReplaceRule
from pentool.collections.filter_predicate import FilterOp, FilterPredicate, FilterSpec
from pentool.core.logging import get_logger
from pentool.services.proxy_service import ProxyService
from pentool.tui.header import HeaderAction, HeaderSpec, HeaderTab
from pentool.tui.hotkeys.defaults import PROXY_BINDINGS
from pentool.tui.markup import esc
from pentool.tui.messages import SendToIntruder, SendToRepeater, SyncScopeToTarget
from pentool.tui.mixins.app_mixin import AppMixin
from pentool.tui.mixins.content_clipboard_mixin import ContentClipboardMixin
from pentool.tui.mixins.request_context_menu import RequestContextMenuMixin
from pentool.tui.widgets.content_panel import ContentPanel
from pentool.tui.widgets.context_menu import ContextMenu
from pentool.tui.widgets.data_table_mixins import SortableTableMixin
from pentool.tui.widgets.inspector_panel import InspectorPanel
from pentool.tui.widgets.intercept import InterceptMixin
from pentool.tui.widgets.proxy_data_table import ProxyDataTable
from pentool.tui.widgets.proxy_filter_bar import ProxyFilterBar as FilterBar
from pentool.tui.widgets.proxy_filter_bar import WsFilterBar
from pentool.tui.widgets.proxy_helpers import COL_NAMES as _COL_NAMES
from pentool.tui.widgets.proxy_helpers import make_empty_table as _make_empty_table
from pentool.tui.widgets.proxy_helpers import row_to_record as _row_to_record
from pentool.tui.widgets.proxy_helpers import rows_to_arrow as _rows_to_arrow
from pentool.tui.widgets.request_editor import HttpView
from pentool.tui.widgets.resize_handle import ResizeHandle
from pentool.tui.widgets.table_factory import make_table
from pentool.tui.widgets.toolbar_button import ToolbarButton

logger = get_logger(__name__)

_CSS = (Path(__file__).parent / "screen.tcss").read_text(encoding="utf-8")

# Page size for HTTP History: initial load + each "scroll up to load more" page.
# Matches ProxyService.get_history()'s default limit — the full history lives
# in SQLite (HttpStorage), this only bounds how much is materialized in the
# TUI table/rows_cache at once.
_HISTORY_PAGE_SIZE = 300

# Minimum interval between full filtered reloads of the HTTP History table.
# While a filter is active, every live request used to trigger a full reload
# (COUNT + SELECT + Arrow rebuild + refresh) in the main loop — under dense
# background traffic this starved the Textual renderer ("UI froze for tens of
# seconds"). Coalescing to one reload per window keeps the list fresh without
# drowning the renderer.
_FILTER_RELOAD_DEBOUNCE_S = 0.6

# HTTP-history table Arrow/row helpers (_make_empty_table, _rows_to_arrow,
# _row_to_record, _COL_NAMES) moved to tui/widgets/proxy_helpers.py (Stage 6) —
# imported at the top of this module under the same names.

DataTable = ProxyDataTable


class _LazyTabBody(Vertical):
    """Container that composes one sub-tab's body on demand.

    A sub-tab builder is an ordinary `compose()`-style generator (it uses
    `with Horizontal(...)` blocks), so it can only run inside a widget's own
    compose pass. Mounting the container is what triggers that pass — see
    `ProxyScreen._populate_tab`.
    """

    def __init__(self, builder, **kwargs) -> None:  # noqa: ANN001 - callable generator
        super().__init__(**kwargs)
        self._builder = builder

    def compose(self) -> ComposeResult:
        yield from self._builder()


class ProxyScreen(
    ContentClipboardMixin,
    SortableTableMixin,
    RequestContextMenuMixin,
    AppMixin,
    InterceptMixin,
    Widget,
):
    """Full Proxy module screen."""

    DEFAULT_CSS = _CSS

    BINDINGS = PROXY_BINDINGS

    # For test compatibility (test_stage8_5)
    _COL_LABELS = ["ID", "Mth", "URL", "St", "Size"]

    # ── RequestContextMenuMixin config (text panel) ───────────────────────────
    _cm_show_nmap = True
    _cm_show_send_intruder = True
    _cm_show_send_scanner = True
    _cm_show_send_decoder = True
    _cm_show_send_comparer = True
    _cm_show_export_md = True
    _cm_show_export_html = True

    def __init__(self, proxy_service: ProxyService | None = None, **kwargs) -> None:
        super().__init__(**kwargs)
        self._proxy_service: ProxyService | None = proxy_service
        self._selected_req_id: int | None = None
        # WebSocket-history selection is tracked separately from the HTTP one.
        # The two tables share no id space (WS rows come from a different
        # storage key), so reusing _selected_req_id for the WS guard made every
        # WS load either silently drop (ids rarely match) or — worse — apply a
        # stale entry when numeric ids collided. Keep a distinct value.
        self._selected_ws_req_id: int | None = None
        # _rows_cache is kept in DISPLAY order: oldest first (top), newest
        # last (bottom) — matches the table's top-to-bottom rendering, so
        # new live requests append at the end instead of requiring a prepend
        # + full backend rebuild (see _append_row_to_table).
        self._rows_cache: list[dict] = []
        self._ws_rows_cache: list[dict] = []
        #: Last text written to the "Showing N of M" label — a repeated `update()`
        #: re-measures the widget and costs a layout pass over the whole screen.
        self._history_count_text: str = ""
        self._sort_col: int | None = None
        self._sort_reverse: bool = False
        self._inspector_visible: bool = False
        self._current_filters: FilterSpec | None = None
        self._ws_current_filters: FilterSpec | None = None
        self._pending_req_ids: dict[str, int] = {}
        self._pending_req_ids_ts: dict[str, float] = {}  # BUG-C: timestamps for periodic cleanup
        self._intercept_req: InterceptedRequest | None = None
        self._intercept_pending: list[InterceptedRequest] = []
        #: Sub-tab whose body is currently mounted as the "spare" one (lazy
        #: sub-tabs keep the visible pane plus this one, see `_switch_tab_body`).
        self._previous_tab: str = ""
        #: "starting"/"stopping" while the proxy is coming up or going down; the
        #: header shows a spinner-ish label instead of the plain state then.
        self._proxy_transition: str = ""
        self._intercept_show_special_chars: bool = False
        self._intercept_raw_full: str = ""
        # Debounce: batch rapid row appends into one incremental add_rows() call
        self._pending_append_rows: list[tuple] = []  # (req, row_id) pairs
        # Adaptive debounce for _append_row_to_table: under light traffic (≤5
        # rows/burst) use 0.2s; under heavy traffic (bursts from many tabs)
        # use 0.8s so the main loop isn't flooded with add_rows()/scroll_end().
        # Reset to fast debounce whenever the queue drains completely.
        self._append_debounce_fast = 0.2
        self._append_debounce_slow = 0.8
        self._append_debounce_heavy = 0.8
        self._append_burst_count = 0
        self._last_append_burst_ts = 0.0
        self._debounce_timer = None
        # Same incremental-append batching for the WS History table, so a live
        # WS row is added to the tail without a full `_reload_ws_table` rebuild
        # (which would otherwise reset any scroll-up pagination the user was
        # navigating). See _append_ws_row_to_table / _flush_pending_ws_rows.
        self._pending_ws_append_rows: list[dict] = []
        self._ws_debounce_timer = None
        # Cap on in-memory _rows_cache size — beyond this, oldest loaded rows
        # are dropped and _history_oldest_offset is bumped so "scroll up to
        # load more" can re-fetch them from storage on demand instead of
        # keeping the whole session's history resident in memory forever.
        self._ROWS_CACHE_MAX = 1200
        # "Showing N of M" + scroll-up-to-load-more state (HTTP History only)
        self._history_total: int = 0  # total rows matching current filters (from COUNT(*))
        self._history_oldest_offset: int = 0  # how many older rows are NOT yet loaded (above what's in _rows_cache)
        self._history_loading_more: bool = False
        self._ws_history_total: int = 0  # total WS rows (from COUNT(*)), for the WS "Showing N of M" label
        # WS History pagination (scroll-up-to-load-more), mirroring HTTP's
        # _history_* state. Same rationale: bounded 300-row page so the renderer
        # isn't starved, older rows re-fetched from storage on demand.
        self._ws_history_oldest_offset: int = 0
        self._ws_history_loading_more: bool = False
        # Debounce full reloads while a filter is active: each live request
        # used to trigger a full `_reload_table(filters)` (COUNT + SELECT +
        # Arrow rebuild + refresh) in the main loop. Under dense background
        # traffic with 1000s of rows this starved the Textual renderer and
        # froze the UI for many seconds. Now a filter reload is coalesced to at
        # most one per _FILTER_RELOAD_DEBOUNCE_S window.
        self._filter_reload_pending: bool = False
        self._filter_reload_timer = None  # textual Timer handle (set_timer), see _schedule_filter_reload
        self._current_comment: str = ""  # comment of the currently-selected row (for the Comment dialog)
        # Comments filter moved to ProxyFilterBar as #fb-comments toggle
        # Debounce: delay _load_row_details so rapid cursor movement (RowHighlighted
        # firing on every pixel of mouse travel + programmatic scroll_end from live
        # traffic) doesn't flood the main loop with SQLite workers. Only the LAST
        # highlight within the window triggers a load.
        self._highlight_debounce_handle = None

    def _compose_intercept_tab(self) -> ComposeResult:
        """Children of the ``tab-intercept`` pane (the pane is created by `compose`).

        Mounted lazily by `_populate_tab()` the first time the sub-tab is shown.
        """
        # Forward / Drop / Special are header buttons now (row 2, left side):
        # they are actions of this sub-tab, so they belong to the header spec
        # rather than to the panel. Only the hint stays here.
        yield Label("(enable Intercept to capture requests)", id="intercept-hint")
        with Vertical(id="intercept-req-area"):
            yield ContentPanel(
                "Intercept",
                widget_type="textarea",
                initial_text="(No requests waiting for intercept)",
                buttons=["copy", "paste", "format", "clear"],
                id="intercept-panel",
                classes="card",
            )
        yield ResizeHandle(
            "intercept-req-area",
            "intercept-bottom-area",
            vertical=True,
            id="resize-intercept",
        )
        with Horizontal(id="intercept-bottom-area"):
            with Vertical(id="intercept-sent-panel", classes="card"):
                yield HttpView("Sent Request", id="intercept-sent-req")
            yield ResizeHandle(
                "intercept-sent-panel",
                "intercept-resp-panel",
                id="resize-intercept-sent-resp",
            )
            with Vertical(id="intercept-resp-panel", classes="card"):
                yield HttpView("Response", id="intercept-resp-viewer")

    def _compose_history_tab(self) -> ComposeResult:
        """Children of the ``tab-http-history`` pane (the pane is created by `compose`).

        Mounted lazily by `_populate_tab()` the first time the sub-tab is shown.
        """
        with Horizontal(id="body"):
            with Vertical(id="main-panel"):
                # One card for the whole tab: filters, table and the
                # request/response split live inside it, separated by the resize
                # handles instead of by gaps between separate cards.
                with Vertical(id="history-body", classes="card"):
                    yield FilterBar(id="filter-bar")
                    with Vertical(id="table-area"):
                        yield make_table(
                            _COL_NAMES,
                            table_id="request-list",
                            widths=[5, 24, 8, 24, 6, 8, 8],
                            initial_table=_make_empty_table(),
                            table_class=ProxyDataTable,
                        )
                        yield Static("", id="history-count", classes="history-count")
                    yield ResizeHandle(
                        "table-area",
                        "detail-area",
                        vertical=True,
                        id="resize-table-detail",
                    )
                    with Horizontal(id="detail-area"):
                        with Vertical(id="req-panel"):
                            yield HttpView("Request", id="req-editor")
                        yield ResizeHandle(
                            "req-panel",
                            "resp-panel",
                            id="resize-req-resp",
                        )
                        with Vertical(id="resp-panel"):
                            yield HttpView("Response", id="resp-viewer")
            yield InspectorPanel(id="inspector-panel")

    def _compose_ws_tab(self) -> ComposeResult:
        """Children of the ``tab-ws-history`` pane (the pane is created by `compose`).

        Mounted lazily by `_populate_tab()` the first time the sub-tab is shown.
        """
        with Horizontal(id="ws-body"):
            with Vertical(id="ws-main-panel"):
                with Vertical(id="ws-history-body", classes="card"):
                    yield WsFilterBar(id="ws-filter-bar")
                    with Vertical(id="ws-table-area"):
                        yield make_table(
                            _COL_NAMES,
                            table_id="ws-request-list",
                            widths=[5, 24, 8, 24, 6, 8, 8],
                            initial_table=_make_empty_table(),
                            table_class=ProxyDataTable,
                        )
                        yield Static("", id="ws-history-count", classes="history-count")
                    yield ResizeHandle(
                        "ws-table-area",
                        "ws-detail-area",
                        vertical=True,
                        id="resize-ws-table-detail",
                    )
                    with Horizontal(id="ws-detail-area"):
                        with Vertical(id="ws-req-panel"):
                            yield HttpView("Request", id="ws-req-editor")
                        yield ResizeHandle(
                            "ws-req-panel",
                            "ws-resp-panel",
                            id="resize-ws-req-resp",
                        )
                        with Vertical(id="ws-resp-panel"):
                            yield HttpView("Response", id="ws-resp-viewer")
                yield ResizeHandle(
                    "ws-detail-area",
                    "ws-messages-area",
                    vertical=True,
                    id="resize-ws-detail-msg",
                )
                with Vertical(id="ws-messages-area"):
                    yield ContentPanel(
                        "WebSocket Messages",
                        widget_type="richlog",
                        wrap=True,
                        max_lines=1000,
                        buttons=["copy", "clear"],
                        id="ws-msg-panel",
                        classes="card",
                    )

    def compose(self) -> ComposeResult:
        # The module toolbar (proxy / intercept / skip / M&R / clear) lives in the
        # app's module header now: content occupies the full width and every
        # module reads the same (see `pentool/tui/header.py` and
        # `header_spec()` below). The sub-tab strip is drawn there too — its own
        # `ContentTabs` row is hidden in screen.tcss, so tabs exist once.
        #
        # Panes start **empty**: a sub-tab's body is mounted the first time the
        # tab is shown (`_populate_tab`). Building all three here put 126 widgets
        # in the tree (28 + 47 + 51) while the user looks at one tab, and every
        # hidden widget took part in the layout/render sweep of each action.
        with TabbedContent(initial="tab-http-history", id="proxy-subtabs"):
            for tab_id, title in self._subtab_ids():
                yield TabPane(title, id=tab_id)

    # ── Lazy sub-tabs ─────────────────────────────────────────────────────
    _TAB_BUILDERS = {
        "tab-intercept": "_compose_intercept_tab",
        "tab-http-history": "_compose_history_tab",
        "tab-ws-history": "_compose_ws_tab",
    }

    async def _populate_tab(self, tab_id: str) -> None:
        """Mount *tab_id*'s body if the pane is still empty."""
        if tab_id not in self._TAB_BUILDERS:
            return
        try:
            pane = self.query_one(f"#{tab_id}", TabPane)
        except NoMatches as exc:
            logger.debug("proxy: sub-tab %s not mounted yet: %s", tab_id, exc)
            return
        if pane.children:
            return
        builder = getattr(self, self._TAB_BUILDERS[tab_id])
        try:
            # The builder is a `compose()`-style generator (`with Horizontal(...)`
            # blocks and all). It can only run inside a widget's own compose pass,
            # so the body gets a container that composes it — `mount_all` outside
            # of compose raises `IndexError` on Textual's `_compose_stacks`.
            await pane.mount(_LazyTabBody(builder, id=f"{tab_id}-body"))
        except Exception:
            # A half-built tab is unusable: report loudly, the pane stays empty
            # and the next tab switch retries.
            logger.exception("proxy: sub-tab %s body not mounted", tab_id)
            return
        self._after_tab_mounted(tab_id)

    def _after_tab_mounted(self, tab_id: str) -> None:
        """Fill a freshly built sub-tab with data (its widgets just appeared)."""
        self.call_after_refresh(self._refresh_tab_data, tab_id)

    def _refresh_tab_data(self, tab_id: str) -> None:
        if tab_id == "tab-http-history":
            self.run_worker(self._reload_table(self._current_filters))
        elif tab_id == "tab-ws-history":
            self.run_worker(self._reload_ws_table())
        else:
            self._sync_intercept_tab_widgets()

    def _sync_intercept_tab_widgets(self) -> None:
        """Intercept tab rebuilt: restore hint/buttons from the queue state."""
        try:
            from textual.widgets import Label

            queued = len(self._intercept_pending)
            hint = "(enable Intercept to capture requests)"
            if self._intercept_req is not None:
                hint = f"⏸ Intercepted: {self._intercept_req.method} {self._intercept_req.url}"
                if queued:
                    hint += f"  (+{queued} queued)"
            self.query_one("#intercept-hint", Label).update(hint)
        except NoMatches as exc:
            logger.debug("proxy: intercept hint not restored: %s", exc)

    @on(TabbedContent.TabActivated, "#proxy-subtabs")
    def _on_subtab_activated_lazy(self, event: TabbedContent.TabActivated) -> None:
        """Build the newly selected sub-tab, drop the one left behind."""
        tab_id = getattr(event.tab, "id", "") or ""
        tab_id = tab_id.removeprefix("--content-tab-")
        if not tab_id:
            return
        self.run_worker(self._switch_tab_body(tab_id), group="proxy-tabs", exclusive=True)

    async def _switch_tab_body(self, tab_id: str) -> None:
        """Keep one spare sub-tab mounted (the one just left), unmount the rest."""
        for other in self._TAB_BUILDERS:
            if other in (tab_id, self._previous_tab):
                continue
            await self._unmount_tab_body(other)
        await self._populate_tab(tab_id)
        self._previous_tab = tab_id

    async def _unmount_tab_body(self, tab_id: str) -> None:
        try:
            pane = self.query_one(f"#{tab_id}", TabPane)
        except NoMatches:
            return
        if not pane.children:
            return
        try:
            await pane.remove_children()
        except Exception:
            logger.debug("proxy: sub-tab %s body not unmounted", tab_id, exc_info=True)

    # ── Module header (see pentool/tui/header.py) ─────────────────────────
    def _subtab_ids(self) -> tuple[tuple[str, str], ...]:
        return (
            ("tab-intercept", "Intercept"),
            ("tab-http-history", "HTTP History"),
            ("tab-ws-history", "WS History"),
        )

    def _active_subtab(self) -> str:
        try:
            tabs = self.query_one("#proxy-subtabs", TabbedContent)
        except NoMatches:
            return "tab-http-history"
        return tabs.active or "tab-http-history"

    def header_spec(self) -> HeaderSpec:
        """Two-row header: state on row 1, sub-tab actions + chips on row 2."""
        proxy = self._get_proxy()
        running = bool(proxy and getattr(proxy, "is_running", False))
        port = getattr(proxy, "port", 8080)
        intercepting = bool(proxy and getattr(proxy, "intercept_enabled", False))
        skipping = bool(proxy and getattr(proxy, "enforce_scope", False))
        active = self._active_subtab()

        if self._proxy_transition == "starting":
            proxy_label = "⏳ Proxy…"
        elif self._proxy_transition == "stopping":
            proxy_label = "⏳ Proxy…"
        elif running:
            proxy_label = f"● Proxy:{port}"
        else:
            proxy_label = "○ Proxy"

        actions: list[HeaderAction] = []
        if active == "tab-intercept":
            # Forward/Drop stay clickable with nothing intercepted: a disabled
            # button draws the "not allowed" cursor, which users read as a bug
            # rather than as "nothing to act on yet". The handler explains it.
            actions.append(HeaderAction("forward", "⏩ Forward"))
            actions.append(HeaderAction("drop", "✖ Drop"))
            actions.append(HeaderAction("special", "⏎ Special"))

        pending = len(self._intercept_pending) + (1 if self._intercept_req is not None else 0)
        counters: tuple[str, ...] = (f"⏸ {pending}",) if intercepting and pending else ()

        return HeaderSpec(
            state=(
                HeaderAction("proxy", proxy_label, enabled=running),
                HeaderAction("intercept", "● Intercept" if intercepting else "○ Intercept", enabled=intercepting),
            ),
            counters=counters,
            tabs=tuple(HeaderTab(tab_id, label) for tab_id, label in self._subtab_ids()),
            active_tab=active,
            actions=tuple(actions),
            more=(
                HeaderAction("skip", "☑ Skip out-of-scope: ON" if skipping else "☐ Skip out-of-scope: OFF"),
                HeaderAction("mr", "Match & Replace…"),
                HeaderAction("clear", "Clear history"),
            ),
        )

    def _special_chars_label(self) -> str:
        """Label for the Special-chars toggle (the flag lives on the screen)."""
        return "⏎ Special: ON" if self._intercept_show_special_chars else "⏎ Special: OFF"

    def header_action(self, action_id: str) -> None:
        """A header button was pressed: route to the existing screen actions."""
        if action_id == "proxy":
            self.action_toggle_proxy()
        elif action_id == "intercept":
            self.action_toggle_intercept()
        elif action_id == "skip":
            self.action_toggle_enforce_scope()
        elif action_id == "forward":
            if self._nothing_intercepted():
                self.notify(
                    "Nothing intercepted yet — enable Intercept to capture requests",
                    severity="warning",
                    timeout=3,
                )
                return
            self.action_forward()
        elif action_id == "drop":
            if self._nothing_intercepted():
                self.notify(
                    "Nothing intercepted yet — enable Intercept to capture requests",
                    severity="warning",
                    timeout=3,
                )
                return
            self.action_drop()
        elif action_id == "special":
            self._toggle_intercept_special_chars(None)
        elif action_id == "mr":
            self.action_open_mr()
        elif action_id == "clear":
            self.action_clear_list()

    def _nothing_intercepted(self) -> bool:
        """True when the intercept queue is empty (Forward/Drop have no subject)."""
        return not self._intercept_pending and self._intercept_req is None

    def header_tab_selected(self, tab_id: str) -> None:
        """A sub-tab chip was clicked in the header."""
        try:
            self.query_one("#proxy-subtabs", TabbedContent).active = tab_id
        except NoMatches as exc:
            logger.debug("proxy: header tab %s not applied: %s", tab_id, exc)
            return
        self._refresh_header_now()

    @on(TabbedContent.TabActivated)
    def _on_subtab_activated(self, _: TabbedContent.TabActivated) -> None:
        """Sub-tab changed (chip, hotkey or intercept auto-switch).

        Row 2 shows the actions of the *active* sub-tab — Forward/Drop only exist
        for Intercept — so the header follows the tabs, whatever changed them.
        """
        self._refresh_header_now()

    def _refresh_header_now(self) -> None:
        """Ask the app to redraw the header (state, counters, actions)."""
        refresh = getattr(self.app, "refresh_header", None)
        if refresh is None:
            # Standalone screen (unit tests mount it without PentoolApp).
            logger.debug("proxy: app has no header to refresh")
            return
        refresh()

    def on_mount(self) -> None:
        self._sync_proxy_button()
        self._sync_intercept_button()
        self._sync_enforce_scope_button()
        self._setup_tooltips()
        # init_storage is called from app.on_mount after _proxy_service injection
        # BUG-C: periodic cleanup of stale _pending_req_ids entries (memory leak fix)
        self.set_interval(300, self._cleanup_pending_req_ids)
        # Load the per-project Scope host list (falls back to the global
        # Config.scope only if this project's DB has nothing saved yet —
        # see _load_scope_setting). Replaces the old "set initial
        # ScopeToggle state from Config" block, which read Config.scope
        # directly and never re-synced proxy.scope itself — the bug behind
        # "★ Scope button stops working after reopening an older project".
        self.run_worker(self._load_scope_setting())
        # Load the per-project "Skip out-of-scope" flag (defaults to OFF for
        # a fresh mount — _reload_from_storage reloads it again after any
        # subsequent project switch)
        self.run_worker(self._load_enforce_scope_setting())
        # Subscribe to WS frames
        try:
            from pentool.core.event_bus import get_event_bus
            from pentool.core.events import WebSocketFrameEvent

            get_event_bus().subscribe(WebSocketFrameEvent, self._on_ws_frame_event)
        except Exception:
            # Without the subscription the WS History tab stays empty forever: no
            # error, no "no frames" message — just empty. The reason (bus import,
            # subscription-key conflict) is visible only in the traceback.
            logger.exception("proxy: WS frame subscription failed")

    def _on_ws_frame_event(self, event) -> None:
        """WS frame received — append to log (thread-safe)."""
        self.app.call_from_thread(self._append_ws_frame, event)

    def _append_ws_frame(self, event) -> None:
        try:
            log = self.query_one("#ws-msg-panel", ContentPanel).content_widget
            opcode = getattr(event, "opcode", 0x1)
            direction = getattr(event, "direction", "")
            payload_text = getattr(event, "payload_text", "")
            payload = getattr(event, "payload", b"")

            _opcode_names = {0x1: "TEXT", 0x2: "BIN", 0x8: "CLOSE", 0x9: "PING", 0xA: "PONG"}
            op_name = _opcode_names.get(opcode, f"0x{opcode:X}")

            if direction.startswith("client"):
                dir_color = "cyan"
                dir_arrow = "→"
            else:
                dir_color = "green"
                dir_arrow = "←"

            if opcode == 0x1:
                body = payload_text[:200] + ("…" if len(payload_text) > 200 else "")
                log.write(
                    f"[{dir_color}]{dir_arrow} {op_name}[/{dir_color}] "
                    f"[dim]{getattr(event, 'request_id', '')}[/dim] "
                    f"{esc(body)}"
                )
            elif opcode == 0x2:
                log.write(
                    f"[{dir_color}]{dir_arrow} {op_name}[/{dir_color}] "
                    f"[dim]{getattr(event, 'request_id', '')}[/dim] "
                    f"[dim]{len(payload)} bytes[/dim]"
                )
            else:
                log.write(
                    f"[{dir_color}]{dir_arrow} {op_name}[/{dir_color}] [dim]{getattr(event, 'request_id', '')}[/dim]"
                )
        except Exception as exc:
            # Frame not rendered. Without this record it is indistinguishable from "no frames arrived".
            logger.debug("proxy: WS frame not rendered: %s", exc)

    def on_unmount(self) -> None:
        """Unsubscribe from EventBus when the widget is removed."""
        try:
            from pentool.core.event_bus import get_event_bus
            from pentool.core.events import WebSocketFrameEvent

            get_event_bus().unsubscribe(WebSocketFrameEvent, self._on_ws_frame_event)
        except Exception:
            # Unsubscribe failed — the bus keeps calling the method of an unmounted
            # screen; that is exactly the leak ADR-6 fixes. A traceback is needed:
            # a single line does not show whether the bus missed the subscription or
            # failed inside it.
            logger.exception("proxy: WS frame unsubscribe failed on unmount")

    async def _reload_table(
        self,
        filters: FilterSpec | None = None,
        order_by: str | None = None,
        order_dir: str = "desc",
    ) -> None:
        """Load/reload data into the DataTable from storage.

        Loads the most recent _HISTORY_PAGE_SIZE rows (newest page) and
        displays them oldest-first/newest-last, matching how live traffic
        is appended (see _append_row_to_table) and scrolled (auto-scroll to
        bottom on new arrivals, like a log viewer). Older rows beyond the
        page are not loaded here — see _load_more_history() for scroll-up
        pagination.

        Args:
            filters: optional FilterSpec
            order_by: column name for SQL ORDER BY (None = default = id)
            order_dir: "asc" or "desc"
        """
        if self._proxy_service is None or not self._proxy_service.is_storage_ready():
            return
        try:
            logger.info(
                "PROXY SCREEN: _reload_table called, filters=%s order_by=%s %s",
                "none" if not filters else f"{len(filters.predicates)} predicates",
                order_by or "id",
                order_dir,
            )
            newest_first_rows = await self._proxy_service.get_history(
                limit=_HISTORY_PAGE_SIZE,
                filters=filters,
                order_by=order_by,
                desc=(order_dir == "desc"),
            )
            total = await self._proxy_service.count_history(filters=filters)
            logger.debug(
                "PROXY SCREEN: _reload_table loaded %d/%d rows",
                len(newest_first_rows),
                total,
            )
            # Storage returns newest-first (DESC); display wants oldest-first
            # (top) / newest-last (bottom), like a log tail.
            rows = list(reversed(newest_first_rows))
            self._rows_cache = rows
            self._current_filters = filters
            self._history_total = total
            self._history_oldest_offset = max(total - len(rows), 0)
            arrow = _rows_to_arrow(rows)
            table = self.query_one("#request-list", DataTable)
            # One layout pass for the whole update instead of one per widget:
            # `set_data`, the cursor move and the counter each mark the screen
            # dirty on their own (measured: 6-8 full passes per action).
            with self.app.batch_update():
                table.set_data(arrow)
                # Column widths are owned by the table itself
                # (ProxyDataTable.fit_columns): Host and URL share whatever the
                # fixed columns leave, so no horizontal scrollbar is needed.
                table._clear_caches()
                table._require_update_dimensions = True
                table.refresh()
                # Scroll to the last row — newest requests are at the bottom
                if rows:
                    table.move_cursor(row=len(rows) - 1)
                self._update_history_count_label()
        except Exception as exc:
            logger.error("_reload_table failed: %s", exc, exc_info=True)

    def _update_history_count_label(self) -> None:
        try:
            label = self.query_one("#history-count", Static)
        except NoMatches as exc:
            # Counter not updated — "Showing N of M" still reflects the previous
            # page, so the number of loaded records cannot be read off it.
            logger.debug("proxy: history counter not found: %s", exc)
            return
        shown = len(self._rows_cache)
        total = self._history_total
        # Every update makes Textual re-measure the widget, and a re-measure means
        # a layout pass over the whole screen (measured: ~55 ms with the cards UI).
        # The label changes only when the numbers do.
        text = f"Showing {shown:,} of {total:,} records"
        if text != self._history_count_text:
            self._history_count_text = text
            label.update(text)

    def _update_ws_history_count_label(self) -> None:
        """Same "Showing N of M" treatment for the WS History table.

        WS History now has the same scroll-up pagination as HTTP (page-capped
        at 300), so the counter is identical in shape to HTTP's. When the cap
        hides rows it shows "Showing N of M — scroll up to load more";
        otherwise it's blank (everything loaded)."""
        try:
            label = self.query_one("#ws-history-count", Static)
        except NoMatches as exc:
            # Same for WS History: the counter lags behind the rows actually shown,
            # and "scroll up to load more" does not appear when it should.
            logger.debug("proxy: WS history counter not found: %s", exc)
            return
        shown = len(self._ws_rows_cache)
        total = self._ws_history_total
        label.update(f"Showing {shown:,} of {total:,} records")

    async def _load_more_history(self) -> None:
        """Load one older page of history when the user scrolls to the top.

        Prepends older rows to _rows_cache/table without touching the rows
        already displayed — cursor position and any already-scrolled state
        are preserved by re-anchoring the scroll offset after the prepend.
        """
        if self._history_loading_more or self._history_oldest_offset <= 0:
            return
        if self._proxy_service is None or not self._proxy_service.is_storage_ready():
            return
        self._history_loading_more = True
        try:
            page_offset = max(self._history_oldest_offset - _HISTORY_PAGE_SIZE, 0)
            page_limit = self._history_oldest_offset - page_offset
            if page_limit <= 0:
                return
            older_newest_first = await self._proxy_service.get_history(
                offset=page_offset,
                limit=page_limit,
                filters=self._current_filters,
            )
            older_rows = list(reversed(older_newest_first))
            if not older_rows:
                return
            self._rows_cache = older_rows + self._rows_cache
            self._history_oldest_offset = page_offset
            try:
                table = self.query_one("#request-list", DataTable)
                arrow = _rows_to_arrow(self._rows_cache)
                table.set_data(arrow)  # set_data already resets caches and dimensions
                # Keep the view anchored where the user was — after
                # prepending N rows, scroll down by N rows worth so the
                # previously-visible row stays in view instead of jumping
                # back to the very top.
                table.scroll_to(y=table.scroll_y + len(older_rows), animate=False)
            except Exception:
                logger.warning("proxy: history rows not shown after load", exc_info=True)
            self._update_history_count_label()
            logger.info(
                "PROXY SCREEN: _load_more_history loaded %d older rows, oldest_offset now %d",
                len(older_rows),
                self._history_oldest_offset,
            )
        except Exception:
            logger.error("_load_more_history failed", exc_info=True)
        finally:
            self._history_loading_more = False

    def on_proxy_data_table_scrolled_to_top(self, event: ProxyDataTable.ScrolledToTop) -> None:
        """Load one older page when the history table hits the top (infinite scroll)."""
        if event.table_id == "ws-request-list":
            self.run_worker(self._load_more_ws_history(), group="proxy-history")
        else:
            self.run_worker(self._load_more_history(), group="proxy-history")

    async def _load_more_ws_history(self) -> None:
        """Load one older page of WS history when the user scrolls to the top.

        Mirrors _load_more_history but for the WS History table, which is now
        page-capped (300 rows). Without this, older WS rows were unreachable
        once the cap hid them. Prepends older rows to _ws_rows_cache/table and
        re-anchors the scroll so the user stays put (same as HTTP)."""
        if self._ws_history_loading_more or self._ws_history_oldest_offset <= 0:
            return
        if self._proxy_service is None or not self._proxy_service.is_storage_ready():
            return
        self._ws_history_loading_more = True
        try:
            page_offset = max(self._ws_history_oldest_offset - _HISTORY_PAGE_SIZE, 0)
            page_limit = self._ws_history_oldest_offset - page_offset
            if page_limit <= 0:
                return
            if self._ws_current_filters and not self._ws_current_filters.is_empty:
                ws_filter = self._ws_current_filters
            else:
                ws_filter = FilterSpec(
                    predicates=[
                        FilterPredicate("is_websocket", FilterOp.EQ, True),
                    ]
                )
            older_newest_first = await self._proxy_service.get_history(
                offset=page_offset,
                limit=page_limit,
                filters=ws_filter,
            )
            older_rows = list(reversed(older_newest_first))
            if not older_rows:
                return
            self._ws_rows_cache = older_rows + self._ws_rows_cache
            self._ws_history_oldest_offset = page_offset
            try:
                table = self.query_one("#ws-request-list", DataTable)
                arrow = _rows_to_arrow(self._ws_rows_cache)
                table.set_data(arrow)  # set_data already resets caches and dimensions
                table.scroll_to(y=table.scroll_y + len(older_rows), animate=False)
            except Exception:
                logger.warning("proxy: WS history rows not shown after load", exc_info=True)
            self._update_ws_history_count_label()
            logger.info(
                "PROXY SCREEN: _load_more_ws_history loaded %d older rows, oldest_offset now %d",
                len(older_rows),
                self._ws_history_oldest_offset,
            )
        except Exception:
            logger.error("_load_more_ws_history failed", exc_info=True)
        finally:
            self._ws_history_loading_more = False

    async def _reload_ws_table(
        self,
        filters: FilterSpec | None = None,
        order_by: str | None = None,
        order_dir: str = "desc",
    ) -> None:
        """Load/reload WebSocket requests into the WS History table.

        Args:
            filters: optional FilterSpec
            order_by: column name for SQL ORDER BY (None = default = id)
            order_dir: "asc" or "desc"
        """
        if self._proxy_service is None or not self._proxy_service.is_storage_ready():
            return
        try:
            if filters and not filters.is_empty:
                ws_filters = filters
            else:
                ws_filters = FilterSpec(
                    predicates=[
                        FilterPredicate("is_websocket", FilterOp.EQ, True),
                    ]
                )
            logger.info(
                "PROXY SCREEN: _reload_ws_table called, predicates=%d order_by=%s %s",
                len(ws_filters.predicates),
                order_by or "id",
                order_dir,
            )
            total = await self._proxy_service.count_history(filters=ws_filters)
            rows = await self._proxy_service.get_history(
                limit=_HISTORY_PAGE_SIZE,
                filters=ws_filters,
                order_by=order_by,
                desc=(order_dir == "desc"),
            )
            logger.info("PROXY SCREEN: _reload_ws_table loaded %d/%d WS rows", len(rows), total)
            self._ws_rows_cache = rows
            self._ws_history_total = total
            self._ws_history_oldest_offset = max(total - len(rows), 0)
            self._ws_current_filters = filters
            self._update_ws_history_count_label()
            arrow = _rows_to_arrow(rows)
            try:
                table = self.query_one("#ws-request-list", DataTable)
            except NoMatches as exc:
                # WS table not found — the loaded page is not displayed even though
                # the counter was already bumped: "Showing N of M" now lies.
                logger.debug("proxy: WS table not found, page not shown: %s", exc)
                return
            table.set_data(arrow)
            # Same as the HTTP table: widths are fitted by the table itself.
            table._clear_caches()
            table._require_update_dimensions = True
            table.refresh()
            if rows:
                table.move_cursor(row=0)
        except Exception:
            logger.error("_reload_ws_table failed", exc_info=True)

    def _setup_tooltips(self) -> None:
        # The module toolbar moved to the header (see header_spec): those buttons
        # carry their tooltips from the spec now, so only the panel-local button
        # is left here.
        tooltips = {
            "btn-ca-cert": "Install CA certificate",
        }
        for btn_id, tip in tooltips.items():
            try:
                self.query_one(f"#{btn_id}", ToolbarButton).tooltip = tip
            except NoMatches as exc:
                # The button is not in the tree — it needs no tooltip; but it is
                # exactly this silence that hides a typo in the id.
                logger.debug("proxy: tooltip for #%s not set: %s", btn_id, exc)

    def load_from_project(self) -> None:
        """Called after a project switch — reloads the table from the (already switched) storage."""
        self.run_worker(self._reload_from_storage())

    async def _reload_from_proxy(self) -> None:
        """Sync storage from the in-memory proxy (for history clear/reset)."""
        if self._proxy_service is None:
            return
        for _ in range(50):
            if self._proxy_service.is_storage_ready():
                break
            await asyncio.sleep(0.1)
        if not self._proxy_service.is_storage_ready():
            logger.error("_reload_from_proxy: storage not ready")
            return
        await self._proxy_service.reload_from_proxy(self._get_proxy_api())
        await self._reload_table()

    async def _reload_from_storage(self, is_new: bool = False) -> None:
        """Reload the table from current storage without clearing data."""
        if self._proxy_service is None:
            return
        for _ in range(60):
            if self._proxy_service.is_storage_ready():
                break
            await asyncio.sleep(0.1)
        if not self._proxy_service.is_storage_ready():
            logger.error("_reload_from_storage: storage not ready after 6s")
            return
        logger.info("PROXY SCREEN: _reload_from_storage: storage ready, loading tables")
        await self._reload_table()
        await self._reload_ws_table()
        # Reload the per-project Scope host list AND "Skip out-of-scope" flag
        # for the DB we just switched to — neither must leak from whatever
        # project was open before (see _load_scope_setting docstring for the
        # "★ Scope button stops working after reopening an older project"
        # bug this fixes). is_new propagates so a brand-new project starts
        # with an empty scope rather than inheriting the previous project's.
        await self._load_scope_setting(is_new=is_new)
        await self._load_enforce_scope_setting()
        logger.info("PROXY SCREEN: _reload_from_storage: tables reloaded")

    def add_request_row(self, req: object) -> None:
        """Called from app when a new request arrives (before a response)."""
        if not isinstance(req, InterceptedRequest):
            return
        if req.id in self._pending_req_ids:
            logger.debug("PROXY SCREEN: add_request_row: duplicate req.id=%s, skipping", req.id)
            return
        # Hot path: one line per captured request. `DEBUG` on purpose — INFO here
        # means the journal grows linearly with traffic (T-026/T-021: 4.7 GB in a
        # week), and a write plus a flush per packet is I/O on every capture.
        logger.debug(
            "PROXY SCREEN: add_request_row: %s %s (id=%s, ws=%s)",
            req.method,
            req.url,
            req.id,
            req.is_websocket,
        )
        self._pending_req_ids[req.id] = -1
        self._pending_req_ids_ts[req.id] = time.time()
        self.run_worker(self._store_request(req))

    def _cleanup_pending_req_ids(self) -> None:
        """Periodic cleanup of stale _pending_req_ids (requests never completed)."""
        cutoff = time.time() - 600  # 10 minutes
        stale_ids = [req_id for req_id, ts in self._pending_req_ids_ts.items() if ts < cutoff]
        for req_id in stale_ids:
            self._pending_req_ids.pop(req_id, None)
            self._pending_req_ids_ts.pop(req_id, None)
        if stale_ids:
            logger.debug("PROXY SCREEN: _cleanup_pending_req_ids: removed %d stale entries", len(stale_ids))

    def update_request_row(self, req: object) -> None:
        """Called from app when a request is fully complete (with response)."""
        if not isinstance(req, InterceptedRequest):
            return
        status = req.get_response().status if req.get_response() else None
        # One line per completed request — same rule as add_request_row above.
        logger.debug(
            "PROXY SCREEN: update_request_row: %s %s → %s (id=%s)",
            req.method,
            req.url,
            status,
            req.id,
        )
        self.run_worker(self._update_and_reload(req))

    async def _store_request(self, req: InterceptedRequest) -> None:
        if self._proxy_service is None:
            return
        row_id = await self._proxy_service.store_request(req)
        if row_id is not None:
            # Per-request line: DEBUG, otherwise the journal grows with traffic.
            logger.debug("PROXY SCREEN: _store_request: saved req.id=%s as row_id=%d", req.id, row_id)
            self._pending_req_ids[req.id] = row_id

    async def _wait_for_row_id(self, req: InterceptedRequest) -> int | None:
        """Wait until _store_request replaces the -1 sentinel with a real row_id."""
        for _ in range(50):
            row_id = self._pending_req_ids.get(req.id)
            if row_id is not None and row_id != -1:
                return row_id
            if req.id not in self._pending_req_ids:
                return None
            await asyncio.sleep(0.1)
        return self._pending_req_ids.get(req.id)

    async def _update_and_reload(self, req: InterceptedRequest) -> None:
        _t0 = time.monotonic()
        if self._proxy_service is None or not self._proxy_service.is_storage_ready():
            return
        await self._wait_for_row_id(req)
        _t1 = time.monotonic()
        actual_row_id = self._pending_req_ids.pop(req.id, None)
        self._pending_req_ids_ts.pop(req.id, None)
        if actual_row_id and actual_row_id != -1 and req.get_response() is not None:
            await self._proxy_service.update_response(actual_row_id, req.get_response())
        elif req.get_response() is not None:
            # Either never stored (actual_row_id is None) or _wait_for_row_id
            # timed out while _store_request was still in flight, leaving the
            # -1 sentinel behind (actual_row_id == -1). In both cases the
            # response would otherwise be silently dropped from HTTP History —
            # store the full request+response now instead of losing it.
            new_row_id = await self._proxy_service.store_request(req)
            if new_row_id is not None:
                actual_row_id = new_row_id
        if req.is_websocket:
            if actual_row_id and actual_row_id != -1:
                if self._current_filters:
                    # With filters active (including "Comments: ON") reload the
                    # whole WS table from the DB, so the 💬 marker and the
                    # filtering take effect immediately (same as HTTP).
                    self._schedule_filter_reload()
                else:
                    self._append_ws_row_to_table(req, actual_row_id)
            else:
                # Never stored / id unknown — fall back to a full WS reload.
                await self._reload_ws_table()
        _t2 = time.monotonic()
        if (_t2 - _t0) > 0.2:
            logger.warning(
                "PROXY SCREEN: _update_and_reload slow: wait_row_id=%.1fms update_resp=%.1fms total=%.1fms req=%s %s",
                (_t1 - _t0) * 1000,
                (_t2 - _t1) * 1000,
                (_t2 - _t0) * 1000,
                req.method,
                req.url[:60],
            )
        elif self._current_filters:
            self._schedule_filter_reload()
        elif actual_row_id and actual_row_id != -1:
            self._append_row_to_table(req, actual_row_id)
        else:
            await self._reload_table(None)

    def _schedule_filter_reload(self) -> None:
        """Coalesce full filtered reloads while live traffic is streaming in.

        See _FILTER_RELOAD_DEBOUNCE_S. The first pending request reloads
        immediately-ish; any further requests within the window only mark it
        pending, and one final reload fires after the window closes. This stops
        the per-request full-table rebuild that froze the UI."""
        self._filter_reload_pending = True
        if self._filter_reload_timer is not None:
            return  # already scheduled — later reload coalesces into it
        self._filter_reload_timer = self.set_timer(
            _FILTER_RELOAD_DEBOUNCE_S,
            lambda: self.run_worker(self._flush_filter_reload()),
        )

    async def _flush_filter_reload(self) -> None:
        """Fire one coalesced filtered reload (debounce window has closed)."""
        self._filter_reload_timer = None
        if not self._filter_reload_pending:
            return
        self._filter_reload_pending = False
        await self._reload_table(self._current_filters)
        await self._reload_ws_table(self._current_filters)

    def _append_row_to_table(self, req: InterceptedRequest, row_id: int) -> None:
        """Incrementally add a single row — debounced at 150 ms.

        Multiple rapid row arrivals (e.g. burst traffic) are batched into
        one ArrowBackend rebuild, avoiding per-request redraws.
        """
        parsed = req.to_parsed_request()
        url = parsed.url or ""
        ts = time.time()
        row: dict = {
            "id": row_id,
            "host": parsed.headers.get("Host", "").split(":")[0] or url.split("/")[2] if "://" in url else url,
            "method": req.method or "",
            "url": url,
            "status_code": req.get_response().status if req.get_response() else None,
            "length": len((req.get_response().body or "").encode("utf-8")) if req.get_response() else None,
            "timestamp": ts,
            "is_websocket": req.is_websocket,
        }
        self._pending_append_rows.append(row)
        if self._debounce_timer is None:
            # Adaptive debounce: if a burst just drained, start fast; if
            # the burst count keeps growing, use slow debounce so the
            # main loop doesn't drown in table rebuilds.
            now = time.time()
            if now - self._last_append_burst_ts < 0.5:
                self._append_burst_count += 1
            else:
                self._append_burst_count = 0
            self._last_append_burst_ts = now
            delay = self._append_debounce_slow if self._append_burst_count > 10 else self._append_debounce_fast
            self._debounce_timer = self.set_timer(delay, self._flush_pending_rows)

    def _flush_pending_rows(self) -> None:
        """Append pending rows incrementally (add_rows, no full rebuild), tail-scroll."""
        self._debounce_timer = None
        if not self._pending_append_rows:
            return
        new_rows = self._pending_append_rows
        self._pending_append_rows = []
        self._rows_cache.extend(new_rows)
        self._history_total += len(new_rows)
        _t0 = time.monotonic()
        try:
            table = self.query_one("#request-list", DataTable)
            _t1 = time.monotonic()
            records = [_row_to_record(r) for r in new_rows]
            _t2 = time.monotonic()
            old_tail = len(self._rows_cache) - len(new_rows) - 1
            was_at_tail = table.cursor_row >= old_tail
            try:
                table.add_rows(records)
            except Exception as exc:
                logger.error("PROXY SCREEN: _flush_pending_rows: add_rows crashed: %s", exc, exc_info=True)
                # Fall back to full rebuild (slow but safe)
                arrow = _rows_to_arrow(self._rows_cache)
                table.set_data(arrow)  # set_data already resets caches and dimensions
            _t3 = time.monotonic()
            if was_at_tail or table.cursor_row >= len(self._rows_cache) - 1:
                table.scroll_end(animate=False)
            _t4 = time.monotonic()
            if len(new_rows) > 50 or (_t4 - _t0) > 0.05:
                logger.warning(
                    "PROXY SCREEN: _flush_pending_rows: %d rows, "
                    "query_one=%.1fms _row_to_record=%.1fms add_rows=%.1fms scroll_end=%.1fms total=%.1fms",
                    len(new_rows),
                    (_t1 - _t0) * 1000,
                    (_t2 - _t1) * 1000,
                    (_t3 - _t2) * 1000,
                    (_t4 - _t3) * 1000,
                    (_t4 - _t0) * 1000,
                )
            # add_rows() appends at the BOTTOM and never shifts existing row
            # indexes, so a highlighted row keeps pointing at the same request
            # even while live traffic streams in. Auto-scroll to the bottom
            # ONLY when the user was already sitting at the tail (following
            # the stream, tail -f style) — if they have selected an older row
            # further up, don't yank their cursor/selection down to the newest
            # entry. That is the second barrier behind the _selected_req_id
            # race guard.
            #
            # Previous logic keyed the "follow the stream" decision on
            # `table.has_focus`, which goes False the instant a context menu
            # (or any other widget) takes focus — so opening the right-click
            # menu over a selected row made the next incoming request fire
            # scroll_end() and yank the table to the newest entry, moving the
            # requested row out from under the user's cursor. We now judge by
            # the cursor's position relative to the OLD tail *before* the
            # append, independent of focus: only follow the stream when the
            # cursor was at (or past) the last row already there.
        except Exception:
            logger.warning("proxy: pending rows not flushed", exc_info=True)
        # Cap unbounded growth of the in-memory cache during very long
        # sessions: drop the oldest rows once we exceed the cap and mark
        # them as available again via _history_oldest_offset so scrolling
        # up re-fetches them from storage instead of leaking memory.
        if len(self._rows_cache) > self._ROWS_CACHE_MAX:
            overflow = len(self._rows_cache) - self._ROWS_CACHE_MAX
            self._rows_cache = self._rows_cache[overflow:]
            self._history_oldest_offset += overflow
            try:
                table = self.query_one("#request-list", DataTable)
                arrow = _rows_to_arrow(self._rows_cache)
                table.set_data(arrow)  # set_data already resets caches and dimensions
                table.scroll_end(animate=False)
            except Exception:
                logger.warning("proxy: rows cache trim failed", exc_info=True)
        self._update_history_count_label()

    def _append_ws_row_to_table(self, req: InterceptedRequest, row_id: int) -> None:
        """Incrementally add a single WS row — debounced like HTTP.

        Same tail-append as _append_row_to_table, but for the WS History table.
        Using incremental add_rows() (instead of _reload_ws_table) keeps any
        scroll-up pagination the user was navigating intact: a new live WS row
        only touches the tail, it never resets the loaded-older-rows offset.
        """
        parsed = req.to_parsed_request()
        url = parsed.url or ""
        ts = time.time()
        row: dict = {
            "id": row_id,
            "host": parsed.headers.get("Host", "").split(":")[0] or url.split("/")[2] if "://" in url else url,
            "method": req.method or "",
            "url": url,
            "status_code": req.get_response().status if req.get_response() else None,
            "length": len((req.response.body or "").encode("utf-8")) if req.response else None,
            "timestamp": ts,
            "is_websocket": True,
        }
        self._pending_ws_append_rows.append(row)
        if self._ws_debounce_timer is None:
            self._ws_debounce_timer = self.set_timer(0.15, self._flush_pending_ws_rows)

    def _flush_pending_ws_rows(self) -> None:
        """Flush pending WS rows via incremental add_rows(), tail-append."""
        self._ws_debounce_timer = None
        if not self._pending_ws_append_rows:
            return
        new_rows = self._pending_ws_append_rows
        self._pending_ws_append_rows = []
        self._ws_rows_cache.extend(new_rows)
        self._ws_history_total += len(new_rows)
        try:
            table = self.query_one("#ws-request-list", DataTable)
            records = [_row_to_record(r) for r in new_rows]
            old_tail = len(self._ws_rows_cache) - len(new_rows) - 1
            was_at_tail = table.cursor_row >= old_tail
            try:
                table.add_rows(records)
            except Exception as exc:
                logger.error("PROXY SCREEN: _flush_pending_ws_rows: add_rows crashed: %s", exc, exc_info=True)
                arrow = _rows_to_arrow(self._ws_rows_cache)
                table.set_data(arrow)  # set_data already resets caches and dimensions
            if was_at_tail or table.cursor_row >= len(self._ws_rows_cache) - 1:
                table.scroll_end(animate=False)
        except Exception:
            logger.warning("proxy: pending WS rows not flushed", exc_info=True)
        # Cap unbounded growth of _ws_rows_cache during long sessions — oldest
        # rows become re-fetchable via scroll-up (_ws_history_oldest_offset),
        # same strategy as HTTP's _flush_pending_rows.
        if len(self._ws_rows_cache) > self._ROWS_CACHE_MAX:
            overflow = len(self._ws_rows_cache) - self._ROWS_CACHE_MAX
            self._ws_rows_cache = self._ws_rows_cache[overflow:]
            self._ws_history_oldest_offset += overflow
            try:
                table = self.query_one("#ws-request-list", DataTable)
                arrow = _rows_to_arrow(self._ws_rows_cache)
                table.set_data(arrow)  # set_data already resets caches and dimensions
                table.scroll_end(animate=False)
            except Exception:
                logger.warning("proxy: WS rows cache trim failed", exc_info=True)
        self._update_ws_history_count_label()

    def _select_row(self, row_idx: int) -> None:
        try:
            if 0 <= row_idx < len(self._rows_cache):
                row = self._rows_cache[row_idx]
                new_id = row.get("id")
                if new_id == self._selected_req_id:
                    return
                self._selected_req_id = new_id
                # Debounce: cancel pending timer, schedule _load_row_details in 0.25s.
                if self._highlight_debounce_handle is not None:
                    try:
                        self._highlight_debounce_handle.stop()
                    except Exception as exc:
                        # The timer already fired — nothing to stop; the handle is
                        # overwritten by the next line anyway.
                        logger.debug("proxy: highlight timer already gone: %s", exc)
                self._highlight_debounce_handle = self.set_timer(0.25, lambda: self._debounced_load(new_id))
        except Exception as exc:
            logger.error("PROXY SCREEN: _select_row crashed: %s", exc, exc_info=True)

    def _select_ws_row(self, row_idx: int) -> None:
        """Select a row in WS History — loads details into the WS panels."""
        try:
            if 0 <= row_idx < len(self._ws_rows_cache):
                row = self._ws_rows_cache[row_idx]
                row_id = row.get("id")
                if row_id is not None:
                    if row_id == self._selected_ws_req_id:
                        return
                    self._selected_ws_req_id = row_id
                    self.run_worker(self._load_ws_row_details(row_id))
        except Exception as exc:
            logger.error("PROXY SCREEN: _select_ws_row crashed: %s", exc, exc_info=True)

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        if event.data_table.id == "ws-request-list":
            self._select_ws_row(event.cursor_row)
        else:
            self._select_row(event.cursor_row)

    def on_proxy_data_table_comment_icon_clicked(self, event: "ProxyDataTable.CommentIconClicked") -> None:
        """Single left-click landing in the Host column opens the comment
        dialog directly when that row has a comment (💬 marker) — this is
        the explicit "click the icon" behavior requested, distinct from
        Enter/double-click which just select the row as usual."""
        if event.row_index < 0 or event.column_index != 1:  # column 1 = Host
            return
        if not (0 <= event.row_index < len(self._rows_cache)):
            return
        row = self._rows_cache[event.row_index]
        comment = str(row.get("comment", "") or "")
        if comment.strip():
            self._comment_dialog(initial_comment=comment)

    def on_data_table_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        """Row highlighted → load details with debounce."""
        try:
            if event.data_table.id == "ws-request-list":
                self._select_ws_row(event.cursor_row)
            else:
                self._select_row(event.cursor_row)
        except Exception:
            logger.exception("PROXY SCREEN: on_data_table_row_highlighted crashed")

    def on_data_table_cell_highlighted(self, event: DataTable.CellHighlighted) -> None:
        """Give focus to DataTable on any cursor movement — required for mouse scroll."""
        try:
            event.data_table.focus()
        except Exception:
            # Without focus the mouse wheel stops paging the table — which users
            # read as "scrolling broke". Otherwise it looks like a Textual bug.
            # A traceback, because focus in Textual can fail for various reasons
            # and a single line cannot tell them apart.
            logger.exception("proxy: table not focused on cell highlight")

    def _debounced_load(self, row_id: int | None) -> None:
        """Run _load_row_details with guard against widget-removed race."""
        try:
            app = self.app
            if not app.is_running:
                return
        except Exception:
            # The widget is already unmounted: `self.app` walks up the parent chain
            # and finds no app (Textual raises `NoActiveAppError`, which lives in a
            # private module — importing it for a single handler costs more than
            # logging a traceback).
            logger.exception("proxy: debounced load skipped, app not usable")
            return
        self.run_worker(self._load_row_details(row_id))

    async def _load_row_details(self, row_id: int | None) -> None:
        if row_id is None or self._proxy_service is None or not self._proxy_service.is_storage_ready():
            return
        entry = await self._proxy_service.get_full_entry(row_id)
        if entry is None:
            return
        # Selection race guard: by the time get_full_entry() returns, the
        # user may have clicked a different row — drawing the stale entry
        # would make the request/response panels show a request that no
        # longer matches the highlighted row. Drop it if the target id moved.
        if self._selected_req_id is not None and row_id != self._selected_req_id:
            return
        self.call_after_refresh(self._load_entry_details, entry)

    async def _load_ws_row_details(self, row_id: int) -> None:
        if self._proxy_service is None or not self._proxy_service.is_storage_ready():
            return
        entry = await self._proxy_service.get_full_entry(row_id)
        if entry is None:
            return
        # Same selection race guard as _load_row_details — ignore stale loads,
        # but keyed on the WS table's own selection (see _selected_ws_req_id).
        if self._selected_ws_req_id is not None and row_id != self._selected_ws_req_id:
            return
        self.call_after_refresh(self._load_ws_entry_details, entry)

    def _load_ws_entry_details(self, entry: dict) -> None:
        # Selection race guard (second layer) — skip drawing a stale entry
        # if the highlighted row changed after the async load finished.
        entry_id = entry.get("id")
        if self._selected_ws_req_id is not None and entry_id is not None and entry_id != self._selected_ws_req_id:
            return
        from pentool.utils.parser import ParsedRequest

        # Stash comment for the comment dialog — same pattern as _load_row_details
        self._current_comment = entry.get("comment", "") or ""

        req_headers = entry.get("request_headers") or {}
        parsed_req = ParsedRequest(
            method=entry.get("method", "GET"),
            url=entry.get("url", ""),
            headers=req_headers if isinstance(req_headers, dict) else {},
            body=entry.get("request_body", "") or "",
        )
        try:
            from pentool.utils.parser import build_http_request

            raw_req = build_http_request(parsed_req)
            self.query_one("#ws-req-editor", HttpView).load_raw_http(raw_req)
        except Exception:
            # The WS frame's request panel still holds the previous frame — that is,
            # it shows someone else's request under the selected row.
            logger.warning("proxy: WS request panel not filled", exc_info=True)

        resp_headers = entry.get("response_headers") or {}
        status = entry.get("status_code")
        resp_body = entry.get("response_body", "") or ""
        try:
            view = self.query_one("#ws-resp-viewer", HttpView)
            if status is not None:
                headers_text = "\r\n".join(
                    f"{k}: {v}" for k, v in (resp_headers if isinstance(resp_headers, dict) else {}).items()
                )
                raw = f"HTTP/1.1 {status}\r\n{headers_text}\r\n\r\n{resp_body}"
                view.load_raw_http(raw)
            else:
                view.load_raw_http("(no response)")
        except Exception:
            # Same problem on the other side: the response panel keeps a foreign
            # response, and the difference from the selected frame is unexplained.
            logger.warning("proxy: WS response panel not filled", exc_info=True)

    def on_data_table_header_selected(self, event: DataTable.HeaderSelected) -> None:
        order_by_map = {
            "ID": "id",
            "Host": "host",
            "Method": "method",
            "URL": "url",
            "Status": "status_code",
            "Size": "length",
            "Time": "timestamp",
        }
        if event.data_table.id == "ws-request-list":
            self._sort_table_sql(
                event,
                _COL_NAMES,
                order_by_map=order_by_map,
                reload_cb=lambda order_by, order_dir: self._reload_ws_table(
                    filters=self._ws_current_filters,
                    order_by=order_by,
                    order_dir=order_dir,
                ),
            )
        else:
            self._sort_table_sql(
                event,
                _COL_NAMES,
                order_by_map=order_by_map,
                reload_cb=lambda order_by, order_dir: self._reload_table(
                    filters=self._current_filters,
                    order_by=order_by,
                    order_dir=order_dir,
                ),
            )

    def on_proxy_filter_bar_filter_changed(self, event: FilterBar.FilterChanged) -> None:
        """HTTP History filter changed → reload."""
        spec = event.spec if event.spec and not event.spec.is_empty else None
        self._current_filters = spec
        self.run_worker(self._reload_table(spec))

    def on_ws_filter_bar_filter_changed(self, event: WsFilterBar.FilterChanged) -> None:
        """WS History filter changed → reload."""
        spec = event.spec if event.spec and not event.spec.is_empty else None
        self._ws_current_filters = spec
        self.run_worker(self._reload_ws_table(spec))

    def action_toggle_inspector(self) -> None:
        self._inspector_visible = not self._inspector_visible
        try:
            panel = self.query_one("#inspector-panel", InspectorPanel)
            if self._inspector_visible:
                panel.add_class("-visible")
            else:
                panel.remove_class("-visible")
        except NoMatches as exc:
            # The flag is already toggled but the panel is not: the next click flips
            # the flag back and panel and state diverge for good. `NoMatches` — the
            # panel is not in the tree (the tab is not mounted).
            logger.debug("proxy: inspector panel not toggled: %s", exc)

    def _switch_proxy_tab(self, tab_id: str) -> None:
        """Switch to a Proxy tab and focus the table."""
        try:
            from textual.widgets import TabbedContent

            tabs = self.query_one(TabbedContent)
            tabs.active = tab_id
            # Focus the DataTable in the target tab
            self.call_after_refresh(self._focus_tab_table, tab_id)
            # Reload the table if switching to HTTP History — rows may have
            # accumulated in _rows_cache while the table was off-screen and
            # query_one("#request-list") was failing (TabPane hidden = widget
            # not in DOM). Without this, cached rows never appear.
            if tab_id == "tab-http-history":
                self.call_after_refresh(self._reload_http_history_on_switch)
        except Exception as exc:
            # The tab hotkey was pressed but the tab did not switch — exactly what
            # the user describes as "the key does not work".
            logger.debug("proxy: switch to tab %s failed: %s", tab_id, exc)

    def _reload_http_history_on_switch(self) -> None:
        """Rebuild the backend from _rows_cache when switching to HTTP History."""
        try:
            table = self.query_one("#request-list", DataTable)
            if not self._rows_cache:
                return
            import pentool.tui.screens.proxy.screen as _ps

            arrow = _ps._rows_to_arrow(self._rows_cache)
            table.set_data(arrow)  # set_data already resets caches and dimensions
            if self._rows_cache:
                table.scroll_end(animate=False)
        except Exception:
            # The table keeps its old contents even though rows are in the cache —
            # exactly the case this method was written to fix.
            logger.error("proxy: HTTP history not rebuilt on tab switch", exc_info=True)

    def _focus_tab_table(self, tab_id: str) -> None:
        try:
            from textual.widgets import DataTable
            from textual_fastdatatable import DataTable as FastDT

            pane = self.query_one(f"#{tab_id}")
            for cls in (FastDT, DataTable):
                try:
                    table = pane.query_one(cls)
                    table.focus()
                    return
                except Exception as exc:
                    # Normal case: the Intercept tab has no table at all. The log
                    # entry is there to tell this apart from a typo in the class.
                    logger.debug("proxy: no %s in #%s: %s", cls.__name__, tab_id, exc)
        except Exception as exc:
            # No such tab — focus stays where it was.
            logger.debug("proxy: pane #%s not found for focusing: %s", tab_id, exc)

    def action_focus_tab_history(self) -> None:
        """Switch to HTTP History."""
        self._switch_proxy_tab("tab-http-history")

    def action_focus_tab_intercept(self) -> None:
        """Switch to Intercept."""
        self._switch_proxy_tab("tab-intercept")

    def action_focus_tab_ws(self) -> None:
        """Switch to WS History."""
        self._switch_proxy_tab("tab-ws-history")

    def _show_context_menu_at_cursor(self) -> None:
        try:
            table = self.query_one("#request-list", DataTable)
            r = table.region
            x = r.x + 2
            y = r.y + 1 + table.cursor_row
        except NoMatches as exc:
            # The menu opens in the corner instead of at the row — noticeable, but
            # without the log entry the cause cannot be reconstructed.
            logger.debug("proxy: context menu position unknown, using default: %s", exc)
            x, y = 10, 5
        self._open_context_menu(x, y)

    def action_send_to_repeater(self) -> None:
        if self._selected_req_id is None:
            return
        self.run_worker(self._do_send_to("repeater"))

    def action_copy_url(self) -> None:
        """Copy selected request URL to clipboard."""
        self._copy_selected_url()

    def action_open_in_browser(self) -> None:
        """Open selected URL in Lightpanda viewer."""
        logger.info("action_open_in_browser: req_id=%s", self._selected_req_id)
        try:
            self._open_in_lightpanda()
        except Exception as exc:
            logger.error("action_open_in_browser crashed: %s", exc, exc_info=True)

    def action_context_menu(self) -> None:
        """Show context menu for selected row."""
        self._show_context_menu_at_cursor()

    def action_send_to_scanner(self) -> None:
        """Send selected request to Scanner."""
        host = self._get_selected_host_sync()
        if host:
            from pentool.tui.messages import SendHostToScanner

            self.app.post_message(SendHostToScanner(host))

    def action_hide_detail(self) -> None:
        """Hide/close the request inspector detail panel."""
        self.action_toggle_inspector()

    def _send_to_intruder(self) -> None:
        if self._selected_req_id is None:
            return
        self.run_worker(self._do_send_to("intruder"))

    async def _do_send_to(self, target: str) -> None:
        if self._proxy_service is None or not self._proxy_service.is_storage_ready() or self._selected_req_id is None:
            return
        entry = await self._proxy_service.get_full_entry(self._selected_req_id)
        if entry is None:
            return
        from pentool.utils.parser import ParsedRequest, build_http_request

        parsed = ParsedRequest(
            method=entry.get("method", "GET"),
            url=entry.get("url", ""),
            headers=entry.get("request_headers") or {},
            body=entry.get("request_body", "") or "",
        )
        raw = build_http_request(parsed)
        self._auto_add_host_to_target(parsed.url)
        if target == "repeater":
            self.app.post_message(SendToRepeater(raw))
        elif target == "intruder":
            self.app.post_message(SendToIntruder(raw))

    def _auto_add_host_to_target(self, url: str) -> None:
        """Automatically add the host from a URL to the Target sitemap."""
        try:
            from pentool.utils.parser import ParsedRequest

            parsed = ParsedRequest(method="GET", url=url, headers={}, body="")
            from pentool.tui.messages import SendToTarget

            self.app.post_message(SendToTarget(parsed))  # type: ignore[attr-defined]
        except Exception as exc:
            # The host never reached the sitemap — the user does not expect it and
            # will not see it either; the log entry explains why Target is empty.
            logger.debug("proxy: host not auto-added to Target: %s", exc)

    def _open_in_lightpanda(self) -> None:
        """Open selected URL in Lightpanda viewer modal."""
        if self._selected_req_id is None:
            return
        self.run_worker(self._do_lightpanda())

    async def _do_lightpanda(self) -> None:
        parsed = await self._get_selected_parsed()
        if parsed is None or not parsed.url:
            return
        from pentool.tui.dialogs.lightpanda_viewer import LightpandaViewer

        self.app.push_screen(LightpandaViewer(parsed.url))

    def _copy_selected_url(self) -> None:
        if self._selected_req_id is None:
            return
        self.run_worker(self._do_copy_url())

    async def _do_copy_url(self) -> None:
        parsed = await self._get_selected_parsed()
        if parsed is None:
            return
        from pentool.utils.copy_as import copy_to_clipboard

        ok = copy_to_clipboard(parsed.url)
        if ok:
            self.app.notify("URL copied", timeout=2)
        else:
            self.app.notify("Could not copy to clipboard", severity="warning", timeout=3)

    async def _get_selected_parsed(self):
        if self._selected_req_id is None or self._proxy_service is None or not self._proxy_service.is_storage_ready():
            return None
        entry = await self._proxy_service.get_full_entry(self._selected_req_id)
        if entry is None:
            return None
        from pentool.utils.parser import ParsedRequest

        return ParsedRequest(
            method=entry.get("method", "GET"),
            url=entry.get("url", ""),
            headers=entry.get("request_headers") or {},
            body=entry.get("request_body", "") or "",
        )

    def _copy_as(self, action: str) -> None:
        self.run_worker(self._do_copy_as(action))

    async def _do_copy_as(self, action: str) -> None:
        parsed = await self._get_selected_parsed()
        if parsed is None:
            return
        from pentool.utils.copy_as import (
            copy_as_curl,
            copy_as_fetch,
            copy_as_ffuf,
            copy_as_jwt_tool,
            copy_as_nmap,
            copy_as_sqlmap,
            copy_to_clipboard,
        )

        if action == "copy_curl":
            text, label = copy_as_curl(parsed), "curl"
        elif action == "copy_fetch":
            text, label = copy_as_fetch(parsed), "fetch()"
        elif action == "copy_ffuf":
            text, label = copy_as_ffuf(parsed), "ffuf"
        elif action == "copy_sqlmap":
            text, label = copy_as_sqlmap(parsed), "sqlmap"
        elif action == "copy_nmap":
            text, label = copy_as_nmap(parsed), "nmap"
        elif action == "copy_jwt":
            text, label = copy_as_jwt_tool(parsed), "jwt_tool"
        else:
            return
        ok = copy_to_clipboard(text)
        if ok:
            self.app.notify(f"Copied as {label}", timeout=2)
        else:
            self.app.notify(f"Clipboard unavailable. {label}:\n{text[:80]}", severity="warning", timeout=5)

    def _open_in_browser(self) -> None:
        self.run_worker(self._do_open_in_browser())

    async def _do_open_in_browser(self) -> None:
        parsed = await self._get_selected_parsed()
        if parsed is None:
            return
        from pentool.utils.copy_as import open_in_browser

        url = parsed.url
        if url:
            open_in_browser(url)
            self.app.notify(f"Opening: {url[:60]}", timeout=2)

    def _save_request_txt(self) -> None:
        self.run_worker(self._do_save_request_txt())

    async def _do_save_request_txt(self) -> None:
        parsed = await self._get_selected_parsed()
        if parsed is None:
            self.app.notify("No request selected", severity="warning", timeout=3)
            return
        from pentool.utils.copy_as import save_request_txt

        path = os.path.expanduser("~/request.txt")
        try:
            save_request_txt(parsed, path)
            self.app.notify(f"Saved to {path}", timeout=3)
        except Exception as exc:
            # The notification shows the reason to the user, but the journal never
            # had it — and the journal is what people read to find "where did it save".
            logger.warning("proxy: request not saved to file", exc_info=True)
            self.app.notify(f"Save failed: {exc}", severity="error", timeout=4)

    def _delete_selected_request(self) -> None:
        self.run_worker(self._do_delete_selected())

    async def _do_delete_selected(self) -> None:
        if self._selected_req_id is None or self._proxy_service is None:
            return
        try:
            await self._proxy_service.delete_request(self._selected_req_id)
            self._selected_req_id = None
            await self._reload_table(self._current_filters)
        except Exception as exc:
            logger.error("Delete failed: %s", exc)

    def _load_entry_details(self, entry: dict) -> None:
        # Second layer of the selection race guard: the deferred paint may
        # run after the user has already moved to another row, so re-check
        # that this entry still matches the current selection before drawing.
        entry_id = entry.get("id")
        if self._selected_req_id is not None and entry_id is not None and entry_id != self._selected_req_id:
            return
        from pentool.utils.parser import ParsedRequest, ParsedResponse

        req_headers = entry.get("request_headers") or {}
        parsed_req = ParsedRequest(
            method=entry.get("method", "GET"),
            url=entry.get("url", ""),
            headers=req_headers if isinstance(req_headers, dict) else {},
            body=entry.get("request_body", "") or "",
        )

        try:
            from pentool.utils.parser import build_http_request

            raw_req = build_http_request(parsed_req)
            self.query_one("#req-editor", HttpView).load_raw_http(raw_req)
        except Exception:
            # The editor keeps the previous request — so under the selected row a
            # foreign one is shown. The worst of the silent outcomes here.
            logger.warning("proxy: request panel not filled for entry %s", entry_id, exc_info=True)

        # Comment is no longer shown in a persistent field — stash it so the
        # "View/Edit Comment" dialog (opened via context menu or 💬 click)
        # has the current value without a re-query.
        self._current_comment = entry.get("comment", "") or ""

        resp_headers = entry.get("response_headers") or {}
        status = entry.get("status_code")
        resp_body = entry.get("response_body", "") or ""
        try:
            view = self.query_one("#resp-viewer", HttpView)
            if status is not None:
                headers_text = "\r\n".join(
                    f"{k}: {v}" for k, v in (resp_headers if isinstance(resp_headers, dict) else {}).items()
                )
                raw = f"HTTP/1.1 {status}\r\n{headers_text}\r\n\r\n{resp_body}"
                view.load_raw_http(raw)
            else:
                view.load_raw_http("(no response)")
        except Exception:
            # Same asymmetry as with the request: the response panel keeps a foreign one.
            logger.warning("proxy: response panel not filled for entry %s", entry_id, exc_info=True)

        try:
            panel = self.query_one("#inspector-panel", InspectorPanel)
            parsed_resp_for_inspector = None
            if status is not None:
                parsed_resp_for_inspector = ParsedResponse(
                    status=status,
                    headers=resp_headers if isinstance(resp_headers, dict) else {},
                    body=resp_body,
                )
            panel.load(parsed_req, parsed_resp_for_inspector)
        except Exception:
            # The inspector shows the analysis of the previous row — with the panel
            # open that is outright misleading.
            logger.warning("proxy: inspector not loaded for entry %s", entry_id, exc_info=True)

    def action_load_history(self) -> None:
        self.run_worker(self._reload_table(self._current_filters))

    def action_toggle_proxy(self) -> None:
        proxy = self._get_proxy()
        # Instant feedback in the header — before the thread actually starts or
        # stops. The label lives in the header spec now, so the state is a field
        # on the screen and `refresh_header()` repaints it.
        if proxy and not proxy.is_running:
            self._proxy_transition = "starting"
        elif proxy and proxy.is_running:
            self._proxy_transition = "stopping"
        self._refresh_header_now()
        self.app.action_toggle_proxy()  # type: ignore[attr-defined]
        self.call_after_refresh(self._sync_proxy_button)

    def action_clear_list(self) -> None:
        proxy = self._get_proxy()
        if proxy:
            proxy.clear_requests()
        self.run_worker(self._do_clear_table())
        try:
            self.query_one("#req-editor", HttpView).clear()
            self.query_one("#resp-viewer", HttpView).clear()
        except NoMatches as exc:
            # History cleared but the panels still show a request that no longer exists.
            logger.debug("proxy: detail panels not cleared with history: %s", exc)
        self._selected_req_id = None
        self._selected_ws_req_id = None

    async def _do_clear_table(self) -> None:
        if self._proxy_service is not None and self._proxy_service.is_storage_ready():
            await self._proxy_service.clear_history()
        # Also drop retained ProxyRequestCaptured/Completed metadata from the
        # EventBus ring buffer — otherwise "Clear" empties the visible table
        # but old request records linger in bus._history until they age out
        # naturally (up to max_history=10_000 entries later).
        try:
            from pentool.core.event_bus import get_event_bus
            from pentool.core.events import ProxyRequestCaptured, ProxyRequestCompleted

            get_event_bus().clear_history((ProxyRequestCaptured, ProxyRequestCompleted))
        except Exception as exc:
            logger.debug("PROXY SCREEN: _do_clear_table: EventBus history purge failed: %s", exc)
        self._rows_cache = []
        self._current_filters = None
        self._history_total = 0
        self._history_oldest_offset = 0
        try:
            table = self.query_one("#request-list", DataTable)
            table.clear_data()
            table.refresh()
        except Exception as exc:
            # Cache and counter are zeroed but the table is not: it will show rows
            # that no longer exist, with no way to notice it.
            logger.debug("proxy: table not cleared with history: %s", exc)
        self._update_history_count_label()

    def action_toggle_enforce_scope(self) -> None:
        """Toggle the 'Skip out-of-scope' capture filter (per-project, persisted to DB)."""
        proxy = self._get_proxy()
        if proxy is None:
            return
        enabled = not proxy.enforce_scope
        proxy.set_enforce_scope(enabled)
        # Pass `enabled` explicitly instead of letting _sync_enforce_scope_button
        # re-read proxy.enforce_scope — set_enforce_scope() defers the actual
        # attribute write via call_soon_threadsafe onto the proxy's own event
        # loop (a different thread) when the proxy is running, so reading it
        # back immediately here could still see the OLD value. That's what
        # made the button's checkbox lag one click behind the real state:
        # click 1 flips the real flag (eventually) but the button re-read the
        # stale value and showed unchecked; click 2 then showed the PREVIOUS
        # click's real state while flipping the flag again for next time.
        self._sync_enforce_scope_button(enabled)
        self.run_worker(self._save_enforce_scope_setting(enabled))
        if enabled and not proxy.scope:
            # Scope host list is empty — is_in_scope() treats an empty list as
            # "everything matches", so there is nothing to tunnel yet. Without
            # this, turning the toggle on looks like it silently does nothing.
            self.app.notify(
                "Skip out-of-scope: ON, but Scope has no hosts yet — "
                "everything still counts as in-scope. Add hosts via the "
                "'Scope' button to actually filter traffic.",
                severity="warning",
                timeout=5,
            )
        else:
            self.app.notify(
                (
                    "Skip out-of-scope: ON — non-scope traffic will be tunneled, not captured"
                    if enabled
                    else "Skip out-of-scope: OFF — all traffic is captured regardless of Scope"
                ),
                timeout=3,
            )

    async def _save_enforce_scope_setting(self, enabled: bool) -> None:
        """Save enforce-scope flag per-project (DB)."""
        try:
            from pentool.core.db_schema import set_project_setting

            db_path = self._get_db_path()
            if db_path:
                await set_project_setting(db_path, "proxy.enforce_scope", "1" if enabled else "0")
        except Exception:
            logger.warning("_save_enforce_scope_setting: setting not saved", exc_info=True)

    async def _save_scope_setting(self, hosts: list[str]) -> None:
        """Save scope host list per-project."""
        try:
            from pentool.core.db_schema import set_project_setting

            db_path = self._get_db_path()
            if db_path:
                await set_project_setting(db_path, "proxy.scope", json.dumps(hosts))
        except Exception:
            logger.warning("_save_scope_setting: scope not saved", exc_info=True)

    async def _load_scope_setting(self, is_new: bool = False) -> None:
        """Load persisted scope for the current project."""
        proxy = self._get_proxy()
        if proxy is None:
            return
        hosts: list[str] | None = None
        try:
            from pentool.core.db_schema import get_project_setting

            db_path = self._get_db_path()
            raw = await get_project_setting(db_path, "proxy.scope", None) if db_path else None
            if raw is not None:
                hosts = json.loads(raw)
        except Exception:
            logger.warning("_load_scope_setting: scope not read", exc_info=True)
            hosts = None
        if hosts is None and not is_new:
            try:
                from pentool.core.config import get_config

                hosts = list(get_config().scope)
            except Exception:  # logging-ok: a new project has no scope setting — this is expected
                # The project has no scope setting yet and the global config is
                # unavailable — then the scope really is empty. The log entry tells
                # this apart from a failure.
                logger.debug("proxy: global scope not available")
                hosts = []
        if hosts is None:
            hosts = []
        logger.info("PROXY: load_scope_setting -> %d host(s)", len(hosts))
        proxy.set_scope(hosts)
        try:
            from pentool.tui.widgets.proxy_filter_bar import ProxyFilterBar
            from pentool.tui.widgets.toolbar_button import ToolbarButton

            filter_bar = self.query_one("#filter-bar", ProxyFilterBar)
            st = filter_bar.query_one("#fb-scope", ToolbarButton)
            if hosts:
                st.remove_class("disabled")
            else:
                st.add_class("disabled")
        except Exception:
            # The Scope button will show the wrong state (disabled while scope is
            # populated) — the most annoying of the small symptoms.
            logger.warning("proxy: scope toggle not synced", exc_info=True)

    async def _load_enforce_scope_setting(self) -> None:
        """Load persisted 'skip out-of-scope' flag for the current project."""
        proxy = self._get_proxy()
        if proxy is None:
            return
        enabled: bool = False
        try:
            from pentool.core.db_schema import get_project_setting

            db_path = self._get_db_path()
            raw = await get_project_setting(db_path, "proxy.enforce_scope", None) if db_path else None
            if raw is not None:
                enabled = json.loads(raw)
        except Exception:
            # The flag stays OFF. That is the safe outcome (no filtering), but it is
            # exactly why a read failure is easily mistaken for "no setting saved".
            logger.warning("proxy: enforce_scope setting not read", exc_info=True)
        logger.info("PROXY: load_enforce_scope_setting -> enforce=%s", enabled)
        proxy.set_enforce_scope(enabled)
        if enabled:
            self._sync_enforce_scope_button(True)

    def _sync_enforce_scope_button(self, enabled: bool | None = None) -> None:
        """Repaint the Skip-out-of-scope state in the header.

        Kept as a method (and named like before) because several call sites —
        project switch, settings load, toolbar action — still call it; the state
        itself is read from the proxy inside `header_spec()`.
        """
        self._refresh_header_now()

    def action_open_mr(self) -> None:
        proxy = self._get_proxy()
        rules = proxy.match_replace_rules if proxy else []
        from pentool.tui.dialogs.match_replace_dialog import MatchReplaceDialog

        def _apply(result: list[MatchReplaceRule] | None) -> None:
            if result is not None and proxy is not None:
                proxy.match_replace_rules = result

        self.app.push_screen(MatchReplaceDialog(rules), _apply)

    def action_open_ca_cert(self) -> None:
        from pentool.core.config import get_config
        from pentool.tui.dialogs.cert_dialog import CertInstallDialog

        ca_path = str(get_config().cert_dir) + "/ca.crt"
        self.app.push_screen(CertInstallDialog(ca_path))

    def _sync_proxy_button(self) -> None:
        """Repaint the proxy state in the header (label + counter come from the spec)."""
        self._proxy_transition = ""
        self._refresh_header_now()

    def update_proxy_label(self, running: bool, port: int) -> None:
        self._sync_proxy_button()

    def update_intercept_label(self, enabled: bool) -> None:
        self._sync_intercept_button()

    # IDs of containers belonging to text panels (Request/Response)
    _TEXT_PANEL_IDS = frozenset(
        {
            "req-panel",
            "resp-panel",
            "ws-req-panel",
            "ws-resp-panel",
            "req-editor",
            "resp-viewer",
            "ws-req-editor",
            "ws-resp-viewer",
            "intercept-editor",
            "intercept-sent-req",
            "intercept-resp-viewer",
            "intercept-req-area",
            "intercept-sent-panel",
            "intercept-resp-panel",
            # internal HttpView widgets
            "http-headers",
            "http-body",
        }
    )

    def _is_in_text_panel(self, widget) -> bool:
        """Check whether the widget or one of its ancestors is a text panel."""
        try:
            from pentool.tui.widgets.request_editor import HttpView

            node = widget
            while node is not None and node is not self:
                nid = getattr(node, "id", None) or ""
                if nid in self._TEXT_PANEL_IDS:
                    return True
                # HttpView — always a text panel
                if isinstance(node, HttpView):
                    return True
                node = getattr(node, "parent", None)
        except Exception as exc:
            # False means "not a text editor" — so the hotkey goes to the widget
            # instead of typing a character.
            logger.debug("proxy: _is_in_text_panel failed: %s", exc)
        return False

    def on_proxy_data_table_context_menu_request(self, event: ProxyDataTable.ContextMenuRequest) -> None:
        """Context menu for the HTTP History row under the pointer (Ctrl+click / right-click)."""
        try:
            table = self.query_one("#request-list", DataTable)
            cursor_row = table.cursor_row
            if 0 <= cursor_row < len(self._rows_cache):
                self._selected_req_id = self._rows_cache[cursor_row].get("id")
        except NoMatches as exc:
            # The menu opens, but its actions will be applied to the wrong row —
            # not the one the user clicked: the table is not in the tree (the
            # history tab is not mounted).
            logger.debug("proxy: cursor row not resolved for context menu: %s", exc)
        self._open_context_menu(event.screen_x, event.screen_y)

    def on__base_http_widget_context_menu_request(self, event) -> None:
        """Ctrl+click / right-click on any _BaseHttpWidget → context menu."""
        self.cm_open_text_menu(event.screen_x, event.screen_y)

    def on_mouse_down(self, event) -> None:
        # Right-click (button=3) or Ctrl+left — context menu
        if not ((event.button == 3) or (event.button == 1 and event.ctrl)):
            return

        widget = event.widget

        if self._is_in_text_panel(widget):
            # Click in Request / Response area → text menu
            self.cm_open_text_menu(event.screen_x, event.screen_y)
            event.stop()
            return

        # Click in DataTable (#request-list) — handled via
        # on_proxy_data_table_context_menu_request, so here
        # we only open the menu if the event did NOT come from the table
        try:
            table = self.query_one("#request-list", DataTable)
            node = widget
            while node is not None:
                if node is table:
                    # This event is from DataTable — ignore it (ContextMenuRequest handles it)
                    return
                node = getattr(node, "parent", None)
        except NoMatches as exc:
            # Could not tell whose click this was — the menu opens as a table menu
            # even over a text panel. `NoMatches` — the table is not in the tree.
            logger.debug("proxy: click source not resolved: %s", exc)
        # Click outside text panel and DataTable — open the table context menu
        self._open_context_menu(event.screen_x, event.screen_y)
        event.stop()

    def on_click(self, event) -> None:
        # Double-click — load details into Request/Response panels
        if event.chain == 2:
            try:
                table = self.query_one("#request-list", DataTable)
                self._select_row(table.cursor_row)
            except NoMatches as exc:
                # Double-clicking a row opened nothing: the user will try again and
                # it will look like a hang. The cause — the table is not in the tree,
                # i.e. the History tab is not mounted.
                logger.debug("proxy: double-click did not open row details: %s", exc)

    def _open_context_menu(self, x: int, y: int) -> None:
        """Context menu for a row in the HTTP History table."""
        selected_host = self._get_selected_host_sync()
        proxy = self._get_proxy()
        in_scope = proxy.is_in_scope(selected_host) if (proxy and selected_host) else False
        scope_is_empty = not bool(proxy.scope) if proxy else True

        items = [
            ("send_repeater", "Send to Repeater"),
            ("send_intruder", "Send to Intruder"),
            ("send_scanner", "Send to Scanner"),
            ("-", ""),
            ("mark_req", "Mark color"),
            ("edit_comment", "View/Edit Comment"),
            ("-", ""),
        ]
        if selected_host and not in_scope:
            items.append(("add_scope", f"Add {selected_host} to Scope"))
        elif selected_host and in_scope and not scope_is_empty:
            items.append(("remove_scope", f"Remove {selected_host} from Scope"))
        else:
            items.append(("add_scope", "Add to Scope"))
        items += [
            ("-", ""),
            ("delete_req", "Delete"),
        ]

        self.app.show_context_menu(items, x, y, callback=self._on_ctx_action)

    # ── RequestContextMenuMixin impl ──────────────────────────────────────────

    def _cm_get_raw_request(self) -> str:
        """Raw HTTP from the Request panel (HttpView#req-editor → TextArea#http-body)."""
        try:
            from textual.widgets import TextArea

            view = self.query_one("#req-editor", HttpView)
            area = view.query_one("#http-body", TextArea)
            return area.text or ""
        except NoMatches as exc:
            # Return an "empty request" — the caller sends it as is, so Repeater
            # receives a blank instead of the selected request.
            logger.debug("proxy: request text not read: %s", exc)
            return ""

    def _get_selected_host_sync(self) -> str:
        """Synchronously get the host of the selected request from the cache."""
        # First search by cursor_row (more up-to-date than _selected_req_id)
        try:
            table = self.query_one("#request-list", DataTable)
            row_idx = table.cursor_row
            if 0 <= row_idx < len(self._rows_cache):
                host = str(self._rows_cache[row_idx].get("host", ""))
                if host:
                    return host
        except Exception as exc:
            # There is a fallback by _selected_req_id below — silence here would
            # hide that the primary path stopped working.
            logger.debug("proxy: host by cursor row unavailable: %s", exc)
        # Fallback — look up by _selected_req_id
        if self._selected_req_id is None or not self._rows_cache:
            return ""
        for row in self._rows_cache:
            if row.get("id") == self._selected_req_id:
                return str(row.get("host", ""))
        return ""

    def _on_ctx_action(self, action: str) -> None:
        if action == "send_repeater":
            self.action_send_to_repeater()
        elif action == "send_intruder":
            self._send_to_intruder()
        elif action == "send_decoder":
            self.app.action_switch_module("decoder")  # type: ignore[attr-defined]
        elif action == "send_scanner":
            host = self._get_selected_host_sync()
            if host:
                from pentool.tui.messages import SendHostToScanner

                self.app.post_message(SendHostToScanner(host))
        elif action == "mark_req":
            self._mark_dialog()
        elif action == "edit_comment":
            self._comment_dialog()
        elif action == "add_scope":
            self._scope_action_for_selected(add=True)
        elif action == "remove_scope":
            self._scope_action_for_selected(add=False)
        elif action in ("copy_curl", "copy_ffuf", "copy_sqlmap", "copy_nmap", "copy_jwt"):
            self._copy_as(action)
        elif action == "save_req_txt":
            self._save_request_txt()
        elif action == "delete_req":
            self._delete_selected_request()

    def _scope_action_for_selected(self, add: bool) -> None:
        """Add or remove the selected request's host from scope."""
        if self._selected_req_id is None:
            return
        self.run_worker(self._do_scope_action(add))

    async def _do_scope_action(self, add: bool) -> None:
        if self._proxy_service is None or not self._proxy_service.is_storage_ready() or self._selected_req_id is None:
            return
        entry = await self._proxy_service.get_full_entry(self._selected_req_id)
        if entry is None:
            return
        url = entry.get("url", "")
        try:
            host = urlparse(url).netloc or urlparse(url).path.split("/")[0]
        except Exception:
            host = url
        if not host:
            return
        proxy = self._get_proxy()
        if proxy is None:
            return
        scope = list(proxy.scope)
        if add:
            if host not in scope:
                scope.append(host)
                proxy.set_scope(scope)
                self.app.notify(f"★ {host} added to scope", severity="information", timeout=2)
                self._sync_target_host_scope(host, True)
            else:
                self.app.notify(f"{host} is already in scope", timeout=2)
        else:
            if host in scope:
                scope.remove(host)
                proxy.set_scope(scope)
                self.app.notify(f"{host} removed from scope", severity="information", timeout=2)
                self._sync_target_host_scope(host, False)
            else:
                self.app.notify(f"{host} is not in scope", timeout=2)
        # Persist per-project (DB) so it survives a project switch, plus
        # mirror into the global Config as the last-used fallback — same
        # two writes as action_open_scope._apply.
        await self._save_scope_setting(list(proxy.scope))
        try:
            from pentool.core.config import get_config

            cfg = get_config()
            cfg.scope = list(proxy.scope)
            cfg.save()
        except Exception as e:
            logger.warning("_do_scope_action: failed to save scope to config: %s", e)
        # Update ★ Scope button state in FilterBar
        try:
            from pentool.tui.widgets.proxy_filter_bar import ProxyFilterBar
            from pentool.tui.widgets.toolbar_button import ToolbarButton

            st = self.query_one("#filter-bar", ProxyFilterBar).query_one("#fb-scope", ToolbarButton)
            if scope:
                st.remove_class("disabled")
            else:
                st.add_class("disabled")
        except Exception as exc:
            # The Scope button will diverge from the real host list: the host was
            # just added, yet the button still reads "unavailable".
            logger.debug("proxy: scope button not synced after action: %s", exc)

    def _sync_target_host_scope(self, host: str, in_scope: bool) -> None:
        self.app.post_message(SyncScopeToTarget(host, in_scope))  # type: ignore[attr-defined]

    # ── Colors available for marking requests ─────────────────────────────────

    _COLOR_OPTIONS: list[tuple[str, str]] = [
        ("🔴 Red", "red"),
        ("🟠 Orange", "orange"),
        ("🟡 Yellow", "yellow"),
        ("🟢 Green", "green"),
        ("🔵 Blue", "blue"),
        ("🟣 Purple", "purple"),
        ("⬜ Clear", ""),
    ]

    def _mark_dialog(self) -> None:
        """Show color picker for the selected request.

        Variant A: color IS the tag — picking a color writes both `color`
        and `tags` (tag name == color name) in one action, so the mark can
        be filtered on (ColorFilterDots in FilterBar) and shown as a dot.
        """
        req_id = self._selected_req_id
        if not req_id:
            return
        from pentool.tui.dialogs.color_pick import ColorPickScreen

        def _on_color(color: str | None) -> None:
            if color is not None:
                self.run_worker(self._mark_request(req_id, color))

        self.app.push_screen(ColorPickScreen(), _on_color)

    async def _mark_request(self, request_id: int, color: str) -> None:
        """Set color mark for request — color is written to BOTH `color`
        and `tags` columns so it doubles as a filterable tag (variant A).
        """
        try:
            if self._proxy_service:
                await self._proxy_service.update_color(request_id, color)
                # Color IS the tag: replace any previous color-tag with the
                # new one, keeping the color name as the sole tag value.
                await self._proxy_service.update_tags(request_id, color)
                label = next((name for name, value in self._COLOR_OPTIONS if value == color), color)
                msg = f"Marked: {label}" if color else "Mark cleared"
                self.notify(msg, timeout=2)
                # Update cache
                for row in self._rows_cache:
                    if row.get("id") == request_id:
                        row["color"] = color
                        row["tags"] = color
                        break
                # Visual update: rebuild table to show color dot in Host column
                await self._reload_table(self._current_filters)
        except Exception as exc:
            logger.error("Failed to mark request: %s", exc)

    def _comment_dialog(self, initial_comment: str | None = None) -> None:
        """Show comment edit modal (on-demand, context-menu or click).

        Picks the correct req_id depending on the active tab:
        - HTTP History tab → self._selected_req_id
        - WS History tab   → self._selected_ws_req_id
        """
        from textual.widgets import TabbedContent

        tabs = self.query_one(TabbedContent)
        req_id = self._selected_ws_req_id if tabs.active == "tab-ws-history" else self._selected_req_id
        if not req_id:
            return
        from pentool.tui.dialogs.comment_dialog import CommentDialog

        initial_comment = initial_comment if initial_comment is not None else self._current_comment

        def _on_comment(comment: str | None) -> None:
            if comment is not None:
                self.run_worker(self._save_comment(req_id, comment))

        self.app.push_screen(CommentDialog(initial_comment), _on_comment)

    async def _save_comment(self, request_id: int, comment: str) -> None:
        """Save comment to database."""
        try:
            if self._proxy_service:
                await self._proxy_service.update_comment(request_id, comment)
            logger.info("PROXY: Comment saved for request %d", request_id)
            if request_id == self._selected_req_id:
                self._current_comment = comment
            # Keep cache in sync so the list-row indicator (💬) updates
            # immediately, same as _mark_request does for color/tags.
            for row in self._rows_cache:
                if row.get("id") == request_id:
                    row["comment"] = comment
                    break
            # Visual update: rebuild table so the 💬 marker in Host shows up
            # right away instead of only after the next reload/restart.
            await self._reload_table(self._current_filters)
            self.app.notify("Comment saved" if comment else "Comment cleared", timeout=2)
        except Exception:
            logger.error("proxy: comment not saved", exc_info=True)

    def on_context_menu_item_selected(self, event: ContextMenu.ItemSelected) -> None:
        self._on_ctx_action(event.action)

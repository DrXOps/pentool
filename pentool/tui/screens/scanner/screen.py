"""Scanner screen — passive and active vulnerability scanning."""

from __future__ import annotations

import time
from urllib.parse import urlparse, urlunparse
from datetime import datetime

from textual import on, work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.widget import Widget
from pathlib import Path

_CSS = (Path(__file__).parent / "screen.tcss").read_text(encoding="utf-8")
from textual.widgets import (
    Checkbox,
    Input,
    Label,
    ProgressBar,
    RichLog,
    Static,
    TabPane,
    TabbedContent,
    TextArea,
)
import pyarrow as pa
from textual_fastdatatable import DataTable
from textual_fastdatatable.backend import ArrowBackend

from pentool.core.logging import get_logger
from pentool.tui.widgets.toolbar_button import ToolbarButton
from pentool.tui.widgets.request_editor import HttpView
from pentool.tui.widgets.resize_handle import ResizeHandle
from pentool.tui.mixins.request_context_menu import RequestContextMenuMixin
from pentool.tui.screens.base import BaseModuleScreen

logger = get_logger(__name__)

class _ScanTabState:
    """State of a single Scanner tab."""

    def __init__(self, tab_id: str, name: str) -> None:
        self.tab_id = tab_id
        self.name = name
        # Scan data
        self.rows: list = []
        self.row_sources: list[str] = []
        self.scanner_api = None
        # Flags
        self.scanning: bool = False
        self.stop_requested: bool = False
        self.paused: bool = False
        self.detail_panel_open: bool = False
        self.current_finding = None
        # Deferred target URL — applied in _fill_settings after the Input is mounted
        self.pending_target: str = ""
        # Original requests from Proxy/History for scanning
        self.seed_requests: list = []          # list[ParsedRequest]
        self.pending_request = None            # ParsedRequest | None, awaiting mount
        # True if the tab was opened for a new target — do not load old findings from DB
        self.skip_db_load: bool = False
        # Saved parameters (for Resume)
        self.last_targets: list[str] | None = None
        self.last_check_names: list[str] | None = None
        self.last_threads: int = 5
        # Reference to the active ScanService (for request_stop)
        self.active_service = None
        self.last_delay_sec: float = 0.0
        self.last_depth: int = 3
        self.last_pages: int = 100
        # URLs collected by the crawler — used on Resume (skips re-crawling)
        self.last_crawled_targets: list[str] = []
        # Live counters for the status panel
        self.req_sent: int = 0
        self.threads_active: int = 0
        self.req_bucket: int = 0        # requests in the current window (for req/s)
        self.req_window_start: float = 0.0
        self.req_per_sec: float = 0.0
        self._last_ui_update: float = 0.0  # throttle: at most once every 150 ms

class ScannerScreen(BaseModuleScreen, RequestContextMenuMixin):
    """Passive and active vulnerability scanning — unified screen."""

    DEFAULT_CSS = _CSS

    BINDINGS = [
        Binding("f5", "start_scan",       "Start Scan", show=False, priority=True),
        Binding("f6", "stop_scan",        "Stop",       show=False, priority=True),
        Binding("r",  "send_to_repeater", "→ Repeater", show=False, priority=True),
    ]

    # TabRenameMixin config
    _rename_input_id: str = "scan-rename-input"
    _rename_tab_prefix: str = "scan-tab-"
    _rename_tabs_widget_id: str = "scanner-tabs"

    # RequestContextMenuMixin config — Scanner: curl + browser + send to Repeater/Intruder
    _cm_show_copy_url      = True
    _cm_show_ffuf          = False
    _cm_show_sqlmap        = False
    _cm_show_jwt           = False
    _cm_show_save_txt      = False
    _cm_show_send_repeater = True
    _cm_show_send_intruder = True

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._passive_enabled = False
        # ── Tabs ─────────────────────────────────────────────────────────────
        self._tabs: list[_ScanTabState] = []
        self._tab_counter: int = 0
        self._active_tab_id: str | None = None
        # ── Double-click (state stored in TabRenameMixin) ────────────────────
        self._tab_click_time: float = 0.0
        self._tab_click_id: str | None = None
        # ── Backward compatibility (active tab properties) ───────────────────
        # Proxy to self._active_tab to avoid breaking the rest of the code

    @property
    def _active_tab(self) -> _ScanTabState | None:
        for t in self._tabs:
            if t.tab_id == self._active_tab_id:
                return t
        return None

    # ── Backward compatibility — properties delegate to the active tab ───────

    @property
    def _scanner_api(self):
        t = self._active_tab
        return t.scanner_api if t else None

    @_scanner_api.setter
    def _scanner_api(self, v):
        t = self._active_tab
        if t:
            t.scanner_api = v

    @property
    def _rows(self) -> list:
        t = self._active_tab
        return t.rows if t else []

    @_rows.setter
    def _rows(self, v: list):
        t = self._active_tab
        if t:
            t.rows = v

    @property
    def _row_sources(self) -> list:
        t = self._active_tab
        return t.row_sources if t else []

    @_row_sources.setter
    def _row_sources(self, v: list):
        t = self._active_tab
        if t:
            t.row_sources = v

    @property
    def _scanning(self) -> bool:
        t = self._active_tab
        return t.scanning if t else False

    @_scanning.setter
    def _scanning(self, v: bool):
        t = self._active_tab
        if t:
            t.scanning = v

    @property
    def _stop_requested(self) -> bool:
        t = self._active_tab
        return t.stop_requested if t else False

    @_stop_requested.setter
    def _stop_requested(self, v: bool):
        t = self._active_tab
        if t:
            t.stop_requested = v

    @property
    def _active_service(self):
        t = self._active_tab
        return t.active_service if t else None

    @_active_service.setter
    def _active_service(self, v) -> None:
        t = self._active_tab
        if t:
            t.active_service = v

    @property
    def _paused(self) -> bool:
        t = self._active_tab
        return t.paused if t else False

    @_paused.setter
    def _paused(self, v: bool):
        t = self._active_tab
        if t:
            t.paused = v

    @property
    def _detail_panel_open(self) -> bool:
        t = self._active_tab
        return t.detail_panel_open if t else False

    @_detail_panel_open.setter
    def _detail_panel_open(self, v: bool):
        t = self._active_tab
        if t:
            t.detail_panel_open = v

    @property
    def _current_finding(self):
        t = self._active_tab
        return t.current_finding if t else None

    @_current_finding.setter
    def _current_finding(self, v):
        t = self._active_tab
        if t:
            t.current_finding = v

    @property
    def _last_targets(self):
        t = self._active_tab
        return t.last_targets if t else None

    @_last_targets.setter
    def _last_targets(self, v):
        t = self._active_tab
        if t:
            t.last_targets = v

    @property
    def _last_check_names(self):
        t = self._active_tab
        return t.last_check_names if t else None

    @_last_check_names.setter
    def _last_check_names(self, v):
        t = self._active_tab
        if t:
            t.last_check_names = v

    @property
    def _last_threads(self) -> int:
        t = self._active_tab
        return t.last_threads if t else 5

    @_last_threads.setter
    def _last_threads(self, v: int):
        t = self._active_tab
        if t:
            t.last_threads = v

    @property
    def _last_delay_sec(self) -> float:
        t = self._active_tab
        return t.last_delay_sec if t else 0.0

    @_last_delay_sec.setter
    def _last_delay_sec(self, v: float):
        t = self._active_tab
        if t:
            t.last_delay_sec = v

    @property
    def _last_depth(self) -> int:
        t = self._active_tab
        return t.last_depth if t else 3

    @_last_depth.setter
    def _last_depth(self, v: int):
        t = self._active_tab
        if t:
            t.last_depth = v

    @property
    def _last_pages(self) -> int:
        t = self._active_tab
        return t.last_pages if t else 100

    @_last_pages.setter
    def _last_pages(self, v: int):
        t = self._active_tab
        if t:
            t.last_pages = v

    @property
    def _last_crawled_targets(self) -> list:
        t = self._active_tab
        return t.last_crawled_targets if t else []

    @_last_crawled_targets.setter
    def _last_crawled_targets(self, v: list):
        t = self._active_tab
        if t:
            t.last_crawled_targets = v

    def compose(self) -> ComposeResult:
        # ── Toolbar ────────────────────────────────────────────────────────────
        with Horizontal(id="toolbar"):
            yield ToolbarButton("▶ Start",       "btn-start")
            yield Static(" │ ", classes="toolbar-sep")
            yield ToolbarButton("■ Stop",        "btn-stop",         classes="disabled")
            yield Static(" │ ", classes="toolbar-sep")
            yield ToolbarButton("→ Repeater",    "btn-send-repeater",classes="disabled")
            yield Static(" │ ", classes="toolbar-sep")
            yield ToolbarButton("📄 Report",     "btn-report")
            yield Static(" │ ", classes="toolbar-sep")
            yield ToolbarButton("🔒 PRO Report", "btn-pro-report",   classes="pro-locked")
            yield Static(" │ ", classes="toolbar-sep")
            yield ToolbarButton("🗑 Clear",      "btn-clear")
            yield Static(" │ ", classes="toolbar-sep")
            yield ToolbarButton("● Passive: OFF","btn-passive")
            yield Static(" │ ", classes="toolbar-sep")
            yield ToolbarButton("⚑ False+",     "btn-fp")
            yield Static(" │ ", classes="toolbar-sep")
            yield ToolbarButton("⬇ History",    "btn-from-history")
            yield Static(" │ ", classes="toolbar-sep")
            yield ToolbarButton("➕ Tab",        "btn-new-tab")
            yield Static(" │ ", classes="toolbar-sep")
            yield ToolbarButton("➖ Tab",        "btn-close-tab")

        # ── TabbedContent — main container ──────────────────────────────────────
        with Vertical(id="scanner-tabs-area"):
            yield TabbedContent(id="scanner-tabs")

        yield Static(
            "Ctrl+J: Start  │  Ctrl+P: Pause/Resume  │  Ctrl+R: Send to Repeater"
            "  │  M: Context menu  │  Double-click tab to rename",
            id="status-bar",
        )

    # ── mount ──────────────────────────────────────────────────────────────────

    def on_mount(self) -> None:
        # Load saved tabs from DB
        self._load_tabs_from_db()

    def _load_tabs_from_db(self) -> None:
        """Load saved scanner tabs from DB on mount."""
        # Always create default tab immediately — guarantees the full widget
        # tree (_fill_results, detail panels) is mounted on the main thread.
        # Then, if a project is open, patch the target URL from saved tabs.
        self.action_new_tab()
        db_path = getattr(self.app, "db_path", None) or getattr(self.app, "_db_path", "")
        if not db_path:
            return
        from pentool.api.scanner_api import ScannerAPI
        from pentool.utils.http_client import HTTPClient
        http_client = HTTPClient(timeout=20.0, follow_redirects=True, verify_ssl=False)
        scanner_api = ScannerAPI(db_path=db_path, http_client=http_client)
        self.run_worker(self._do_load_tabs(scanner_api), exclusive=False)

    async def _do_load_tabs(self, scanner_api) -> None:
        """Async worker — restore target URLs into already-mounted tabs."""
        try:
            tabs_data = await scanner_api.get_tabs()
            if not tabs_data:
                return
            # Patch the first tab's target URL (most recent save)
            first = tabs_data[0]
            target_url = first.get("target_url", "")
            tab_name   = first.get("tab_name", "Scan")
            if target_url:
                def _apply():
                    t = self._active_tab
                    if t is None:
                        return
                    try:
                        self.query_one(f"#target-input-{t.tab_id}", Input).value = target_url
                    except Exception:
                        pass
                    try:
                        t.name = tab_name
                        tabs = self.query_one("#scanner-tabs", TabbedContent)
                        pane = tabs.get_pane(self._active_tab_id)
                        if pane:
                            pane.label = tab_name
                    except Exception:
                        pass
                self.call_after_refresh(_apply)
            # Extra saved tabs — create additional tabs for each beyond the first
            for tab_data in tabs_data[1:]:
                extra_url  = tab_data.get("target_url", "")
                extra_name = tab_data.get("tab_name", "Scan")
                self.call_after_refresh(
                    self.action_new_tab, extra_url
                )
        except Exception as exc:
            logger.debug("_do_load_tabs: %s", exc)

    def _auto_save_tab(self, state: _ScanTabState) -> None:
        """Auto-save tab state (name, target URL) to DB."""
        db_path = getattr(self.app, "db_path", None) or getattr(self.app, "_db_path", "")
        if not db_path or not state.scanner_api:
            return
        try:
            # Get current target URL from input
            target_input = self.query_one(f"#target-input-{state.tab_id}", Input)
            target_url = target_input.value
            self.run_worker(
                state.scanner_api.save_tab(state.name, target_url),
                exclusive=False,
            )
        except Exception:
            pass

    # ── Tab management ────────────────────────────────────────────────────────

    def action_new_tab(self, initial_url: str = "", seed_request=None, seed_requests=None) -> None:

        self._tab_counter += 1
        tab_id = f"scan-tab-{self._tab_counter}"
        name = f"Scan {self._tab_counter}"
        state = _ScanTabState(tab_id, name)

        if seed_requests is not None:
            state.seed_requests = list(seed_requests)
            url = getattr(seed_requests[0], "url", "") if seed_requests else initial_url
            state.pending_target = url or initial_url
            state.skip_db_load = True
        elif seed_request is not None:
            state.seed_requests = [seed_request]
            state.pending_request = seed_request
            url = getattr(seed_request, "url", "") or initial_url
            state.pending_target = url
            state.skip_db_load = True
        else:
            state.pending_target = initial_url
            if initial_url:
                state.skip_db_load = True

        self._tabs.append(state)

        tabs = self.query_one("#scanner-tabs", TabbedContent)
        pane = TabPane(name, id=tab_id)
        tabs.add_pane(pane)
        tabs.active = tab_id
        self._active_tab_id = tab_id
        self.call_after_refresh(self._mount_tab_content, tab_id, state)

    def _mount_tab_content(self, tab_id: str, state: _ScanTabState) -> None:
        """Mount the Scanner tab content (level 1 of 3)."""
        try:
            pane = self.query_one(f"#{tab_id}", TabPane)
            body = Vertical(classes="scan-tab-body", id=f"scan-body-{tab_id}")
            pane.mount(body)
            self.call_after_refresh(self._fill_tab_body, tab_id, state, body)
        except Exception as exc:
            logger.debug("_mount_tab_content: %s", exc)

    def _apply_pending_target(self, state: _ScanTabState) -> None:
        """Apply pending_target to an already-mounted Input (when reusing a tab)."""
        try:
            inp = self.query_one(f"#target-input-{state.tab_id}", Input)
            inp.value = state.pending_target
            state.pending_target = ""
        except Exception:
            pass

    def _fill_tab_body(self, tab_id: str, state: _ScanTabState, body: Vertical) -> None:
        """Mount settings and results containers into body (level 2 of 3).

        In Textual 8.x widgets must be in the DOM before .mount() can be
        called on them. We build the settings sub-tree via constructors and
        pass everything to body.mount() in one shot so `settings` is in the
        DOM immediately. `results` is mounted empty and filled one refresh
        later by _fill_results().
        """
        try:
            pending_target = state.pending_target
            state.pending_target = ""

            settings = Vertical(
                # target row
                Horizontal(
                    Label("Target:", classes="tab-target-label"),
                    Input(
                        placeholder="https://example.com",
                        id=f"target-input-{tab_id}",
                        classes="tab-target-input",
                        value=pending_target,
                        compact=True,
                    ),
                    id=f"target-row-{tab_id}", classes="tab-target-row",
                ),
                # checks row
                Horizontal(
                    Label("Checks:", classes="tab-checks-label"),
                    Checkbox("SQLi",          value=True, id=f"chk-sqli-{tab_id}",          classes="chk"),
                    Checkbox("XSS",           value=True, id=f"chk-xss-{tab_id}",           classes="chk"),
                    Checkbox("SSTI",          value=True, id=f"chk-ssti-{tab_id}",          classes="chk"),
                    Checkbox("LFI",           value=True, id=f"chk-lfi-{tab_id}",           classes="chk"),
                    Checkbox("RCE",           value=True, id=f"chk-rce-{tab_id}",           classes="chk"),
                    Checkbox("Redirect",      value=True, id=f"chk-redirect-{tab_id}",      classes="chk"),
                    Checkbox("SSRF",          value=True, id=f"chk-ssrf-{tab_id}",          classes="chk"),
                    Checkbox("XXE",           value=True, id=f"chk-xxe-{tab_id}",           classes="chk"),
                    Checkbox("CORS",          value=True, id=f"chk-cors-{tab_id}",          classes="chk"),
                    Checkbox("PathTraversal", value=True, id=f"chk-pathtraversal-{tab_id}", classes="chk"),
                    Checkbox("HeaderInj",     value=True, id=f"chk-headerinj-{tab_id}",     classes="chk"),
                    Checkbox("BrokenAuth",    value=True, id=f"chk-brokenauth-{tab_id}",    classes="chk"),
                    Checkbox("JWT",           value=True, id=f"chk-jwt-{tab_id}",           classes="chk"),
                    Checkbox("NoSQLi",        value=True, id=f"chk-nosqli-{tab_id}",        classes="chk"),
                    Checkbox("GraphQL",       value=True, id=f"chk-graphql-{tab_id}",       classes="chk"),
                    Checkbox("ProtoPoll",     value=True, id=f"chk-protopoll-{tab_id}",     classes="chk"),
                    Checkbox("DOM XSS",       value=True, id=f"chk-domxss-{tab_id}",        classes="chk"),
                    Checkbox("OAuth",         value=True, id=f"chk-oauth-{tab_id}",         classes="chk"),
                    Checkbox("SensData",      value=True, id=f"chk-sensdata-{tab_id}",      classes="chk"),
                    id=f"checks-row-{tab_id}", classes="tab-checks-row",
                ),
                # options row
                Horizontal(
                    Label("Threads:", classes="opt-label"),
                    Input("5",   id=f"opt-threads-{tab_id}", classes="opt-input", compact=True),
                    Label("Delay (ms):", classes="opt-label"),
                    Input("0",   id=f"opt-delay-{tab_id}",   classes="opt-input", compact=True),
                    Label("Depth:", classes="opt-label"),
                    Input("3",   id=f"opt-depth-{tab_id}",   classes="opt-input", compact=True),
                    Label("Pages:", classes="opt-label"),
                    Input("100", id=f"opt-pages-{tab_id}",   classes="opt-input", compact=True),
                    id=f"scan-options-row-{tab_id}", classes="tab-opts-row",
                ),
                # progress row
                Horizontal(
                    ProgressBar(total=100, id=f"scan-progress-{tab_id}", show_eta=False,
                                classes="tab-progress-bar"),
                    Static("—", id=f"progress-label-{tab_id}", classes="tab-progress-label"),
                    id=f"progress-row-{tab_id}", classes="tab-progress-row",
                ),
                # live stats row
                Horizontal(
                    Static(
                        "[dim]Requests:[/dim] [bold]0[/bold]"
                        "  [dim]│[/dim]  [dim]Speed:[/dim] [bold]0[/bold][dim] req/s[/dim]"
                        "  [dim]│[/dim]  [dim]Threads:[/dim] [bold]0[/bold]"
                        "  [dim]│[/dim]  [dim]Idle[/dim]",
                        id=f"scan-live-status-{tab_id}",
                        classes="tab-live-status",
                        markup=True,
                    ),
                    id=f"live-row-{tab_id}", classes="tab-live-row",
                ),
                classes="tab-settings-area", id=f"settings-area-{tab_id}",
            )
            results = Vertical(classes="tab-results-area", id=f"results-area-{tab_id}")

            # Mount settings (full tree) + resize handle + empty results into body
            body.mount(settings)
            body.mount(ResizeHandle(
                f"settings-area-{tab_id}", f"results-area-{tab_id}",
                vertical=True, id=f"resize-settings-results-{tab_id}",
            ))
            body.mount(results)

            # ── Results: need one more defer — results is now in DOM ───────────
            self.call_after_refresh(self._fill_results, tab_id, state, results)
        except Exception as exc:
            logger.debug("_fill_tab_body: %s", exc)

    def _fill_results(self, tab_id: str, state: _ScanTabState, results: Vertical) -> None:
        """Mount upper + detail panels inline, then table init on next refresh (level 3 of 3).

        In Textual 8.x widgets must be in the DOM before you can call
        .mount() on them. Build the full tree via constructors and mount
        everything into `results` (which IS already in the DOM) in one go.
        """
        try:
            # ── Upper row: findings table + scan log ──────────────────────────
            upper = Horizontal(
                Vertical(
                    Static("Findings (passive / active)",
                           id=f"findings-label-{tab_id}", classes="tab-findings-label"),
                    DataTable(id=f"findings-table-{tab_id}", classes="tab-findings-table"),
                    id=f"findings-panel-{tab_id}", classes="tab-findings-panel",
                ),
                ResizeHandle(
                    f"findings-panel-{tab_id}", f"log-panel-{tab_id}",
                    id=f"resize-find-log-{tab_id}",
                ),
                Vertical(
                    Static("Scan Log", id=f"log-label-{tab_id}", classes="tab-log-label"),
                    RichLog(id=f"scan-log-{tab_id}", highlight=True, markup=True,
                            wrap=True, max_lines=1000, classes="tab-scan-log"),
                    id=f"log-panel-{tab_id}", classes="tab-log-panel",
                ),
                id=f"upper-row-{tab_id}", classes="tab-upper-row",
            )

            # ── Detail panel: request / proof / response ──────────────────────
            detail = Horizontal(
                Vertical(
                    Static("Request", id=f"detail-request-label-{tab_id}",
                           classes="tab-detail-label"),
                    HttpView(id=f"detail-request-{tab_id}", classes="tab-detail-view"),
                    id=f"detail-request-col-{tab_id}", classes="tab-detail-req-col",
                ),
                ResizeHandle(
                    f"detail-request-col-{tab_id}", f"detail-proof-col-{tab_id}",
                    id=f"resize-req-proof-{tab_id}",
                ),
                Vertical(
                    Static("Proof", id=f"detail-proof-label-{tab_id}",
                           classes="tab-detail-label"),
                    TextArea("", read_only=True, id=f"detail-proof-{tab_id}",
                             soft_wrap=True, classes="tab-detail-proof"),
                    id=f"detail-proof-col-{tab_id}", classes="tab-detail-proof-col",
                ),
                ResizeHandle(
                    f"detail-proof-col-{tab_id}", f"detail-response-col-{tab_id}",
                    id=f"resize-proof-resp-{tab_id}",
                ),
                Vertical(
                    Static("Response", id=f"detail-response-label-{tab_id}",
                           classes="tab-detail-label"),
                    HttpView(id=f"detail-response-{tab_id}", classes="tab-detail-view"),
                    id=f"detail-response-col-{tab_id}", classes="tab-detail-resp-col",
                ),
                id=f"detail-panel-{tab_id}", classes="tab-detail-panel",
            )

            # Mount both into `results` — it IS already in the DOM
            results.mount(upper)
            results.mount(ResizeHandle(
                f"upper-row-{tab_id}", f"detail-panel-{tab_id}",
                vertical=True, id=f"resize-upper-detail-{tab_id}",
            ))
            results.mount(detail)

            # One more defer for DataTable init (DataTable must be in DOM first)
            self.call_after_refresh(self._setup_tab_table, tab_id)
            self.call_after_refresh(self._load_tab_passive_findings, tab_id, state)
            self.call_after_refresh(
                lambda: self._tab_log(
                    tab_id,
                    "Scanner ready. Enter target URL and press [bold]▶ Start[/bold] or F5.",
                )
            )
        except Exception as exc:
            logger.debug("_fill_results: %s", exc)

    def action_close_tab(self) -> None:
        if len(self._tabs) <= 1:
            self.app.notify("Cannot close the last tab", severity="warning")
            return
        tab_id = self._active_tab_id
        if not tab_id:
            return
        # Find the adjacent tab
        idx = next((i for i, t in enumerate(self._tabs) if t.tab_id == tab_id), -1)
        self._tabs = [t for t in self._tabs if t.tab_id != tab_id]
        # Activate the adjacent tab
        new_idx = max(0, idx - 1)
        new_tab = self._tabs[new_idx]
        self._active_tab_id = new_tab.tab_id
        try:
            tabs = self.query_one("#scanner-tabs", TabbedContent)
            tabs.remove_pane(tab_id)
            tabs.active = new_tab.tab_id
        except Exception as exc:
            logger.debug("action_close_tab: %s", exc)
        self.call_after_refresh(self._sync_toolbar_to_tab)

    @on(TabbedContent.TabActivated)
    def on_scanner_tab_activated(self, event: TabbedContent.TabActivated) -> None:
        """On tab change — update active state and sync toolbar."""
        if event.tabbed_content.id != "scanner-tabs":
            return
        tab_id = event.pane.id if event.pane else None
        if not tab_id:
            return
        self._active_tab_id = tab_id
        self.call_after_refresh(self._sync_toolbar_to_tab)

    def _sync_toolbar_to_tab(self) -> None:
        t = self._active_tab
        if t is None:
            return
        try:
            btn_start = self.query_one("#btn-start", ToolbarButton)
            btn_stop  = self.query_one("#btn-stop",  ToolbarButton)
            if t.scanning:
                btn_start.label = "▶ Start"
                btn_start.disabled = True
                btn_stop.disabled = False
            elif t.paused and t.last_targets:
                btn_start.label = "▶ Resume"
                btn_start.disabled = False
                btn_stop.disabled = True
            else:
                btn_start.label = "▶ Start"
                btn_start.disabled = False
                btn_stop.disabled = True
        except Exception:
            pass

    def _start_rename(self, tab_id: str) -> None:
        state = next((t for t in self._tabs if t.tab_id == tab_id), None)
        logger.debug("_start_rename: tab_id=%r state=%r", tab_id, state)
        if state is None:
            return
        try:
            try:
                inp = self.query_one("#scan-rename-input", Input)
                logger.debug("_start_rename: found existing input")
            except Exception:
                logger.debug("_start_rename: creating new input, mounting to #scanner-tabs-area")
                inp = Input(id="scan-rename-input", placeholder="Tab name...", compact=True)
                self.query_one("#scanner-tabs-area").mount(inp)
            inp.value = state.name
            inp.display = True
            inp.focus()
            inp.action_select_all()
            inp._rename_tab_id = tab_id  # type: ignore[attr-defined]
            logger.debug("_start_rename: input shown, value=%r", inp.value)
        except Exception as e:
            logger.debug("_start_rename: EXCEPTION: %s", e)

    def _rename_tab(self, tab_id: str, new_name: str) -> None:
        state = next((t for t in self._tabs if t.tab_id == tab_id), None)
        if state is None:
            return
        state.name = new_name
        try:
            tabs = self.query_one("#scanner-tabs", TabbedContent)
            tab_widget = tabs.get_tab(tab_id)
            if tab_widget is not None:
                tab_widget.label = new_name
        except Exception:
            pass

    # ── Helpers: utility methods operating on tab_id ─────────────────────────

    def _tab_widget(self, widget_id: str, tab_id: str | None = None, cls=None):
        tid = tab_id or self._active_tab_id or ""
        try:
            wid = f"#{widget_id}-{tid}"
            return self.query_one(wid) if cls is None else self.query_one(wid, cls)
        except Exception:
            return None

    def _tab_log(self, tab_id: str | None, msg: str, color: str = "dim") -> None:
        ts = datetime.now().strftime("%H:%M:%S")
        tid = tab_id or self._active_tab_id or ""
        try:
            log = self.query_one(f"#scan-log-{tid}", RichLog)
            log.write(f"[{color}]{ts}[/{color}]  {msg}")
        except Exception:
            pass

    def _setup_tab_table(self, tab_id: str | None = None) -> None:
        tid = tab_id or self._active_tab_id or ""
        try:
            table = self.query_one(f"#findings-table-{tid}", DataTable)
            table.cursor_type = "row"
            table.max_column_content_width = 80
            # column_widths: _#, Source, Type, Severity, URL, Param, Evidence
            table.column_widths = [4, 10, 16, 10, 50, 14, 30]
            empty = pa.Table.from_pylist([], schema=self._FINDINGS_SCHEMA)
            table.backend = ArrowBackend(empty)
            table._ordered_columns = None
            table._clear_caches()
            table._require_update_dimensions = True
        except Exception as exc:
            logger.debug("_setup_tab_table: %s", exc)

    def _load_tab_passive_findings(self, tab_id: str, state: _ScanTabState) -> None:
        try:
            # If the tab was opened for a new target — skip loading old findings from DB
            if state.skip_db_load:
                state.skip_db_load = False  # reset — next load will work normally
                return
            db_path = getattr(self.app, "db_path", None) or getattr(self.app, "_db_path", "")
            # Do not load findings if no project is open (DB not selected)
            if not db_path:
                return
            # Do not load findings for the default tab at startup without an explicit project
            project_path = getattr(self.app, "_project_path", None)
            if not project_path:
                return  # no project open — do not pull data from the default DB
            state.scanner_api = self._get_or_create_api_for(state, db_path)
            self._load_findings_worker_for(tab_id, state)
        except Exception as exc:
            logger.warning("_load_tab_passive_findings: %s", exc)

    def _get_or_create_api_for(self, state: _ScanTabState, db_path: str):
        from pentool.api.scanner_api import ScannerAPI
        from pentool.utils.http_client import HTTPClient
        if state.scanner_api is None:
            http_client = HTTPClient(timeout=20.0, follow_redirects=True, verify_ssl=False)
            state.scanner_api = ScannerAPI(db_path=db_path, http_client=http_client)
        return state.scanner_api

    @work
    async def _load_findings_worker_for(self, tab_id: str, state: _ScanTabState) -> None:
        try:
            findings = await state.scanner_api.get_findings()
            self._populate_tab_from_db(tab_id, state, findings)
        except Exception as exc:
            logger.warning("_load_findings_worker_for: %s", exc)

    def _populate_tab_from_db(self, tab_id: str, state: _ScanTabState, findings) -> None:
        # Do not overwrite the table while a scan is running — findings would be duplicated
        if state.scanning:
            return
        state.rows = []
        state.row_sources = []
        for f in findings:
            state.rows.append(f)
            state.row_sources.append("passive")
        self._rebuild_table_backend(tab_id, state)
        self._update_label(tab_id, state)
        if findings:
            self._tab_log(tab_id, f"Loaded [bold]{len(findings)}[/bold] findings from DB.")

    def _setup_table(self) -> None:
        """Initialize the active tab table — delegates to _setup_tab_table."""
        self._setup_tab_table(self._active_tab_id)

    _FINDINGS_SCHEMA = pa.schema([
        ("_#",       pa.string()),
        ("Source",   pa.string()),
        ("Type",     pa.string()),
        ("Severity", pa.string()),
        ("URL",      pa.string()),
        ("Param",    pa.string()),
        ("Evidence", pa.string()),
    ])

    def _reset_table(self) -> None:
        """Reset the active tab table."""
        tid = self._active_tab_id or ""
        try:
            table = self.query_one(f"#findings-table-{tid}", DataTable)
            empty = pa.Table.from_pylist([], schema=self._FINDINGS_SCHEMA)
            table.backend = ArrowBackend(empty)
            table._ordered_columns = None
            table._clear_caches()
            table._require_update_dimensions = True
            table.refresh()
        except Exception as exc:
            logger.debug("_reset_table: %s", exc)

    def _log(self, msg: str, color: str = "dim") -> None:
        """Log to the active tab."""
        self._tab_log(self._active_tab_id, msg, color)

    # ── helpers ────────────────────────────────────────────────────────────────

    def _get_opt_int(self, widget_id: str, default: int) -> int:
        tid = self._active_tab_id or ""
        try:
            val = self.query_one(f"#{widget_id}-{tid}", Input).value.strip()
            v = int(val)
            return v if v > 0 else default
        except Exception:
            return default

    def _get_opt_float(self, widget_id: str, default: float) -> float:
        tid = self._active_tab_id or ""
        try:
            val = self.query_one(f"#{widget_id}-{tid}", Input).value.strip()
            v = float(val)
            return v if v >= 0 else default
        except Exception:
            return default

    # ── DB load ────────────────────────────────────────────────────────────────

    def _load_passive_findings(self) -> None:
        t = self._active_tab
        if t is None:
            return
        try:
            db_path = getattr(self.app, "db_path", None) or getattr(self.app, "_db_path", "")
            if not db_path:
                return
            t.scanner_api = self._get_or_create_api_for(t, db_path)
            self._load_findings_worker_for(t.tab_id, t)
        except Exception as exc:
            logger.warning("ScannerScreen._load_passive_findings: %s", exc)

    def _get_or_create_api(self, db_path: str):
        t = self._active_tab
        if t is None:
            return None
        return self._get_or_create_api_for(t, db_path)

    @work
    async def _load_findings_worker(self) -> None:
        t = self._active_tab
        if t is None or t.scanner_api is None:
            return
        tab_id = t.tab_id
        state = t
        try:
            findings = await state.scanner_api.get_findings()
            self._populate_tab_from_db(tab_id, state, findings)
        except Exception as exc:
            logger.warning("_load_findings_worker: %s", exc)

    def _populate_from_db(self, findings) -> None:
        """Delegate to _populate_tab_from_db for the active tab."""
        t = self._active_tab
        if t is None:
            return
        self._populate_tab_from_db(t.tab_id, t, findings)

    def _add_row_to_table(self, table: DataTable, finding, source: str) -> None:
        self._rows.append(finding)
        self._row_sources.append(source)
        # Append a single row to the existing ArrowBackend (fast path)
        try:
            new_row = self._finding_to_row(finding, len(self._rows), source)
            new_arrow = pa.Table.from_pylist([new_row], schema=self._FINDINGS_SCHEMA)
            if hasattr(table, "backend") and table.backend is not None:
                existing = table.backend.source_data
                combined = pa.concat_tables([existing, new_arrow])
            else:
                combined = new_arrow
            table.backend = ArrowBackend(combined)
            table._ordered_columns = None
            table._clear_caches()
            table._require_update_dimensions = True
            table.refresh()
        except Exception as exc:
            logger.debug("_add_row_to_table: %s", exc)

    def _finding_to_row(self, finding, n: int, source: str) -> dict:
        sev      = getattr(finding, "severity",  "info").upper()
        ftype    = getattr(finding, "type",      getattr(finding, "name", "?"))
        url      = getattr(finding, "url",       "?")
        param    = getattr(finding, "parameter", None) or "—"
        evidence = getattr(finding, "evidence",  "") or "—"
        fp_prefix = "[FP] " if getattr(finding, "false_positive", False) else ""

        sev_color = {
            "CRITICAL": "bold red", "HIGH": "red",
            "MEDIUM": "yellow", "LOW": "green", "INFO": "blue",
        }.get(sev, "white")
        return {
            "_#":       str(n),
            "Source":   source,
            "Type":     fp_prefix + ftype,
            "Severity": f"[{sev_color}]{sev}[/{sev_color}]",
            "URL":      url[:55],
            "Param":    param[:20],
            "Evidence": evidence[:50],
        }

    def _rebuild_table_backend(self, tab_id: str | None = None,
                               state: _ScanTabState | None = None) -> None:
        """Rebuild the ArrowBackend from the tab's rows/row_sources."""
        tid = tab_id or self._active_tab_id or ""
        st  = state or self._active_tab
        if st is None:
            return
        try:
            table = self.query_one(f"#findings-table-{tid}", DataTable)
            rows = [
                self._finding_to_row(f, i + 1, src)
                for i, (f, src) in enumerate(zip(st.rows, st.row_sources))
            ]
            arrow = pa.Table.from_pylist(rows, schema=self._FINDINGS_SCHEMA)
            table.backend = ArrowBackend(arrow)
            table._ordered_columns = None
            table._clear_caches()
            table._require_update_dimensions = True
            table.refresh()
        except Exception as exc:
            logger.debug("_rebuild_table_backend: %s", exc)

    def _update_label(self, tab_id: str | None = None, state: _ScanTabState | None = None) -> None:
        tid = tab_id or self._active_tab_id or ""
        st  = state or self._active_tab
        if st is None:
            return
        try:
            n = len(st.rows)
            seed_info = f"  │  [dim]{len(st.seed_requests)} seed req[/dim]" if st.seed_requests else ""
            self.query_one(f"#findings-label-{tid}", Static).update(
                f"Findings: [bold]{n}[/bold]  (passive + active){seed_info}"
            )
        except Exception:
            pass

    # ── public API ─────────────────────────────────────────────────────────────

    def add_finding(self, finding) -> None:
        self.call_after_refresh(self._add_finding_ui, finding)

    def _add_finding_ui(self, finding) -> None:
        try:
            tid = self._active_tab_id or ""
            table = self.query_one(f"#findings-table-{tid}", DataTable)
            self._add_row_to_table(table, finding, source="passive")
            self._update_label()
            sev   = getattr(finding, "severity", "info")
            ftype = getattr(finding, "type", "?")
            url   = getattr(finding, "url",  "?")
            self._log(f"[yellow]PASSIVE[/yellow] [{sev}] {ftype} → {url}")
        except Exception:
            pass

    def set_target(self, url: str) -> None:
        tid = self._active_tab_id or ""
        try:
            self.query_one(f"#target-input-{tid}", Input).value = url
        except Exception:
            pass

    # ── row selection → detail panel ──────────────────────────────────────────

    def on_data_table_row_highlighted(self, event) -> None:
        """On cursor move in the table — show request/response.
        Only fires with cursor_type='row'."""
        idx = event.cursor_row
        if idx < 0 or idx >= len(self._rows):
            return
        self._show_detail(self._rows[idx])

    def on_data_table_row_selected(self, event) -> None:
        """Enter on a row — also shows the detail panel."""
        idx = event.cursor_row
        if idx < 0 or idx >= len(self._rows):
            return
        self._show_detail(self._rows[idx])

    def _show_detail(self, finding) -> None:
        self._current_finding = finding
        tid = self._active_tab_id or ""

        req_raw  = getattr(finding, "request_raw",  "") or ""
        resp_raw = getattr(finding, "response_raw", "") or ""

        # If request_raw is empty — build a minimal request from url
        if not req_raw.strip():
            req_raw = self._build_http_raw(finding)

        try:
            panel = self.query_one(f"#detail-panel-{tid}")
            panel.styles.height = 18
            panel.display = True
            self._detail_panel_open = True
        except Exception as exc:
            logger.debug("_show_detail panel: %s", exc)

        try:
            proof_area = self.query_one(f"#detail-proof-{tid}", TextArea)
            proof_area.load_text(self._render_proof(finding))
        except Exception:
            pass

        # Collect highlight terms: payload and/or xsspwn marker
        payload = getattr(finding, "payload", "") or ""
        highlight_terms: list[str] = []
        if payload:
            import re as _re
            m = _re.search(r"xsspwn[0-9a-f]{8}", payload)
            if m:
                highlight_terms.append(m.group(0))
            # Also add the payload itself (truncated to 80 chars)
            core = payload.split("<!--")[0].strip()
            if len(core) > 4 and core not in highlight_terms:
                highlight_terms.append(core[:80])

        # Load req/resp — with a delay so the layout has time to reflow
        self.call_after_refresh(self._load_detail_content, req_raw, resp_raw, highlight_terms)

        try:
            self.query_one("#btn-send-repeater", ToolbarButton).disabled = False
        except Exception:
            pass

    def _load_detail_content(self, req_raw: str, resp_raw: str,
                             highlight_terms: list[str] | None = None) -> None:
        tid = self._active_tab_id or ""
        try:
            req_view = self.query_one(f"#detail-request-{tid}", HttpView)
            req_view.load_raw_http(req_raw)
        except Exception:
            pass
        try:
            resp_view = self.query_one(f"#detail-response-{tid}", HttpView)
            resp_view.load_raw_http(resp_raw, highlight_terms=highlight_terms)
        except Exception:
            pass

    @staticmethod
    def _render_proof(finding) -> str:
        """Build plain-text proof for display in TextArea."""
        sev  = getattr(finding, "severity", "info").upper()
        name = getattr(finding, "name", "") or getattr(finding, "type", "?")

        name        = name
        ftype       = getattr(finding, "type",         "?")
        parameter   = getattr(finding, "parameter",    "") or "—"
        payload     = getattr(finding, "payload",      "") or "—"
        evidence    = getattr(finding, "evidence",     "") or "—"
        desc        = getattr(finding, "description",  "") or "—"
        cwe         = getattr(finding, "cwe",          "") or "—"
        mitre       = getattr(finding, "mitre_attack", "") or "—"
        remediation = getattr(finding, "remediation",  "") or "—"
        url         = getattr(finding, "url",          "") or "—"

        lines: list[str] = [
            f"▶ {name}",
            "",
            f"Type:      {ftype}",
            f"Severity:  {sev}",
            f"URL:       {url}",
            f"Parameter: {parameter}",
            "",
            "── Payload ──────────────────────",
            payload,
            "",
            "── Evidence (matched) ───────────",
            evidence,
            "",
        ]
        if desc and desc != "—":
            lines += ["── Description ──────────────────", desc, ""]
        if cwe != "—" or mitre != "—":
            lines.append("── References ───────────────────")
            if cwe != "—":
                lines.append(f"CWE:    {cwe}")
            if mitre != "—":
                lines.append(f"MITRE:  {mitre}")
            lines.append("")
        if remediation != "—":
            lines += ["── Remediation ──────────────────", remediation]
        return "\n".join(lines)

    @staticmethod
    def _build_http_raw(finding) -> str:
        """Build a complete HTTP/1.1 request from finding data.

        request_raw already contains the full HTTP request with the payload
        (populated by format_request_raw helpers in checks). If absent — build a
        minimal request from url.
        """

        raw = getattr(finding, "request_raw", "") or ""
        if raw.strip():
            return raw

        # Fallback: build a minimal GET request from url
        url = getattr(finding, "url", "") or ""
        if not url:
            return "GET / HTTP/1.1\r\nHost: unknown\r\nConnection: close\r\n\r\n"

        try:
            parsed = urlparse(url)
            host = parsed.netloc or parsed.hostname or "unknown"
            path = parsed.path or "/"
            if parsed.query:
                path = path + "?" + parsed.query
        except Exception:
            host = "unknown"
            path = "/"

        return (
            f"GET {path} HTTP/1.1\r\n"
            f"Host: {host}\r\n"
            "User-Agent: pentool/1.0\r\n"
            "Accept: */*\r\n"
            "Connection: close\r\n"
            "\r\n"
        )

    # ── context menu (detail panel) ───────────────────────────────────────────

    def on__base_http_widget_context_menu_request(self, event) -> None:
        """Ctrl+click / right-click on any _BaseHttpWidget → context menu."""
        self.cm_open_text_menu(event.screen_x, event.screen_y)

    def _cm_get_raw_request(self) -> str:
        """Raw HTTP from the current finding."""
        return self._build_http_raw(self._current_finding) if self._current_finding else ""

    # ── toolbar ────────────────────────────────────────────────────────────────

    @on(ToolbarButton.Pressed, "#btn-start")
    def on_btn_start(self, _: ToolbarButton.Pressed) -> None:
        if self._paused:
            self.action_resume_scan()
        else:
            self.action_start_scan()

    @on(ToolbarButton.Pressed, "#btn-stop")
    def on_btn_stop(self, _: ToolbarButton.Pressed) -> None:
        self.action_stop_scan()

    @on(ToolbarButton.Pressed, "#btn-send-repeater")
    def on_btn_send_repeater(self, _: ToolbarButton.Pressed) -> None:
        self.action_send_to_repeater()

    @on(ToolbarButton.Pressed, "#btn-report")
    def on_btn_report(self, _: ToolbarButton.Pressed) -> None:
        self.action_generate_report()

    @on(ToolbarButton.Pressed, "#btn-pro-report")
    def on_btn_pro_report(self, _: ToolbarButton.Pressed) -> None:
        self.action_generate_pro_report()

    @on(ToolbarButton.Pressed, "#btn-clear")
    def on_btn_clear(self, _: ToolbarButton.Pressed) -> None:
        self.action_clear()

    @on(ToolbarButton.Pressed, "#btn-passive")
    def on_btn_passive(self, _: ToolbarButton.Pressed) -> None:
        self.action_toggle_passive()

    @on(ToolbarButton.Pressed, "#btn-fp")
    def on_btn_fp(self, _: ToolbarButton.Pressed) -> None:
        self.action_mark_false_positive()

    @on(ToolbarButton.Pressed, "#btn-new-tab")
    def on_btn_new_tab(self, _: ToolbarButton.Pressed) -> None:
        self.action_new_tab()

    @on(ToolbarButton.Pressed, "#btn-from-history")
    def on_btn_from_history(self, _: ToolbarButton.Pressed) -> None:
        self.action_scan_from_history()

    @on(ToolbarButton.Pressed, "#btn-close-tab")
    def on_btn_close_tab(self, _: ToolbarButton.Pressed) -> None:
        self.action_close_tab()

    @on(Input.Changed)
    def on_input_changed(self, event: Input.Changed) -> None:
        """Auto-save tab state when target URL input changes."""
        # Check if this is a target-input for a scanner tab
        if event.input.id and event.input.id.startswith("target-input-"):
            if self._active_tab:
                self._auto_save_tab(self._active_tab)

    # ── send to repeater ───────────────────────────────────────────────────────

    def action_send_to_repeater(self) -> None:
        finding = self._current_finding
        if finding is None:
            self.app.notify("Select a finding first", severity="warning")
            return

        raw = self._build_http_raw(finding)

        try:
            from pentool.tui.messages import SendToRepeater
            self.app.post_message(SendToRepeater(raw))
        except Exception as exc:
            self.app.notify(f"Send to Repeater failed: {exc}", severity="error")

    # ── from history ──────────────────────────────────────────────────────────

    def action_scan_from_history(self) -> None:
        self._load_history_worker()

    @work
    async def _load_history_worker(self) -> None:
        try:
            db_path = self.app.db_path
        except Exception:
            db_path = ""
        if not db_path:
            self.app.notify("No project open — open a project first", severity="warning")
            return
        try:
            from pentool.api.scanner_api import ScannerAPI
            api = ScannerAPI(db_path=db_path)
            reqs = await api.get_history_requests(limit=300)
        except Exception as exc:
            self.app.notify(f"History load failed: {exc}", severity="error")
            return
        if not reqs:
            self.app.notify("History is empty", severity="warning")
            return
        self.call_from_thread(self._open_history_tab, reqs)

    def _open_history_tab(self, reqs: list) -> None:
        n = len(reqs)
        hosts: set[str] = set()
        for r in reqs:
            try:
                from urllib.parse import urlparse as _up
                h = _up(r.url).hostname or ""
                if h:
                    hosts.add(h)
            except Exception:
                pass
        if len(hosts) == 1:
            label = f"History: {next(iter(hosts))}"
        else:
            label = f"History ({n})"
        first_urls = list({r.url.split('?')[0] for r in reqs[:10]})
        first_url = first_urls[0] if first_urls else ""
        self.app.notify(f"Loaded {n} requests from history", severity="information")
        self.action_new_tab(initial_url=first_url, seed_requests=reqs)

    # ── start scan ─────────────────────────────────────────────────────────────

    def action_start_scan(self) -> None:
        if self._scanning:
            self.app.notify("Scan already running", severity="warning")
            return

        tid = self._active_tab_id or ""
        try:
            target_input = self.query_one(f"#target-input-{tid}", Input)
            raw = target_input.value.strip()
        except Exception:
            raw = ""

        if not raw:
            self.app.notify("Enter target URL", severity="warning")
            return

        # Auto-save tab state before starting scan
        if self._active_tab:
            self._auto_save_tab(self._active_tab)

        targets = [u.strip() for u in raw.replace(",", "\n").splitlines() if u.strip()]
        if not targets:
            self.app.notify("No valid targets", severity="warning")
            return

        # URL normalisation
        normalized = []
        for url in targets:
            try:
                parsed = urlparse(url)
                if not parsed.scheme:
                    url = "https://" + url
                    parsed = urlparse(url)
                if parsed.port == 443 and parsed.scheme == "https":
                    url = urlunparse(parsed._replace(netloc=parsed.hostname or parsed.netloc))
                elif parsed.port == 80 and parsed.scheme == "http":
                    url = urlunparse(parsed._replace(netloc=parsed.hostname or parsed.netloc))
                normalized.append(url)
            except Exception:
                normalized.append(url)
        targets = normalized

        check_map = {
            "chk-sqli":         "sqli",
            "chk-xss":          "xss",
            "chk-ssti":         "ssti",
            "chk-lfi":          "lfi",
            "chk-rce":          "rce",
            "chk-redirect":     "open_redirect",
            "chk-ssrf":         "ssrf",
            "chk-xxe":          "xxe",
            "chk-cors":         "cors",
            "chk-pathtraversal":"path_traversal",
            "chk-headerinj":    "header_injection",
            "chk-brokenauth":   "broken_auth",
            "chk-jwt":          "jwt_none",
            "chk-nosqli":       "nosql_injection",
            "chk-graphql":      "graphql",
            "chk-protopoll":    "prototype_pollution",
            "chk-domxss":       "dom_xss",
            "chk-oauth":        "oauth",
            "chk-sensdata":     "sensitive_data",
        }
        selected = []
        for chk_id, check_name in check_map.items():
            try:
                if self.query_one(f"#{chk_id}-{tid}", Checkbox).value:
                    selected.append(check_name)
            except Exception:
                pass

        threads   = self._get_opt_int("opt-threads", 10)
        delay_ms  = self._get_opt_float("opt-delay", 0.0)
        delay_sec = delay_ms / 1000.0
        depth     = self._get_opt_int("opt-depth", 3)
        pages     = self._get_opt_int("opt-pages", 100)

        try:
            db_path = self.app.db_path
        except Exception:
            db_path = ""

        t = self._active_tab
        if t is None:
            return
        t.scanner_api = self._get_or_create_api_for(t, db_path)
        self._scanning = True
        self._stop_requested = False
        self._paused = False

        # Save parameters for Resume
        self._last_targets        = targets
        self._last_check_names    = selected or None
        self._last_threads        = threads
        self._last_delay_sec      = delay_sec
        self._last_depth          = depth
        self._last_pages          = pages
        self._last_crawled_targets = list(targets)  # starting point — expands in on_url_crawled

        try:
            progress = self.query_one(f"#scan-progress-{tid}", ProgressBar)
            progress.update(total=1000, progress=0)  # indeterminate-style: total will update in on_progress
            self.query_one(f"#progress-label-{tid}", Static).update("0 req")
        except Exception:
            pass

        self.query_one("#btn-start", ToolbarButton).disabled = True
        self.query_one("#btn-stop",  ToolbarButton).disabled = False

        self._log(
            f"[bold green]START[/bold green] {len(targets)} target(s), "
            f"{len(selected) or 'all'} checks  │  "
            f"threads={threads}  delay={delay_ms:.0f}ms  "
            f"depth={depth}  pages={pages}"
        )
        for target in targets:
            self._log(f"  → {target}")

        self._run_active_scan(targets, selected or None, threads, delay_sec, depth, pages)

    @work
    async def _run_active_scan(
        self,
        targets: list[str],
        check_names: list[str] | None = None,
        threads: int = 5,
        delay_sec: float = 0.0,
        max_depth: int = 3,
        max_pages: int = 100,
        resume: bool = False,
    ) -> None:
        from pentool.api.spider_api import SpiderAPI
        from pentool.core.event_bus import get_event_bus
        from pentool.services.scan_service import ScanConfig, ScanService

        # Pin tab_id at scan start — do not read _active_tab_id from callbacks
        # (the user may switch tabs while scanning)
        scan_tab_id = self._active_tab_id or ""

        # Reset live counters
        self._reset_live_status(scan_tab_id)

        # Log callback — delivers messages to the TUI
        def on_log(msg: str) -> None:
            self._tab_log(scan_tab_id, msg)

        # Callback for each discovered URL → send to Target + remember for Resume
        def on_url_crawled(event) -> None:
            self._send_url_to_target(event.url)
            t = next((x for x in self._tabs if x.tab_id == scan_tab_id), None)
            if t and event.url not in t.last_crawled_targets:
                t.last_crawled_targets.append(event.url)

        # Finding callback → add to the TUI table of the specific scan tab
        def on_finding_discovered(event) -> None:
            if not self._stop_requested:
                self._on_active_finding_for_tab(event.finding, scan_tab_id)

        # Progress callback
        def on_scan_progress(event) -> None:
            self._on_progress(event.done, event.total)

        # Callback for every HTTP request → update live status + Dashboard
        def on_request_sent(req_sent: int, threads_active: int,
                            check_name: str, param_name: str, url: str) -> None:
            self._on_request_sent(scan_tab_id, req_sent, threads_active,
                                  check_name, param_name, url)
            # Also push to the Dashboard live feed
            self._push_request_to_dashboard(url, threads_active)

        bus = get_event_bus()
        from pentool.core.events import FindingDiscovered, ScanProgressEvent, UrlCrawled
        bus.subscribe(UrlCrawled,          on_url_crawled)
        bus.subscribe(FindingDiscovered,   on_finding_discovered)
        bus.subscribe(ScanProgressEvent,   on_scan_progress)

        try:
            self._log("[cyan]CRAWL[/cyan] Discovering endpoints…")
            self._update_dashboard_scan(True, 0, threads)

            spider_api = SpiderAPI.from_params(
                max_depth=max_depth,
                max_pages=max_pages,
                concurrency=min(threads, 10),
            )
            service = ScanService(
                scanner_api=self._scanner_api,
                spider_api=spider_api,
                event_bus=bus,
                tui_loop=None,
                on_log=on_log,
            )
            # Save a reference to the service so action_stop_scan can call request_stop()
            self._active_service = service

            try:
                db_path = self.app.db_path
            except Exception:
                db_path = ""

            tab_state = next((x for x in self._tabs if x.tab_id == scan_tab_id), None)
            seed_reqs = list(tab_state.seed_requests) if tab_state else []
            resume_targets = list(tab_state.last_crawled_targets) if (tab_state and resume) else []
            config = ScanConfig(
                targets=targets,
                seed_requests=seed_reqs,
                check_names=check_names,
                threads=threads,
                delay_sec=delay_sec,
                max_depth=max_depth,
                max_pages=max_pages,
                db_path=db_path,
                resume=resume,
                resume_targets=resume_targets,
                on_request_sent=on_request_sent,
            )

            await service.run(config)

        except Exception as exc:
            logger.error("_run_active_scan error: %s", exc)
            self._log(f"[red]ERROR:[/red] {exc}")
        finally:
            # Unsubscribe the temporary handlers
            bus.unsubscribe(UrlCrawled,        on_url_crawled)
            bus.unsubscribe(FindingDiscovered,  on_finding_discovered)
            bus.unsubscribe(ScanProgressEvent,  on_scan_progress)
            self._active_service = None  # clear the reference to the finished service
            self._on_scan_done()

    def _on_active_finding_for_tab(self, finding, tab_id: str) -> None:
        try:
            state = next((t for t in self._tabs if t.tab_id == tab_id), None)
            if state is None:
                return
            # Deduplication by finding.id — protection against duplicate subscription / race condition
            finding_id = getattr(finding, "id", None)
            if finding_id is not None:
                if any(getattr(r, "id", None) == finding_id for r in state.rows):
                    return
            table = self.query_one(f"#findings-table-{tab_id}", DataTable)
            state.rows.append(finding)
            state.row_sources.append("active")
            new_row = self._finding_to_row(finding, len(state.rows), "active")
            new_arrow = pa.Table.from_pylist([new_row], schema=self._FINDINGS_SCHEMA)
            try:
                backend = getattr(table, "backend", None)
                if backend is not None and hasattr(backend, "source_data"):
                    existing = backend.source_data
                    combined = pa.concat_tables([existing, new_arrow])
                else:
                    combined = new_arrow
            except Exception:
                combined = new_arrow
            table.backend = ArrowBackend(combined)
            try:
                table._ordered_columns = None
            except Exception:
                pass
            try:
                table._clear_caches()
            except Exception:
                pass
            try:
                table._require_update_dimensions = True
            except Exception:
                pass
            table.refresh()
            self._update_label(tab_id, state)
            sev   = getattr(finding, "severity",  "info")
            ftype = getattr(finding, "type",      "?")
            url   = getattr(finding, "url",       "?")
            param = getattr(finding, "parameter", None) or ""
            param_str = f" param=[cyan]{param}[/cyan]" if param else ""
            self._tab_log(tab_id, f"[bold red]FOUND[/bold red] [{sev}] {ftype} → {url}{param_str}")
        except Exception as exc:
            logger.debug("_on_active_finding_for_tab: %s", exc)

    def _send_url_to_target(self, url: str) -> None:
        try:
            from pentool.tui.messages import SendUrlToTarget
            from pentool.utils.parser import ParsedRequest
            req = ParsedRequest(method="GET", url=url, headers={}, body="")
            self.app.post_message(SendUrlToTarget(req))
        except Exception:
            pass

    def _update_dashboard_scan(self, scanning: bool, pct: int = 0,
                                threads: int = 0) -> None:
        try:
            from pentool.core.event_bus import get_event_bus
            from pentool.core.events import ScanStarted, ScanFinished
            bus = get_event_bus()
            if scanning:
                bus.emit(ScanStarted(source="scanner"))
            else:
                bus.emit(ScanFinished(total_findings=len(self._rows), source="scanner"))
        except Exception:
            pass
        # Also update the Dashboard directly if it is mounted
        try:
            from pentool.tui.screens.dashboard.screen import DashboardScreen
            dash = self.app.query_one(DashboardScreen)
            dash.update_scan_status(scanning=scanning, progress=pct, threads=threads)
        except Exception:
            pass

    def _push_request_to_dashboard(self, url: str, threads_active: int = 0) -> None:
        """Push an HTTP request to the Dashboard live feed (throttled: every 10th request)."""
        t = self._active_tab
        if t is None:
            return
        # Throttle: push to Dashboard every 10th request to avoid overloading the TUI
        if t.req_sent % 10 != 1:
            return
        try:
            from pentool.tui.screens.dashboard.screen import DashboardScreen
            dash = self.app.query_one(DashboardScreen)
            dash.push_request("SCAN", url, 0)
            # Update thread count on Dashboard
            if threads_active > 0:
                dash.update_scan_status(
                    scanning=True, progress=0, threads=threads_active
                )
        except Exception:
            pass

    def _on_progress(self, done: int, total: int) -> None:
        tid = self._active_tab_id or ""
        try:
            progress = self.query_one(f"#scan-progress-{tid}", ProgressBar)
            progress.update(total=max(total, 1), progress=done)
            # Show task progress in the label only if the live req counter is not active
            t = self._active_tab
            if t is not None and t.req_sent == 0:
                self.query_one(f"#progress-label-{tid}", Static).update(
                    f"tasks {done}/{total}"
                )
        except Exception:
            pass

    def _on_request_sent(self, tab_id: str, req_sent: int, threads_active: int,
                         check_name: str, param_name: str, url: str) -> None:
        t = next((x for x in self._tabs if x.tab_id == tab_id), None)
        if t is None:
            return

        # Always update counters in tab state
        t.req_sent = req_sent
        t.threads_active = threads_active

        # req/s: sliding 2 s window without list comprehension
        now = time.monotonic()
        if now - t.req_window_start >= 2.0:
            t.req_per_sec = t.req_bucket / max(now - t.req_window_start, 0.001)
            t.req_bucket = 0
            t.req_window_start = now
        t.req_bucket += 1

        # Throttle UI: at most every 150 ms, active tab only
        if tab_id != self._active_tab_id:
            return
        if now - t._last_ui_update < 0.15:
            return
        t._last_ui_update = now

        try:
            # Progress label — shows actual request count
            self.query_one(f"#progress-label-{tab_id}", Static).update(
                f"[bold]{req_sent:,}[/bold] req"
            )
            # Live status line
            short_url = url[-40:] if len(url) > 40 else url
            check_display = check_name.replace("_", " ").upper()
            param_display = param_name if param_name and param_name != "—" else ""
            if param_display:
                kind_part = param_display.split(":")[0] if ":" in param_display else "param"
                name_part = param_display.split(":", 1)[1] if ":" in param_display else param_display
                status_check = (
                    f"[cyan]{check_display}[/cyan] "
                    f"[dim]{kind_part}:[/dim][bold]{name_part}[/bold]"
                )
            else:
                status_check = f"[cyan]{check_display}[/cyan]"
            self.query_one(f"#scan-live-status-{tab_id}", Static).update(
                f"[dim]Requests:[/dim] [bold green]{req_sent:,}[/bold green]"
                f"  [dim]│[/dim]  [dim]Speed:[/dim] [bold]{t.req_per_sec:.1f}[/bold][dim] req/s[/dim]"
                f"  [dim]│[/dim]  [dim]Threads:[/dim] [bold cyan]{threads_active}[/bold cyan]"
                f"  [dim]│[/dim]  {status_check}"
                f"  [dim]{short_url}[/dim]"
            )
        except Exception:
            pass

    def _reset_live_status(self, tab_id: str) -> None:
        """Reset live status on scan start/finish."""
        t = next((x for x in self._tabs if x.tab_id == tab_id), None)
        if t is not None:
            t.req_sent = 0
            t.threads_active = 0
            t.req_bucket = 0
            t.req_window_start = 0.0
            t.req_per_sec = 0.0
            t._last_ui_update = 0.0
        try:
            self.query_one(f"#scan-live-status-{tab_id}", Static).update(
                "[dim]Requests:[/dim] [bold]0[/bold]"
                "  [dim]│[/dim]  [dim]Speed:[/dim] [bold]0[/bold][dim] req/s[/dim]"
                "  [dim]│[/dim]  [dim]Threads:[/dim] [bold]0[/bold]"
                "  [dim]│[/dim]  [dim]Idle[/dim]"
            )
            self.query_one(f"#progress-label-{tab_id}", Static).update("—")
        except Exception:
            pass

    def _on_scan_done(self) -> None:
        self._scanning = False
        tid = self._active_tab_id or ""
        t = self._active_tab
        total_req = t.req_sent if t else 0
        logger.info("SCANNER: scan done, findings=%d req_sent=%d", len(self._rows), total_req)
        try:
            btn_start = self.query_one("#btn-start", ToolbarButton)
            btn_stop  = self.query_one("#btn-stop",  ToolbarButton)
            if self._paused:
                # Stopped by the user — show Resume
                btn_start.label = "▶ Resume"
                btn_start.disabled = False
                btn_stop.disabled = True
                self._log(
                    f"[yellow]PAUSED[/yellow] Scan paused after [bold]{total_req:,}[/bold] requests. "
                    f"Press [bold]▶ Resume[/bold] to continue."
                )
                self.app.notify("Scan paused — press Resume to continue", severity="warning")
            else:
                # Finished normally
                btn_start.label = "▶ Start"
                btn_start.disabled = False
                btn_stop.disabled = True
                self._log(
                    f"[bold green]DONE[/bold green] Scan complete. "
                    f"[bold]{total_req:,}[/bold] requests sent. "
                    f"Findings: [bold]{len(self._rows)}[/bold]"
                )
                self.app.notify(
                    f"Scan complete — {len(self._rows)} findings ({total_req:,} req)",
                    severity="information",
                )
        except Exception:
            pass
        self._stop_requested = False
        self._update_dashboard_scan(False, 100)
        # Final live status — show summary, do not reset to 0
        try:
            self.query_one(f"#scan-live-status-{tid}", Static).update(
                f"[dim]Total requests:[/dim] [bold green]{total_req:,}[/bold green]"
                f"  [dim]│[/dim]  [dim]Findings:[/dim] [bold red]{len(self._rows)}[/bold red]"
                f"  [dim]│[/dim]  [dim]Threads:[/dim] [bold]0[/bold]"
                f"  [dim]│[/dim]  [bold green]DONE[/bold green]"
            )
        except Exception:
            pass

    # ── stop / resume ──────────────────────────────────────────────────────────

    def action_stop_scan(self) -> None:
        if not self._scanning:
            # If already paused and Stop is pressed — clear the pause
            if self._paused:
                self._paused = False
                try:
                    btn = self.query_one("#btn-start", ToolbarButton)
                    btn.label = "▶ Start"
                except Exception:
                    pass
            return
        self._paused = True
        self._stop_requested = True
        # Stop ScanService (holds references to spider + engine)
        try:
            svc = self._active_service
            if svc is not None:
                svc.request_stop()
        except Exception:
            pass
        # Fallback: stop engine directly if service is not available
        try:
            engine = self._scanner_api._get_engine()
            engine.request_stop()
        except Exception:
            pass
        self._log("[yellow]STOP[/yellow] Stop requested — finishing current tasks…")

    def action_resume_scan(self) -> None:
        """Resume scanning with the same parameters."""
        if self._scanning:
            return
        if not self._paused or self._last_targets is None:
            self.app.notify("No paused scan to resume", severity="warning")
            return

        self._paused = False
        self._scanning = True
        self._stop_requested = False

        try:
            self.query_one("#btn-start", ToolbarButton).disabled = True
            self.query_one("#btn-stop",  ToolbarButton).disabled = False
        except Exception:
            pass

        self._log("[bold green]RESUME[/bold green] Continuing scan…")
        self._run_active_scan(
            self._last_targets,
            self._last_check_names,
            self._last_threads,
            self._last_delay_sec,
            self._last_depth,
            self._last_pages,
            resume=True,
        )

    # ── passive toggle ─────────────────────────────────────────────────────────

    def action_toggle_passive(self) -> None:
        btn = self.query_one("#btn-passive", ToolbarButton)
        if self._passive_enabled:
            self._passive_enabled = False
            btn.update("● Passive: OFF")
            btn.remove_class("passive-on")
            self._detach_passive()
            self._log("[dim]Passive scanner disabled.[/dim]")
            self.app.notify("Passive scanner OFF", timeout=2)
            self._notify_dashboard_passive(False)
        else:
            self._passive_enabled = True
            btn.update("● Passive: ON")
            btn.add_class("passive-on")
            self._attach_passive()
            self._log("[green]Passive scanner ENABLED[/green] — monitoring proxy traffic.")
            self.app.notify("Passive scanner ON", timeout=2)
            self._notify_dashboard_passive(True)

    def _notify_dashboard_passive(self, enabled: bool) -> None:
        """Notify the Dashboard of a passive scanner status change via EventBus."""
        try:
            from pentool.core.event_bus import get_event_bus
            from pentool.core.events import PassiveScanToggled
            get_event_bus().emit(PassiveScanToggled(enabled=enabled, source="scanner"))
        except Exception:
            pass

    def _attach_passive(self) -> None:
        try:
            db_path   = self.app.db_path
            proxy_api = self.app.get_proxy_api()
            self._scanner_api = self._get_or_create_api(db_path)
            self._scanner_api.set_passive_callback(self.add_finding)
            self._attach_passive_worker(proxy_api)
        except Exception as exc:
            logger.warning("_attach_passive: %s", exc)

    @work
    async def _attach_passive_worker(self, proxy_api) -> None:
        try:
            await self._scanner_api.attach_passive(proxy_api)
        except Exception as exc:
            logger.warning("_attach_passive_worker: %s", exc)

    def _detach_passive(self) -> None:
        if self._scanner_api:
            self._detach_passive_worker()

    @work
    async def _detach_passive_worker(self) -> None:
        try:
            await self._scanner_api.detach_passive()
        except Exception:
            pass

    # ── report ─────────────────────────────────────────────────────────────────

    def action_generate_report(self) -> None:
        from pentool.tui.dialogs.file_selector import FileSelectorDialog, FileSelectorMode

        def _on_path(path: str | None) -> None:
            if not path:
                return
            fmt = "html"
            if path.endswith(".json"):
                fmt = "json"
            elif path.endswith(".csv"):
                fmt = "csv"
            self._generate_report_worker(path, fmt)

        self.app.push_screen(
            FileSelectorDialog(mode=FileSelectorMode.SAVE, title="Save Report"),
            _on_path,
        )

    @work
    async def _generate_report_worker(self, path: str, fmt: str) -> None:
        try:
            db_path = self.app.db_path
            self._scanner_api = self._get_or_create_api(db_path)
            await self._scanner_api.generate_report(path, fmt)
            self.app.notify(f"Report saved: {path}", severity="information")
        except Exception as exc:
            self.app.notify(f"Report failed: {exc}", severity="error")

    # ── clear ──────────────────────────────────────────────────────────────────

    def action_generate_pro_report(self) -> None:
        from pentool.core.license import get_session_license
        info = get_session_license()
        if not info.has_feature("reports_pro"):
            self.app.notify(  # type: ignore[attr-defined]
                "🔒 PRO Report requires PRO license — go to Settings → License",
                severity="warning",
                timeout=4,
            )
            return

        if not self._rows:
            self.app.notify("No findings to report", severity="warning", timeout=3)  # type: ignore[attr-defined]
            return

        from pentool.tui.dialogs.file_selector import FileSelectorDialog, FileSelectorMode

        def _on_path(path: str | None) -> None:
            if not path:
                return
            self._generate_pro_report_worker(path)

        self.app.push_screen(  # type: ignore[attr-defined]
            FileSelectorDialog(mode=FileSelectorMode.SAVE, title="Save PRO Report (HTML)"),
            _on_path,
        )

    @work
    async def _generate_pro_report_worker(self, path: str) -> None:
        try:
            from pentool.plugins.builtin.reports_pro import generate_bulk_report
            generate_bulk_report(self._rows, template="Generic", output_path=path)
            self.app.notify(  # type: ignore[attr-defined]
                f"✓ PRO Report saved: {path}",
                severity="information",
                timeout=5,
            )
        except Exception as exc:
            self.app.notify(f"PRO Report failed: {exc}", severity="error", timeout=5)  # type: ignore[attr-defined]

    # ── clear ──────────────────────────────────────────────────────────────────

    def action_clear(self) -> None:
        t = self._active_tab
        if t is None:
            return
        t.rows.clear()
        t.row_sources.clear()
        t.current_finding = None
        t.paused = False
        t.last_targets = None
        t.detail_panel_open = False
        tid = t.tab_id
        try:
            self._reset_table()
            self.query_one(f"#progress-label-{tid}", Static).update("—")
            self.query_one(f"#scan-progress-{tid}",  ProgressBar).update(progress=0)
            self.query_one(f"#scan-log-{tid}",       RichLog).clear()
            try:
                self.query_one(f"#detail-request-{tid}", HttpView).clear()
            except Exception:
                pass
            try:
                self.query_one(f"#detail-proof-{tid}", TextArea).load_text("")
            except Exception:
                pass
            try:
                self.query_one(f"#detail-response-{tid}", HttpView).clear()
            except Exception:
                pass
            try:
                panel = self.query_one(f"#detail-panel-{tid}")
                panel.styles.height = 0
                panel.display = False
            except Exception:
                pass
            self.query_one("#btn-send-repeater", ToolbarButton).disabled = True
            btn_start = self.query_one("#btn-start", ToolbarButton)
            btn_start.label = "▶ Start"
            btn_start.disabled = False
            self.query_one("#btn-stop", ToolbarButton).disabled = True
            self._update_label()
            self._log("Cleared all findings and log.")
        except Exception:
            pass

    # ── false positive ─────────────────────────────────────────────────────────

    def action_mark_false_positive(self) -> None:
        tid = self._active_tab_id or ""
        try:
            table = self.query_one(f"#findings-table-{tid}", DataTable)
            idx = table.cursor_row
            if 0 <= idx < len(self._rows):
                finding = self._rows[idx]
                self._mark_fp_worker(finding.id)
        except Exception:
            pass

    @work
    async def _mark_fp_worker(self, finding_id: str) -> None:
        if not self._scanner_api:
            return
        try:
            await self._scanner_api.mark_false_positive(finding_id)
            self._load_passive_findings()
            self.app.notify("Marked as false positive", severity="information")
        except Exception as exc:
            logger.warning("_mark_fp_worker: %s", exc)

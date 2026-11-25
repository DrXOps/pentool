"""Intruder screen — automated attacks with payloads.

Per-tab full UI: every tab is a self-contained screen with its own toolbar,
positions, payloads, results, details and filter. Only ➕Tab / ➖Tab stay
global.
"""

from __future__ import annotations

import asyncio
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from textual import events as _tevents
from textual import on
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.css.query import NoMatches
from textual.widgets import Input, Label, ListItem, ListView, ProgressBar, Static, TabPane, TextArea

from pentool.api.intruder_api import (
    AttackType,
    ChainedPayloadSource,
    CharPayloadSource,
    FilePayloadSource,
    IntruderAttack,
    IntruderConfig,
    IntruderResult,
    NumericPayloadSource,
    ProcessedPayloads,
    count_lines_with_progress,
    count_markers,
    process_payload,
)
from pentool.api.payload_serialization import deserialize_payloads, serialize_payloads
from pentool.collections.filter_predicate import FilterPredicate, FilterSpec
from pentool.core.activity import set_activity
from pentool.core.logging import get_logger
from pentool.tui.dialogs.intruder_generate import GenerateDialog
from pentool.tui.dialogs.intruder_input import InputDialog
from pentool.tui.dialogs.intruder_smart_payloads import SmartPayloadsDialog
from pentool.tui.header import HeaderAction, HeaderSpec
from pentool.tui.hotkeys.defaults import INTRUDER_BINDINGS
from pentool.tui.markup import esc
from pentool.tui.messages import SendToRepeater
from pentool.tui.mixins.ai_sync import AiModeSyncMixin
from pentool.tui.mixins.autosave import AutoSaveMixin
from pentool.tui.mixins.content_clipboard_mixin import ContentClipboardMixin
from pentool.tui.mixins.request_context_menu import RequestContextMenuMixin
from pentool.tui.screens.base import BaseModuleScreen
from pentool.tui.screens.module_screen import ModuleScreen
from pentool.tui.widgets.content_panel import ContentPanel
from pentool.tui.widgets.data_table_mixins import SortableTableMixin
from pentool.tui.widgets.intruder_filter_bar import IntruderFilterBar as _IntruderFilterBar
from pentool.tui.widgets.intruder_results_table import IntruderResultsTable
from pentool.tui.widgets.nice_checkbox import NiceCheckbox as Checkbox
from pentool.tui.widgets.request_editor import HttpView, _load_into_textarea
from pentool.tui.widgets.resize_handle import ResizeHandle
from pentool.tui.widgets.tab_panel import TabbedContentPanel
from pentool.tui.widgets.table_factory import make_table
from pentool.tui.widgets.toolbar import Toolbar
from pentool.tui.widgets.toolbar_button import ToolbarButton

logger = get_logger(__name__)

_CSS = (Path(__file__).parent / "screen.tcss").read_text(encoding="utf-8")

if TYPE_CHECKING:
    from pentool.api.intruder_api import IntruderAPI


# Module constants
_ATTACK_LABELS = {
    AttackType.SNIPER: "Sniper",
    AttackType.BATTERING_RAM: "Battering Ram",
    AttackType.PITCHFORK: "Pitchfork",
    AttackType.CLUSTER_BOMB: "Cluster Bomb",
}
_ATTACK_DESCRIPTIONS = {
    AttackType.SNIPER: "One payload set, one position at a time",
    AttackType.BATTERING_RAM: "One payload set, all positions simultaneously",
    AttackType.PITCHFORK: "Multiple sets, parallel (zip)",
    AttackType.CLUSTER_BOMB: "Cartesian product of all sets",
}

_RESULTS_COL_NAMES = ["#", "Payload(s)", "Status", "Length", "Time(ms)", "Error"]

_PAYLOAD_LIST_PREVIEW_LIMIT = 500
_LAZY_SOURCE_TYPES = (
    FilePayloadSource,
    NumericPayloadSource,
    CharPayloadSource,
    ChainedPayloadSource,
)
DataTable = IntruderResultsTable


#: Suffixes for the per-tab widget ids. ``_wid(tab_id, suffix)`` turns a
#: suffix into a real id (``<suffix>-<tab_id>``); both halves of the
#: contract — the id used at mount and the id used at query — must name
#: the same entry here, so a typo cannot survive as a runtime LookupError
#: on a tab the user happens to open (F-023).
class _TabId:
    # ATTACK TOOLBAR + TEMPLATE
    TOOLBAR = "toolbar"
    BTN_ATTACK_TYPE = "btn-attack-type"
    BTN_ADD_MARKER = "btn-add-marker"
    BTN_CLEAR_MARKERS = "btn-clear-markers"
    BTN_MARK_PARAMS = "btn-mark-params"
    ATTACK_TYPE_DESC = "attack-type-desc"
    TEMPLATE_PANEL = "template-panel"
    POSITIONS_PANEL = "positions-panel"

    # PAYLOADS
    PAYLOAD_BUTTONS_TOOLBAR = "payload-buttons-toolbar"
    BTN_PAYLOAD_SET = "btn-payload-set"
    BTN_PAYLOAD_ADD = "btn-payload-add"
    BTN_PAYLOAD_REMOVE = "btn-payload-remove"
    BTN_PAYLOAD_CLEAR = "btn-payload-clear"
    BTN_PAYLOAD_LOAD = "btn-payload-load"
    BTN_PAYLOAD_GENERATE = "btn-payload-generate"
    BTN_PAYLOAD_SMART = "btn-payload-smart"
    PAYLOAD_LIST = "payload-list"
    PAYLOAD_COUNT_LABEL = "payload-count-label"
    PAYLOADS_PANEL = "payloads-panel"

    # PROCESSING
    PROCESSING_BAR = "processing-bar"
    PROC_URL_ENCODE = "proc-url-encode"
    PROC_BASE64 = "proc-base64"
    PROC_HTML_ENCODE = "proc-html-encode"
    PROC_MD5 = "proc-md5"

    # RESULTS
    RESULTS_AREA = "results-area"
    INTRUDER_FILTER_BAR = "intruder-filter-bar"
    PROGRESS_ROW = "progress-row"
    ATTACK_PROGRESS = "attack-progress"
    PROGRESS_LABEL = "progress-label"
    RESULTS_TABLE = "results-table"

    # DETAIL
    INTRUDER_DETAIL_PANEL = "intruder-detail-panel"
    DETAIL_REQUEST = "detail-request"
    DETAIL_REQUEST_COL = "detail-request-col"
    DETAIL_RESPONSE = "detail-response"
    DETAIL_RESPONSE_COL = "detail-response-col"

    # LAYOUT
    TOP_AREA = "top-area"
    BODY_RIGHT = "body-right"
    TAB_BODY = "tab-body"


@dataclass
class _IntruderTabState:
    """State of a single Intruder tab — now holds EVERYTHING, including
    results, details and the filter (these used to be global)."""

    tab_id: str = ""
    tab_uid: str = ""
    name: str = "New Tab"
    target_url: str = ""
    template_text: str = ""
    attack_type: AttackType = AttackType.SNIPER
    thread_count: int = 1
    delay_ms: int = 0
    payload_sources: list = field(default_factory=list)
    active_set_idx: int = 0
    all_results: list = field(default_factory=list)
    filtered_results: list = field(default_factory=list)
    result_count: int = 0
    current_result: "IntruderResult | None" = None
    filter_spec: "FilterSpec | None" = None
    grep_match_patterns: list = field(default_factory=list)
    grep_extract_patterns: list = field(default_factory=list)
    grep_only_match: bool = False
    running: bool = False
    paused: bool = False
    stop_requested: bool = False
    turbo_mode: bool = False
    payload_load_in_progress: bool = False
    last_payload_sets: list | None = None
    # This tab's attack — isolated and able to run in parallel (IntruderAttack).
    # attack_task — the asyncio.Task from run(); used for careful cancellation.
    attack: "IntruderAttack | None" = None


class IntruderScreen(
    BaseModuleScreen,
    ModuleScreen,
    ContentClipboardMixin,
    AutoSaveMixin,
    SortableTableMixin,
    RequestContextMenuMixin,
    AiModeSyncMixin,
):
    """Intruder module screen — per-tab isolated full UI."""

    DEFAULT_CSS = _CSS
    BINDINGS = INTRUDER_BINDINGS

    # TabRenameMixin config (kept for compatibility, but delegates to TabbedContentPanel)
    _rename_input_id: str = "intruder-rename-input"
    _rename_tab_prefix: str = "intruder-tab-"
    _rename_tabs_widget_id: str = "intruder-tabs"

    # RequestContextMenuMixin config
    _cm_show_copy_url = False
    _cm_show_send_repeater = True
    _cm_show_send_intruder = False
    _cm_show_send_scanner = False

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        # Which tab's values the global toolbar is currently showing. Needed so
        # TabDeactivated does not overwrite a tab's state with a neighbour's
        # values (see _save_toolbar_to_tab).
        self._toolbar_tab_id: str | None = None
        # Legacy _tabs kept for backward compatibility (tests)
        self._tabs: list[_IntruderTabState] = []
        self._active_tab_id: str | None = None
        self._tab_counter: int = 0
        # ── Tab factory for TabbedContentPanel ──
        import uuid as _uuid

        def _factory(tab_id: str, name: str) -> _IntruderTabState:
            return _IntruderTabState(
                tab_id=tab_id,
                name=name,
                tab_uid=_uuid.uuid4().hex,
                thread_count=10,
                delay_ms=0,
            )

        self._tab_factory = _factory
        # ── API ──
        self._api = None
        # Saved selection in template-editor (for ADD §§ after focus loss)
        self._last_editor_selection: tuple | None = None
        self._last_click_time: float = 0.0
        # Auto-save state
        self._state_loaded: bool = False
        self._running_save_tasks: list[str] = []
        # tab_id -> live attack. Exists solely so on_unmount can shut attacks
        # down: by that point the DOM tree is gone and the tab states cannot be
        # fetched from the panel any more.
        self._live_attacks: dict[str, object] = {}

    # ── Active tab state ─────────────────────────────────────────────────

    @property
    def _tc_panel(self) -> TabbedContentPanel:
        """The TabbedContentPanel widget."""
        return self.query_one("#intruder-tabs", TabbedContentPanel)

    @property
    def _active_tab(self) -> _IntruderTabState | None:
        """Return active tab state, with fallback to old _tabs list for tests."""
        try:
            panel = self._tc_panel
            st = panel.active_state
            if st is not None:
                return st  # type: ignore[return-value]
        except Exception as exc:
            # Below is the fallback path for tests without compose. The log line
            # tells "no screen yet" apart from "panel exists but is broken".
            logger.debug("intruder: tab panel state unavailable: %s", exc)
        # Fallback for tests (without compose)
        if hasattr(self, "_tabs") and self._active_tab_id:
            for t in self._tabs:
                if t.tab_id == self._active_tab_id:
                    return t
        return None

    # Proxy properties for backward compatibility (all read from _active_tab)
    @property
    def _attack_type(self) -> AttackType:
        t = self._active_tab
        return t.attack_type if t else AttackType.SNIPER

    @_attack_type.setter
    def _attack_type(self, v: AttackType) -> None:
        t = self._active_tab
        if t:
            t.attack_type = v

    @property
    def _payloads(self) -> list:
        t = self._active_tab
        return t.payload_sources if t else [[]]

    @_payloads.setter
    def _payloads(self, v: list) -> None:
        t = self._active_tab
        if t:
            t.payload_sources = v

    @property
    def _active_set_idx(self) -> int:
        t = self._active_tab
        return t.active_set_idx if t else 0

    @_active_set_idx.setter
    def _active_set_idx(self, v: int) -> None:
        t = self._active_tab
        if t:
            t.active_set_idx = v

    @property
    def _all_results(self) -> list:
        t = self._active_tab
        return t.all_results if t else []

    @_all_results.setter
    def _all_results(self, v: list) -> None:
        t = self._active_tab
        if t:
            t.all_results = v

    @property
    def _filtered_results(self) -> list:
        t = self._active_tab
        return t.filtered_results if t else []

    @_filtered_results.setter
    def _filtered_results(self, v: list) -> None:
        t = self._active_tab
        if t:
            t.filtered_results = v

    @property
    def _current_result(self) -> "IntruderResult | None":
        t = self._active_tab
        return t.current_result if t else None

    @_current_result.setter
    def _current_result(self, v: "IntruderResult | None") -> None:
        t = self._active_tab
        if t:
            t.current_result = v

    @property
    def _filter_spec(self) -> "FilterSpec | None":
        t = self._active_tab
        return t.filter_spec if t else None

    @_filter_spec.setter
    def _filter_spec(self, v: "FilterSpec | None") -> None:
        t = self._active_tab
        if t:
            t.filter_spec = v

    @property
    def _payload_load_in_progress(self) -> bool:
        t = self._active_tab
        return t.payload_load_in_progress if t else False

    @_payload_load_in_progress.setter
    def _payload_load_in_progress(self, v: bool) -> None:
        t = self._active_tab
        if t:
            t.payload_load_in_progress = v

    # ── Per-tab widget helpers ────────────────────────────────────────────

    @staticmethod
    def _wid(tab_id: str, suffix: str) -> str:
        return f"{suffix}-{tab_id}"

    def _tab_widget(self, tab_id: str, suffix: str, widget_cls: type) -> object:
        return self.query_one(f"#{self._wid(tab_id, suffix)}", widget_cls)

    def _template_editor(self, tab: _IntruderTabState | None = None) -> ContentPanel:
        """Return the tab's ContentPanel (the active tab's by default)."""
        tab = tab if tab is not None else self._active_tab
        if tab is None:
            raise LookupError("no active tab")
        wid = self._wid(tab.tab_id, _TabId.TEMPLATE_PANEL)
        return self.query_one(f"#{wid}", ContentPanel)

    # ── BUILD TAB UI — per-tab: only template + payloads ──────────────────
    # Toolbar, results, detail panel are global, built in compose().
    # This keeps tabs light, fast to switch, and their titles never get lost.

    def _build_tab_ui(self, state: _IntruderTabState, tab_id: str) -> TabPane:
        """Create a TabPane.
        Returns an empty placeholder — the content is mounted step by step in
        _mount_tab_body() AFTER add_pane() has added the tab to the DOM. That
        way a heavy Intruder tab does not overload the layout on add_pane, and
        the tab header is visible immediately.
        """
        placeholder = Static("…", id=f"tab-placeholder-{tab_id}")
        return TabPane(state.name, placeholder, id=tab_id)

    async def _mount_tab_body(self, tab_id: str, state: _IntruderTabState) -> None:
        """Assemble the full attack content inside the TabPane, step by step.

        Called from _on_tab_created (after the tab has been added to the DOM
        and became active). tab-body is a vertical stack:
        toolbar → top (template+payloads) → results → filter → detail.
        The method is async for a single await: call_after_refresh runs the
        returned coroutine through commit, so mounting gets to finish before
        the tab data is loaded.
        """

        # ── Attack toolbar (per-tab): Sniper/Add§§/Clear§§/Auto§§ ─────────────
        # (as in _compose_positions before multi-tab, a315ada)
        # The label and description come from state, not a literal: a tab can be
        # restored from the DB with an attack type already chosen, and it used to
        # show "Sniper ▼" with the sniper description at state=battering_ram.
        attack_toolbar = Toolbar(
            Label("Attack:", classes="toolbar-label"),
            ToolbarButton(f"{_ATTACK_LABELS[state.attack_type]} ▼", self._wid(tab_id, _TabId.BTN_ATTACK_TYPE)),
            ToolbarButton("Add §§", self._wid(tab_id, _TabId.BTN_ADD_MARKER)),
            ToolbarButton("Clear §§", self._wid(tab_id, _TabId.BTN_CLEAR_MARKERS)),
            ToolbarButton("Auto §§", self._wid(tab_id, _TabId.BTN_MARK_PARAMS)),
            Static(
                _ATTACK_DESCRIPTIONS.get(state.attack_type, ""),
                id=self._wid(tab_id, _TabId.ATTACK_TYPE_DESC),
                classes="attack-type-desc",
            ),
            id=self._wid(tab_id, _TabId.TOOLBAR),
        )

        # ── Template editor (in the left positions column) ─────────────
        template = Vertical(
            Static("Positions", classes="section-title panel-title"),
            attack_toolbar,
            ContentPanel(
                title="Request Template",
                widget_type="textarea",
                initial_text=state.template_text or "GET / HTTP/1.1\r\nHost: example.com\r\n\r\n",
                role="request-editable-plain",
                id=self._wid(tab_id, _TabId.TEMPLATE_PANEL),
                classes="intruder-template-panel",
            ),
            id=self._wid(tab_id, _TabId.POSITIONS_PANEL),
            classes="intruder-positions-panel card",
        )

        # ── Payloads panel ──────────────────────────────────────────────
        # Separators are built in groups (`Toolbar.row`): yes between groups, no
        # inside a group. There must be no leading rule before the label — it
        # divided emptiness (a note from testing).
        # Labels were shortened: the long ones ("Load from file…", "Generate…")
        # pushed the toolbar off the screen edge together with "Smart…".
        # A separator between EVERY pair of actions (reported: "no divider
        # between Add and Clear"). Labels are short: the long ones
        # ("Load from file…", "Generate…") pushed "Smart" off screen.
        # No dividers: one flat row of payload actions, same look as the module
        # header and the Repeater toolbar. Short labels keep the row inside the
        # panel width.
        payloads_toolbar = Toolbar(
            Label("Payload set:"),
            ToolbarButton("Set 1 ▼", self._wid(tab_id, _TabId.BTN_PAYLOAD_SET)),
            ToolbarButton("Add", self._wid(tab_id, _TabId.BTN_PAYLOAD_ADD)),
            ToolbarButton("Rem", self._wid(tab_id, _TabId.BTN_PAYLOAD_REMOVE)),
            ToolbarButton("Clr", self._wid(tab_id, _TabId.BTN_PAYLOAD_CLEAR)),
            ToolbarButton("Load", self._wid(tab_id, _TabId.BTN_PAYLOAD_LOAD)),
            ToolbarButton("Gen", self._wid(tab_id, _TabId.BTN_PAYLOAD_GENERATE)),
            ToolbarButton("Smart", self._wid(tab_id, _TabId.BTN_PAYLOAD_SMART), classes="pro-locked"),
            id=self._wid(tab_id, _TabId.PAYLOAD_BUTTONS_TOOLBAR),
        )

        pldiv = Vertical(
            Static("Payloads", classes="section-title panel-title"),
            payloads_toolbar,
            # The counter sits above the list, as in the pre-multi-tab layout: it
            # shows how many lines arrived while loading a file, and during
            # streaming it grows visibly — below the list that would be hidden.
            Static("", id=self._wid(tab_id, _TabId.PAYLOAD_COUNT_LABEL), classes="payload-count-label"),
            ListView(id=self._wid(tab_id, _TabId.PAYLOAD_LIST), classes="intruder-payload-list"),
            classes="intruder-payloads-panel card",
            id=self._wid(tab_id, _TabId.PAYLOADS_PANEL),
        )

        # ── Processing bar ──────────────────────────────────────────────
        proc = Horizontal(
            Label("Processing:", classes="proc-label"),
            Checkbox("URL encode", id=self._wid(tab_id, _TabId.PROC_URL_ENCODE), value=False),
            Checkbox("Base64", id=self._wid(tab_id, _TabId.PROC_BASE64), value=False),
            Checkbox("HTML encode", id=self._wid(tab_id, _TabId.PROC_HTML_ENCODE), value=False),
            Checkbox("MD5", id=self._wid(tab_id, _TabId.PROC_MD5), value=False),
            classes="proc-bar",
            id=self._wid(tab_id, _TabId.PROCESSING_BAR),
        )

        # ── Top area (template | handle | payloads + processing) ───────
        top_area = Horizontal(
            template,
            # The Positions|Payloads divider existed in the pre-multi-tab layout
            # and was lost in the move: both panels are fixed, and on a wide
            # terminal the template could not be given more room.
            # The targets are direct children of top-area: ResizeHandle writes
            # width into them directly, while `payloads-panel` is nested inside
            # `body-right`, so resizing its width would change nothing.
            ResizeHandle(
                self._wid(tab_id, _TabId.POSITIONS_PANEL),
                self._wid(tab_id, _TabId.BODY_RIGHT),
            ),
            Vertical(pldiv, proc, id=self._wid(tab_id, _TabId.BODY_RIGHT), classes="intruder-body-right"),
            id=self._wid(tab_id, _TabId.TOP_AREA),
            classes="intruder-top-area",
        )

        # ── Results + progress ──────────────────────────────────────────
        # The filter is ON TOP, above the table (as in the original layout a315ada:
        # filter bar → progress → results-table → detail).
        filter_bar = _IntruderFilterBar(id=self._wid(tab_id, _TabId.INTRUDER_FILTER_BAR))
        results_col = Vertical(
            filter_bar,
            Horizontal(
                ProgressBar(total=100, id=self._wid(tab_id, _TabId.ATTACK_PROGRESS), show_eta=False),
                Static(
                    "0/0 (0%)",
                    id=self._wid(tab_id, _TabId.PROGRESS_LABEL),
                    classes="progress-label",
                ),
                id=self._wid(tab_id, _TabId.PROGRESS_ROW),
                classes="progress-row",
            ),
            make_table(
                _RESULTS_COL_NAMES,
                table_id=self._wid(tab_id, _TabId.RESULTS_TABLE),
                widths=[5, 45, 8, 10, 10, 30],
                # The screen's table subclass adds the "extract column" action and
                # posts the messages the screen listens to.
                table_class=DataTable,
            ),
            id=self._wid(tab_id, _TabId.RESULTS_AREA),
            classes="intruder-results-area",
        )

        # ── Detail panel (per-tab) ─────────────────────────────────────
        detail_panel = Horizontal(
            Vertical(
                HttpView("Request", id=self._wid(tab_id, _TabId.DETAIL_REQUEST), classes="detail-view"),
                id=self._wid(tab_id, _TabId.DETAIL_REQUEST_COL),
                classes="detail-col",
            ),
            ResizeHandle(
                self._wid(tab_id, _TabId.DETAIL_REQUEST_COL),
                self._wid(tab_id, _TabId.DETAIL_RESPONSE_COL),
            ),
            Vertical(
                HttpView("Response", id=self._wid(tab_id, _TabId.DETAIL_RESPONSE), classes="detail-view"),
                id=self._wid(tab_id, _TabId.DETAIL_RESPONSE_COL),
                classes="detail-col",
            ),
            id=self._wid(tab_id, _TabId.INTRUDER_DETAIL_PANEL),
            classes="intruder-detail-panel",
        )

        inner = Vertical(
            top_area,
            ResizeHandle(
                self._wid(tab_id, _TabId.TOP_AREA),
                self._wid(tab_id, _TabId.RESULTS_AREA),
                vertical=True,
            ),
            results_col,
            detail_panel,
            id=self._wid(tab_id, _TabId.TAB_BODY),
            classes="intruder-tab-body",
        )

        try:
            pane = self.query_one(f"#{tab_id}", TabPane)
            # Remove the placeholder
            try:
                ph = pane.query_one(f"#tab-placeholder-{tab_id}")
                ph.remove()
            except Exception as exc:
                # The stub is already gone from a previous pass — a normal case.
                # The log entry tells it apart from a typo in the placeholder id.
                logger.debug("intruder: placeholder for %s not removed: %s", tab_id, exc)
            # mount() is not an instant insert: it is scheduled in the message
            # queue, and without await the children land in the DOM some
            # arbitrary tick later. Then _refresh_payload_list looks for the
            # ListView too early, catches NoMatches and swallows it, leaving the
            # tab with an empty payload list. AwaitComplete guarantees the tree
            # is already assembled by the next line.
            await pane.mount(inner)
        except Exception as exc:
            logger.debug("_mount_tab_body: %s", exc)
            return
        # New tabs start with their AI control visible; match the current mode
        # right away instead of waiting for the next AiModeChanged (F-022).
        self.call_after_refresh(self._apply_ai_visibility_after_mount, tab_id)
        # Tooltips are set here: the tab buttons enter the DOM on this very line.
        self._apply_tab_tooltips(tab_id)
        # Tab content — right after mounting, without deferring to yet another
        # refresh: a tab can come from the DB already with payload_sources,
        # attack_type and an active set, and until this line it would show an
        # empty list and "Set 1 ▼" regardless of what the DB holds.
        # The helpers read _active_tab, so during batch restore (tabs are
        # created in a row and the last one is active) this call fills the
        # active tab, not the one whose body just arrived — it is data-driven,
        # so the data always lands in its own widgets. The other tabs are
        # filled on TabActivated, when the user opens them.
        self._load_active_tab_content()

    def _apply_ai_visibility_after_mount(self, tab_id: str) -> None:
        """Re-apply AI visibility once a freshly mounted tab is in the DOM."""
        try:
            from pentool.core.config import get_config

            self._sync_ai_ui_for_tab(tab_id, bool(get_config().ai_enabled))
        except Exception as exc:
            logger.debug("_apply_ai_visibility_after_mount: %s", exc)

    # ── TabbedContentPanel message handlers ───────────────────────────────
    # When the user switches tabs, TabbedContentPanel posts
    # TabDeactivated (old tab) and TabActivated (new tab).

    @on(TabbedContentPanel.TabDeactivated, "#intruder-tabs")
    def _on_tab_deactivated(self, event: TabbedContentPanel.TabDeactivated) -> None:
        """Save the old tab's state before the switch."""
        state = event.tab_state
        if not isinstance(state, _IntruderTabState):
            return
        # Save template text from per-tab editor
        try:
            wid = self._wid(state.tab_id, _TabId.TEMPLATE_PANEL)
            panel = self.query_one(f"#{wid}", ContentPanel)
            w = panel.content_widget
            if isinstance(w, TextArea):
                state.template_text = w.text
        except Exception:
            # The old template stays in state — the user's edits in this tab are
            # lost on switching. Exactly the class of loss described in the
            # comment below, hence an error with a traceback.
            logger.error("intruder: template text not saved for tab %s", state.tab_id, exc_info=True)
        # Threads/Delay/Turbo live in the global toolbar and describe the active
        # tab, so they must be captured BEFORE the toolbar is redrawn for the
        # new tab. Without this the values survived only in state defaults: the
        # user typed 77 threads, switched to another tab and came back to the
        # same 10 — the edit was lost silently.
        self._save_toolbar_to_tab(state)
        self._auto_save_tab(state)

    def _save_toolbar_to_tab(self, state: _IntruderTabState) -> None:
        """Move Threads/Delay/Turbo from the global toolbar into the tab state.

        Errors are not propagated: the toolbar may not be mounted yet (the
        first tab is created in ``on_mount`` before layout), and that is no
        reason to break tab switching.
        """
        if self._toolbar_tab_id != state.tab_id:
            # The toolbar shows a DIFFERENT tab (batch restore creates tabs in a
            # row, and _sync_toolbar_from_tab only gets through for the active
            # one). Saving now would write somebody else's values into this tab:
            # 55 threads restored from the DB turned into the default 10 on the
            # very first switch.
            return
        try:
            threads = self.query_one("#intruder-threads", Input)
            delay = self.query_one("#intruder-delay", Input)
            turbo = self.query_one("#intruder-turbo", Checkbox)
        except NoMatches:
            return
        # An empty field is not zero threads but "the user erased the value";
        # attack start treats it as the default, so here too we leave the state
        # as is instead of saving 0.
        if threads.value.strip():
            try:
                state.thread_count = int(threads.value)
            except ValueError:
                pass
        if delay.value.strip():
            try:
                state.delay_ms = int(delay.value)
            except ValueError:
                pass
        state.turbo_mode = bool(turbo.value)

    @on(TabbedContentPanel.TabActivated, "#intruder-tabs")
    def _on_tab_activated(self, event: TabbedContentPanel.TabActivated) -> None:
        """Tab switched — refresh the UI (the data is already in state)."""
        # Data, not just the table: restoring from the DB creates tabs in a
        # batch and makes the last one active, so the other bodies (and their
        # payload lists) are filled here, when the user opens them.
        self._load_active_tab_content()
        # Sync the global toolbar with the active tab
        tab = self._active_tab
        if tab is not None:
            self._sync_toolbar_from_tab(tab)

    def _sync_toolbar_from_tab(self, tab: _IntruderTabState) -> None:
        """Move the active tab's status/parameters into the global toolbar.

        Start/Stop, Threads, Delay, Turbo reflect the active tab; each tab keeps
        its own values in state, so on switching the toolbar shows exactly the
        active one.
        """
        try:
            self.query_one("#intruder-threads", Input).value = str(tab.thread_count if tab.thread_count else 10)
            self.query_one("#intruder-delay", Input).value = str(tab.delay_ms if tab.delay_ms else 0)
            cb = self.query_one("#intruder-turbo", Checkbox)
            # Turbo cannot be enabled in FREE mode
            from pentool.core.license import get_session_license

            is_pro = get_session_license().is_pro() if get_session_license() else False
            if is_pro:
                cb.value = tab.turbo_mode
                cb.disabled = False
            else:
                cb.value = False
                cb.disabled = True
                cb.tooltip = "⚡ Turbo mode requires PRO license"
            self._toolbar_tab_id = tab.tab_id
        except Exception as exc:
            logger.debug("_sync_toolbar_from_tab: %s", exc)
        # Start/Pause/Stop and the counters live in the module header now.
        self.refresh_header()

    @on(TabbedContentPanel.TabCreated, "#intruder-tabs")
    def _on_tab_created(self, event: TabbedContentPanel.TabCreated) -> None:
        """A new tab was created — mount the full attack content into the pane.

        add_pane has already added the placeholder and header, and the tab is
        active. Now the heavy content (toolbar/results/detail) is loaded in
        stages, so the layout can arrange the empty tab and does not lose the
        headers.
        """
        state = event.tab_state
        if not isinstance(state, _IntruderTabState):
            return
        # _load_active_tab_content is NOT queued here next to _mount_tab_body:
        # both functions would go into one batch of refresh callbacks, and then
        # _refresh_payload_list looks for the ListView before mount() has
        # actually added the tab content to the DOM. NoMatches is swallowed by
        # try/except, so a tab restored from the DB stayed with an empty payload
        # list until the first manual action. The data load is scheduled by
        # _mount_tab_body itself — already after pane.mount(inner).
        self.call_after_refresh(self._mount_tab_body, state.tab_id, state)

    @on(TabbedContentPanel.TabClosed, "#intruder-tabs")
    def _on_tab_closed(self, event: TabbedContentPanel.TabClosed) -> None:
        """Tab closed — shut down its attack and load the remaining one.

        The panel posts the closed state in the message: the tab is already
        removed from ``_states``, and without it there is no way to tell whose
        attack to stop.
        """
        closed = event.tab_state
        if isinstance(closed, _IntruderTabState) and (closed.running or closed.attack is not None):
            self._stop_tab_attack(closed)
            if self._active_tab is None:
                self.refresh_header()
        state = self._active_tab
        if state:
            self._rebuild_table_data()

    async def on_event(self, event: _tevents.Event) -> None:
        """Double-click in template-editor — select the word under the cursor."""
        if isinstance(event, _tevents.MouseDown) and event.button == 1 and not event.ctrl:
            now = time.monotonic()
            if (now - self._last_click_time) < 0.4:
                self._last_click_time = 0.0
                await super().on_event(event)
                try:
                    from textual.widgets.text_area import Selection

                    editor = self._template_editor()
                    area = editor.content_widget
                    if isinstance(area, TextArea):

                        def _sel():
                            cursor = area.cursor_location
                            row, col = cursor
                            lines = area.text.split("\n")
                            if row >= len(lines):
                                return
                            line = lines[row]
                            start = col
                            while start > 0 and (line[start - 1].isalnum() or line[start - 1] in "_-./§"):
                                start -= 1
                            end = col
                            while end < len(line) and (line[end].isalnum() or line[end] in "_-./§"):
                                end += 1
                            if start < end:
                                area.selection = Selection((row, start), (row, end))

                        self.call_after_refresh(_sel)
                except (LookupError, NoMatches) as exc:
                    # No tab, or its body is not mounted — the double click will
                    # select nothing. Exactly these two causes are named:
                    # `LookupError` from `_template_editor` and `NoMatches` from
                    # `content_widget`; a typo in this block will surface.
                    logger.debug("op: double-click select skipped: %s", exc)
                return
            self._last_click_time = now
        await super().on_event(event)

    # ── Compose ──────────────────────────────────────────────────────────

    def compose(self) -> ComposeResult:
        # ── Attack parameters live here; the actions moved to the module header ──
        # Start / Pause / Stop, Clear results, Export CSV and tab add/remove are
        # header buttons now (`header_spec()`), so only the per-attack inputs stay
        # in the panel — no duplicated controls.
        yield Toolbar(
            Label("Threads:", classes="toolbar-label"),
            Input("10", id="intruder-threads", placeholder="10", compact=True, type="integer"),
            Label("Delay(ms):", classes="toolbar-label"),
            Input("0", id="intruder-delay", placeholder="0", compact=True, type="integer"),
            Checkbox("⚡ Turbo", id="intruder-turbo", value=False),
            id="intruder-global-toolbar",
        )

        # ── TabbedContentPanel (full per-tab UI inside) ───────────────────
        yield TabbedContentPanel[_IntruderTabState](
            id="intruder-tabs",
            tab_id_prefix="intruder-tab-",
            build_tab_ui=self._build_tab_ui,
            save_tab=None,
            load_tabs=None,
            rename_input_id="intruder-rename-input",
        )

    # ── Module header (see pentool/tui/header.py) ─────────────────────────
    def header_spec(self) -> HeaderSpec:
        """Attack controls of the *active* tab, shown in the module header.

        Two state buttons, as in the standard: Start (which turns into Pause
        while the attack runs, and into Resume when it is paused) and Stop. Tab
        add/remove and Beautify sit on the left next to Export/Clear.
        """
        tab = self._active_tab
        running = bool(tab and tab.running)
        paused = bool(tab and tab.paused)
        done = tab.result_count if tab else 0

        if running and not paused:
            primary = HeaderAction("pause", "⏸ Pause", enabled=True)
        elif paused:
            primary = HeaderAction("start", "▶ Resume", enabled=True)
        else:
            primary = HeaderAction("start", "▶ Start", enabled=True)

        counters: tuple[str, ...] = (f"{done} req",) if done else ()
        return HeaderSpec(
            state=(primary, HeaderAction("stop", "■ Stop", enabled=running)),
            counters=counters,
            actions=(
                HeaderAction("new_tab", "➕ Tab"),
                HeaderAction("close_tab", "➖ Tab"),
                HeaderAction("beautify", "✨ Beautify"),
                HeaderAction("export", "⤓ Export CSV", enabled=bool(done)),
                HeaderAction("clear", "⌫ Clear results", enabled=bool(done)),
            ),
            # No `⋯` menu: every control Intruder has fits in the row, and the
            # only thing that used to hide there (Mark params) is available from
            # the panel toolbar ("Auto §§").
            more=(),
        )

    #: Header buttons (see `header_spec`) → methods that run them.
    ACTIONS = {
        "start": "_header_start_or_resume",
        "pause": "action_toggle_pause",
        "stop": "action_stop",
        "export": "_export_csv",
        "clear": "_clear_results",
        "new_tab": "action_new_tab",
        "close_tab": "action_close_tab",
        "beautify": "_beautify_active_template",
    }

    def _header_start_or_resume(self) -> None:
        """One button for both: a paused attack resumes, anything else starts."""
        tab = self._active_tab
        self.action_resume() if (tab and tab.paused) else self.action_start_attack()

    def _beautify_active_template(self) -> None:
        """Beautify the template of the active tab (header button).

        Delegates to the editor widget that already knows how to split headers
        from the body and pretty-print JSON/XML — no second implementation here.
        """
        tab = self._active_tab
        if tab is None:
            return
        try:
            panel = self._template_editor(tab)
            changed = panel.content_widget.beautify_body()  # type: ignore[attr-defined]
        except Exception:
            logger.warning("intruder: template beautify failed for %s", tab.tab_id, exc_info=True)
            return
        if changed:
            self.notify("Template beautified", timeout=2)
        else:
            self.notify("Nothing to beautify — no valid JSON/XML body found", severity="warning", timeout=3)

    def header_tab_selected(self, tab_id: str) -> None:
        """Sub-tabs belong to the tab body (Positions/Payloads/…), not the header."""
        return None

    # ── Tab lifecycle (action_*) — delegates to TabbedContentPanel ─────

    def action_new_tab(self) -> None:
        """Create a new tab with the default state."""
        self._tab_counter_adjust()
        # The new tab's data is loaded by _load_active_tab_content, which
        # _mount_tab_body schedules after mounting the content. Scheduling it
        # here is not allowed: at this point _post_tab_messages has not created
        # a single per-tab widget yet.
        self._tc_panel.action_new_tab()

    def _tab_counter_adjust(self) -> None:
        """Adjust _tab_counter to match TabbedContentPanel (test compatibility)."""
        pass

    def action_close_tab(self) -> None:
        self._tc_panel.action_close_tab()

    def _load_active_tab_content(self) -> None:
        """Load the active tab's data into the freshly mounted widgets.

        Called from _mount_tab_body as its last line — after pane.mount(inner)
        has actually added the widgets to the DOM. A tab can come from the DB
        already with payload_sources, attack_type and an active set index, so
        every per-tab widget takes its value from state: previously the payload
        list stayed empty and the set label read "Set 1 ▼" regardless of what
        the DB held.

        The results table is rebuilt unconditionally, even without an active
        tab: that is what the former _on_tab_activated did, and the call from it
        must not lose this behaviour because of an early return.
        """
        tab = self._active_tab
        if tab is not None:
            self._sync_attack_type_ui(tab)
            self._update_payload_select()
        self._rebuild_table_data()

    def _save_current_tab_state(self) -> None:
        """Save current tab state to memory."""
        tab = self._active_tab
        if tab is None:
            return
        try:
            editor = self._template_editor()
            w = editor.content_widget
            if isinstance(w, TextArea):
                tab.template_text = w.text
        except Exception:
            # The template in state stays as before, and `_auto_save_tab` below
            # will save exactly that to the DB — so the edit will not survive a
            # restart, even though autosave "worked". Data loss → error.
            logger.error("intruder: current template text not saved", exc_info=True)
        self._auto_save_tab(tab)

    # ── DB persistence ────────────────────────────────────────────────────────

    def _auto_save_tab(self, state: _IntruderTabState) -> None:
        """Save tab state to database (fire-and-forget)."""
        if self._api is None:
            return
        try:
            self.run_worker(
                self._api.save_state(
                    tab_name=state.name,
                    template=state.template_text,
                    attack_type=state.attack_type.value,
                    payloads=serialize_payloads(state.payload_sources),
                    tab_uid=state.tab_uid,
                ),
                exclusive=False,
            )
        except Exception:
            # The tab autosave did not get queued: edits live only in memory and
            # will vanish on restart without saying anything.
            logger.exception("_auto_save_tab failed")

    def _load_tabs_from_db(self) -> None:
        """Load saved tabs from database and restore them."""
        if self._api is None:
            return
        self.run_worker(
            self._do_load_tabs_from_db(self._api),
            exclusive=False,
            exit_on_error=False,
        )

    async def _do_load_tabs_from_db(self, api: "IntruderAPI") -> None:
        """Async: load tabs from DB and create TabPane widgets."""
        try:
            tabs_data = await api.get_tabs()
        except Exception:
            logger.error("intruder: tabs not restored from DB", exc_info=True)
            return
        if not tabs_data:
            return

        for td in tabs_data:
            tab_uid = td.get("tab_uid", "") or td.get("id", "")
            if not tab_uid:
                continue
            # Avoid duplicates
            existing = self._tc_panel.get_tab_id_by_uid(tab_uid)
            if existing:
                continue

            # Create state. ``tab_id`` is a placeholder: action_new_tab()
            # assigns the real one, because only the panel knows its counter.
            # The name is the DB's ``tab_name`` — reading ``td["name"]`` here
            # always missed, since get_tabs() builds the dict with that key,
            # so every restored tab was called the same fallback "Tab 0" and
            # a multi-tab project came back as N identical labels.
            name = td.get("tab_name") or td.get("name") or "Tab"
            state = _IntruderTabState(
                tab_id="",
                tab_uid=tab_uid,
                name=name,
                target_url=td.get("target_url", ""),
                template_text=td.get("template", ""),
            )
            at_str = td.get("attack_type", "sniper")
            try:
                state.attack_type = AttackType(at_str)
            except Exception:
                logger.warning("intruder: saved attack type not restored, using sniper", exc_info=True)
                state.attack_type = AttackType.SNIPER
            payloads_raw = td.get("payloads", [[]])
            if payloads_raw and isinstance(payloads_raw, list):
                state.payload_sources = deserialize_payloads(payloads_raw)

            # Add tab via TabbedContentPanel
            self._tc_panel.action_new_tab(state=state)

    # ── Rename (BaseModuleScreen interface) ───────────────────────────────────

    def _start_rename(self, tab_id: str) -> None:
        """Tab rename: the input lives in the tab panel.

        The screen used to mount its OWN `Input` with the same id as the
        panel's — two fields with an identical id ended up in the tree,
        `query_one` found the hidden first one, and the visible one never got
        focus. From the outside this looks like "F2/double click does not work".
        """
        try:
            self._tc_panel._start_rename(tab_id)
        except Exception:
            # The tab is not renamed — and this is the only place where the
            # cause is visible: the panel itself swallows the error into debug.
            logger.exception("intruder: rename not started for %s", tab_id)

    def _rename_tab(self, tab_id: str, new_name: str) -> None:
        state = None
        for t in self._tc_panel.all_states:
            if getattr(t, "tab_id", None) == tab_id:
                state = t
                break
        if state is None:
            return
        state.name = new_name
        self._tc_panel.update_tab_label(tab_id, new_name)
        self._auto_save_tab(state)

    # ── Mount, show ──────────────────────────────────────────────────────

    def on_unmount(self) -> None:
        """The screen is going away — no attack may outlive it.

        ``cancel_node`` also takes down leftover loads; attacks are stopped by
        name so that the worker goes down first and the attack itself after
        (see ``_stop_tab_attack``).
        """
        # The DOM is already gone by now (Textual unmounts the subtree before a
        # node's on_unmount), so the attacks are taken from our own dict.
        for tab_id, attack in list(self._live_attacks.items()):
            try:
                self.workers.cancel_group(self, self._attack_group(tab_id))
            except Exception:
                # The attack worker was not taken down: it keeps writing to the
                # DB of a project that is already closing and runs to the end
                # after leaving the screen. That is a leak; keep the full cause.
                logger.exception("on_unmount: cancel_group failed for %s", tab_id)
            try:
                # The stop worker lives on the App: the screen is about to have
                # all its workers cancelled, and it must not be caught by that.
                self.app.run_worker(attack.stop(), exit_on_error=False)  # type: ignore[attr-defined]
            except Exception:
                # The attack was not shut down — after leaving the screen there
                # will be no UI left that could stop it.
                logger.exception("on_unmount: attack.stop failed for %s", tab_id)
        self._live_attacks.clear()
        try:
            self.workers.cancel_node(self)
        except Exception:
            # Leftover loads outlive the screen and may write to a closed DB.
            logger.exception("on_unmount: cancel_node failed")

    def on_mount(self) -> None:
        # Create the first tab via TabbedContentPanel
        tc = self._tc_panel
        tc.set_default_state_factory(self._tab_factory)
        tc.action_new_tab()
        # Sync the global toolbar with the first (active) tab
        if self._active_tab is not None:
            self._sync_toolbar_from_tab(self._active_tab)
        self._setup_tooltips()
        self._load_state_from_db()
        self._apply_license_limits()
        self._init_ai_sync()

    def on_show(self) -> None:
        self._rebuild_table_data()
        self._sync_ai_ui()

    # ── AI sync ──────────────────────────────────────────────────────────

    def _sync_ai_ui(self) -> None:
        """Show/hide the AI-gated controls according to ``Config.ai_enabled``.

        The controls are addressed by id, one per tab, because every tab owns its
        own toolbar: ``btn-payload-smart-<tab_id>``. A class query would work
        too, but it would silently skip a tab whose UI is not mounted yet, and
        the class name (``pro-locked``) does not say what the control gates
        (REPORT.md F-022). Tabs still being built are skipped here and caught
        by ``_sync_ai_ui_for_tab`` when their UI mounts.
        """
        try:
            from pentool.core.config import get_config

            ai_on = bool(get_config().ai_enabled)
            for tab in self._tabs:
                self._sync_ai_ui_for_tab(tab.tab_id, ai_on)
        except Exception as exc:
            logger.debug("_sync_ai_ui: %s", exc)

    def _sync_ai_ui_for_tab(self, tab_id: str, ai_on: bool) -> None:
        """Apply the AI visibility to one tab's gated controls, if it is mounted."""
        try:
            button = self.query_one(f"#{self._wid(tab_id, _TabId.BTN_PAYLOAD_SMART)}", ToolbarButton)
        except NoMatches:
            return  # tab UI is being (re)built; on_mount will call back
        button.display = ai_on

    def _sync_attack_type_ui(self, tab: _IntruderTabState) -> None:
        """Bring the attack-type button and its description to ``tab.attack_type``.

        Tab state is the single source of truth, and it is displayed by two
        different widgets. While every writer (menu, DB load, tab activation)
        patched them itself, they drifted apart: ``_do_load_state`` wrote
        ``⚡ Sniper`` into the button and left the description alone, while
        ``_load_active_tab_content`` touched neither — a tab opened after a type
        change showed the label of the previous value.

        NoMatches is not propagated: the tab body may not be mounted yet, and
        then the UI is fixed up by ``_load_active_tab_content`` on activation.
        """
        try:
            btn = self.query_one(f"#{self._wid(tab.tab_id, _TabId.BTN_ATTACK_TYPE)}", ToolbarButton)
            btn.label = f"{_ATTACK_LABELS.get(tab.attack_type, 'Sniper')} ▼"
        except NoMatches:
            return
        try:
            self.query_one(f"#{self._wid(tab.tab_id, _TabId.ATTACK_TYPE_DESC)}", Static).update(
                _ATTACK_DESCRIPTIONS.get(tab.attack_type, "")
            )
        except NoMatches:
            logger.debug("_sync_attack_type_ui: description not mounted for %s", tab.tab_id)

    #: Tooltips for the tab-body buttons. Start/Stop/Pause moved to the module
    #: header (see `header_spec`), so there are no global toolbar tooltips left.
    _GLOBAL_TOOLTIPS: dict[str, str] = {}  # noqa: RUF012 - intentionally empty class table

    #: Tooltips for the buttons living inside a tab — the id is built by ``_wid``.
    _TAB_TOOLTIPS: dict[str, str] = {
        _TabId.BTN_ADD_MARKER: "Wrap selected text in §markers§",
        _TabId.BTN_CLEAR_MARKERS: "Remove all §markers§ from template",
        _TabId.BTN_PAYLOAD_ADD: "Add new payload manually",
        _TabId.BTN_PAYLOAD_LOAD: "Load payloads from file",
    }

    def _setup_tooltips(self) -> None:
        """Tooltips for the global toolbar buttons (tabs are handled separately)."""
        for wid, tip in self._GLOBAL_TOOLTIPS.items():
            try:
                self.query_one(f"#{wid}", ToolbarButton).tooltip = tip
            except NoMatches:
                # StartStopWidget is not mounted yet — not our case, but only
                # "no widget" should be swallowed, not any error.
                logger.debug("_setup_tooltips: #%s not mounted yet", wid)

    def _apply_tab_tooltips(self, tab_id: str) -> None:
        """Tooltips for the per-tab buttons. Called after the tab body is mounted.

        They cannot be set from ``on_mount``: ``compose`` creates only empty
        TabPanes, the bodies are mounted later (``_mount_tab_body``), so a query
        by ``#…-<tab_id>`` found nothing, NoMatches was swallowed, and no
        tooltips appeared for the first tab or for new ones.
        """
        for suffix, tip in self._TAB_TOOLTIPS.items():
            try:
                self.query_one(f"#{self._wid(tab_id, suffix)}", ToolbarButton).tooltip = tip
            except NoMatches:
                logger.debug("_apply_tab_tooltips: #%s not mounted", self._wid(tab_id, suffix))

    # ── API lazy singleton ───────────────────────────────────────────────

    def _get_api(self) -> "IntruderAPI | None":
        from pentool.api.intruder_api import IntruderAPI

        if self._api is None:
            db_path = self._get_db_path()
            if not db_path:
                return None
            self._api = IntruderAPI(db_path=db_path)
        return self._api

    async def reload_from_project(self, db_path: str) -> None:
        """Point persistent IntruderAPI at a different project DB (project switch)."""
        from pentool.api.intruder_api import IntruderAPI

        # Cancel any in-flight auto-save workers
        self._cancel_save_workers()
        try:
            self.workers.cancel_node(self)
        except Exception:
            logger.error("intruder: in-flight workers not cancelled before project switch", exc_info=True)

        # Close all tabs via TabbedContentPanel
        tc = self._tc_panel
        await tc.close_all()
        tc.action_new_tab()

        if self._api is None:
            self._api = IntruderAPI(db_path=db_path)
        else:
            await self._api.switch_db(db_path)
        self._state_loaded = False
        self._load_state_from_db()
        self._load_results_from_db()

    # ── Results loading ──────────────────────────────────────────────────

    def _load_results_from_db(self) -> None:
        api = self._get_api()
        if api is None:
            return
        self.run_worker(self._do_load_results(api), exclusive=False, exit_on_error=False)

    async def _do_load_results(self, api: "IntruderAPI", order_by: str | None = None, order_dir: str = "desc") -> None:
        """Load the results from SQL honouring FilterSpec and ORDER BY."""
        try:
            tab = self._active_tab
            if tab is None:
                return
            sql_predicates: list[FilterPredicate] = []
            fs = tab.filter_spec
            if fs and not fs.is_empty:
                for p in fs.predicates:
                    if p.field in ("status", "length"):
                        db_field = "response_status" if p.field == "status" else "response_length"
                        sql_predicates.append(FilterPredicate(db_field, p.operator, p.value))
            sql_filter = FilterSpec(predicates=sql_predicates) if sql_predicates else None
            results = await api.get_results_from_db(
                limit=100000,
                filters=sql_filter,
                order_by=order_by,
                desc=(order_dir == "desc"),
            )
        except Exception:
            logger.error("intruder: results not loaded", exc_info=True)
            return
        if not results:
            tab.all_results = []
            tab.filtered_results = []
            self._redraw_results()
            return
        if order_by:
            tab.all_results = list(results)
        else:
            tab.all_results = list(reversed(results))
        tab.filtered_results = list(tab.all_results)
        self._redraw_results()

    def _load_state_from_db(self) -> None:
        api = self._get_api()
        if api is None:
            return
        self.run_worker(self._do_load_state(api), exclusive=False, exit_on_error=False)

    def _apply_license_limits(self) -> None:
        from pentool.core.features import get_limit
        from pentool.core.license import get_session_license

        license_info = get_session_license()
        is_pro = license_info.is_pro() if license_info else False
        try:
            threads_input = self.query_one("#intruder-threads", Input)
            delay_input = self.query_one("#intruder-delay", Input)
            turbo_checkbox = self.query_one("#intruder-turbo", Checkbox)
            # The numbers live in `core/features.py` (LIMITS), not here: the site, the
            # licence portal and the input hints must not drift apart.
            plan = "pro" if is_pro else "free"
            max_threads = get_limit("intruder_max_threads", plan)
            min_delay = get_limit("intruder_min_delay_ms", plan)
            if not is_pro:
                threads_input.placeholder = f"Max {max_threads}"
                delay_input.placeholder = f"Min {min_delay}"
                turbo_checkbox.disabled = True
                turbo_checkbox.tooltip = "⚡ Turbo mode requires PRO license"
            else:
                threads_input.placeholder = f"Max {max_threads}"
                delay_input.placeholder = f"{min_delay}"
                turbo_checkbox.disabled = False
                turbo_checkbox.tooltip = "⚡ Turbo: HTTP pipelining, connection pooling"
        except NoMatches as exc:
            logger.debug("_apply_license_limits error: %s", exc)

    async def _do_load_state(self, api: "IntruderAPI") -> None:
        try:
            tab = self._active_tab
            if tab is None:
                return
            _tab_uid = tab.tab_uid
            state = await api.load_state("", tab_uid=_tab_uid)
            if not state:
                return
            template = state.get("template", "")
            if template:
                try:
                    editor = self._template_editor()
                    w = editor.content_widget
                    if isinstance(w, TextArea):
                        w.text = template
                except Exception:
                    # A saved template exists but the editor is empty: the tab
                    # will open blank even though the data sits in the DB. That
                    # is data loss on restore, hence an error with a traceback.
                    logger.error("intruder: saved template not restored for tab %s", _tab_uid, exc_info=True)
            attack_type_str = state.get("attack_type", "sniper")
            try:
                tab.attack_type = AttackType(attack_type_str)
                self._sync_attack_type_ui(tab)
            except ValueError as exc:
                logger.debug("_do_load_state: unknown attack_type %r: %s", attack_type_str, exc)
            payloads = state.get("payloads", [[]])
            if payloads and isinstance(payloads, list):
                tab.payload_sources = deserialize_payloads(payloads)
                self._update_payload_select()
                self.call_after_refresh(self._refresh_payload_list)
            self._state_loaded = True
        except Exception:
            logger.error("intruder: tab state not loaded", exc_info=True)

    def _auto_save_state(self, tab: _IntruderTabState | None = None) -> None:
        """Save the tab state (the active tab by default).

        An explicit ``tab`` is needed by paths that edit a non-active tab (a
        menu opened before switching): otherwise a neighbouring tab would be
        written to the DB.
        """
        api = self._get_api()
        if api is None:
            return
        try:
            tab = tab if tab is not None else self._active_tab
            if tab is None:
                return
            # Read the template from the per-tab editor
            template = ""
            try:
                editor = self._template_editor(tab)
                w = editor.content_widget
                if isinstance(w, TextArea):
                    template = w.text
            except Exception:
                logger.error("intruder: template text not read for autosave", exc_info=True)
                template = tab.template_text
            self._start_save_worker(
                api.save_state(
                    tab_name=tab.name,
                    template=template,
                    attack_type=tab.attack_type.value,
                    payloads=serialize_payloads(tab.payload_sources),
                    tab_uid=tab.tab_uid,
                ),
                f"intruder-save-state-{time.monotonic_ns()}",
            )
        except Exception:
            logger.error("intruder: tab state not saved", exc_info=True)

    def _auto_save_result(self, result: IntruderResult, tab: "_IntruderTabState | None" = None) -> None:
        """Save one result; ``tab`` keeps it attached to its own tab.

        The call site passed a second argument while the method accepted only
        ``result`` — every finished result raised ``TypeError`` ("takes 2
        positional arguments but 3 were given"), so an attack died on its
        first response.
        """
        api = self._get_api()
        if api is None:
            return
        try:
            project_id = getattr(self.app, "project_id", None)
            tab_uid = getattr(tab, "tab_uid", "") if tab is not None else ""
            self._start_save_worker(
                api.save_result(result, project_id=project_id, tab_uid=tab_uid),
                f"intruder-save-result-{time.monotonic_ns()}",
            )
        except Exception:
            logger.error("intruder: result not saved", exc_info=True)

    # ── @on handlers — ToolbarButton.Pressed (global buttons only) ──────
    # Per-tab buttons carry the -{tab_id} suffix — they are caught by the @on
    # without a selector, which matches any ToolbarButton.Pressed, drops the
    # known global ones (btn-start, btn-stop...) and dispatches the rest per tab.

    @on(ToolbarButton.Pressed)
    def _on_toolbar_pressed(self, event: ToolbarButton.Pressed) -> None:
        """Common dispatch for ToolbarButton.

        Skips btn-start/btn-stop/btn-pause — they are handled by StartStopWidget
        itself (which posts separate messages).
        """
        btn = event.button
        btn_id = btn.id or ""

        # ── Skip the StartStopWidget buttons ──────────────────────────
        if btn_id in ("btn-start", "btn-stop", "btn-pause"):
            return

        tab = self._active_tab
        tab_id = tab.tab_id if tab else None

        # ── Global (outside tabs) ─────────────────────────────────────
        if btn_id == "btn-new-tab":
            self.action_new_tab()
            return
        if btn_id == "btn-close-tab":
            self.action_close_tab()
            return

        # ── Per-tab ───────────────────────────────────────────────────
        if tab_id is None:
            return
        suffix = f"-{tab_id}"
        base = btn_id[: -len(suffix)] if btn_id.endswith(suffix) else btn_id

        dispatch = {
            "btn-clear-results": lambda: self._clear_results(),
            "btn-export-csv": lambda: self._export_csv(),
            "btn-add-marker": lambda: self._add_marker_around_selection(),
            "btn-clear-markers": lambda: self._clear_markers(),
            "btn-mark-params": lambda: self._prompt_auto_mark(),
            "btn-attack-type": lambda: self._open_attack_type_menu(btn),
            "btn-payload-set": lambda: self._open_payload_set_menu(btn),
            "btn-payload-add": lambda: self._add_payload_manual(),
            "btn-payload-remove": lambda: self._remove_selected_payload(),
            "btn-payload-clear": lambda: self._clear_payloads(),
            "btn-payload-load": lambda: self._load_payloads_from_file(),
            "btn-payload-generate": lambda: self._open_generate_dialog(),
            "btn-payload-smart": lambda: self._open_smart_payloads_dialog(),
        }
        handler = dispatch.get(base)
        if handler:
            handler()

    # ── TextArea handlers ───────────────────────────────────────────────

    @on(TextArea.SelectionChanged)
    def on_template_selection_changed(self, event: TextArea.SelectionChanged) -> None:
        """Remember the selection in template-editor."""
        try:
            our_editor = self._template_editor()
            # `TextArea.SelectionChanged` carries `text_area`; there is no
            # `widget` on this message, and asking for it raised `AttributeError`
            # on every selection until the handler was narrowed — the old broad
            # `except Exception` swallowed it, so the remembered selection was
            # always empty and «mark selection» never had a range to work with.
            if event.text_area is not our_editor.content_widget:
                return
        except (LookupError, NoMatches):
            # No tab yet (`LookupError` from `_template_editor`) or its body is
            # not mounted (`NoMatches` from `content_widget`): the event came
            # from a TextArea outside the template, so nothing to remember.
            # A broad `except` would also swallow a typo in the event field name.
            return
        sel = event.selection
        if sel.start != sel.end:
            self._last_editor_selection = (sel.start, sel.end)
            self._cursor_only_count = 0
        else:
            self._cursor_only_count = getattr(self, "_cursor_only_count", 0) + 1
            if self._cursor_only_count >= 2:
                self._last_editor_selection = None

    @on(TextArea.Changed)
    def on_template_text_changed(self, event: TextArea.Changed) -> None:
        """Recompute payload sets on template text change."""
        try:
            our_editor = self._template_editor()
            # Same message shape as above: `Changed` carries `text_area`.
            # Reading `event.widget` raised `AttributeError` on every keystroke
            # in the template editor, so payload sets were never recomputed and
            # the auto-save never ran — the handler looked implemented and was
            # dead.
            if event.text_area is not our_editor.content_widget:
                return
        except (LookupError, NoMatches):
            # The edit came from a foreign editor (no template, or the tab body
            # is not mounted) — payload sets are not recomputed. Silence here is
            # not a consequence but the norm: typing in a response editor must
            # not touch Intruder's payload select.
            return
        self._update_payload_select()
        if self._state_loaded:
            self._auto_save_state()

    # ── Filter bar handlers ──────────────────────────────────────────────

    @on(_IntruderFilterBar.FilterChanged)
    def on_intruder_filter_bar_changed(self, event: _IntruderFilterBar.FilterChanged) -> None:
        tab = self._active_tab
        if tab is None:
            return
        spec = event.spec
        # Read the previous state BEFORE clearing it. This line used to sit
        # right after the three assignments below, so ``had_extract`` was
        # always False: adding the pattern worked, removing it never did —
        # the "Extract" column stayed in the table with nothing to fill it.
        had_extract = bool(tab.grep_extract_patterns)
        filter_predicates: list[FilterPredicate] = []
        tab.grep_match_patterns = []
        tab.grep_extract_patterns = []
        tab.grep_only_match = False
        if spec and not spec.is_empty:
            for p in spec.predicates:
                match p.field:
                    case "grep_match":
                        tab.grep_match_patterns = [str(p.value)]
                    case "grep_extract":
                        tab.grep_extract_patterns = [str(p.value)]
                    case "grep_only_match":
                        tab.grep_only_match = bool(p.value)
                    case _:
                        filter_predicates.append(p)
        tab.filter_spec = FilterSpec(predicates=filter_predicates) if filter_predicates else None
        logger.info(
            "INTRUDER: filter applied — predicates=%d match=%d extract=%d only_match=%s",
            len(filter_predicates),
            len(tab.grep_match_patterns),
            len(tab.grep_extract_patterns),
            tab.grep_only_match,
        )
        has_extract = bool(tab.grep_extract_patterns)
        if has_extract != had_extract:
            try:
                table = self._results_table()
                if table and has_extract:
                    table.add_column("Extract")
                elif table:
                    table.remove_column("Extract")
            except NoMatches as exc:
                # The results table is not in the tree (the tab is not mounted)
                # — the column will be added when it is assembled.
                logger.debug("intruder: Extract column not toggled: %s", exc)
            except Exception:
                # The column stayed as it was: the extract filter is applied, but
                # the data from the responses cannot be shown on screen.
                logger.exception("intruder: Extract column toggle failed")
        tab = self._active_tab
        if not (tab and tab.running):
            api = self._get_api()
            if api:
                self.run_worker(self._do_load_results(api), exclusive=False, exit_on_error=False)
            else:
                self._redraw_results()
        else:
            self._redraw_results()

    # ── Attack type menu ────────────────────────────────────────────────

    def _open_attack_type_menu(self, btn: ToolbarButton) -> None:
        tab = self._active_tab
        if tab is None:
            return
        items = [(at.value, ("✓ " if at == tab.attack_type else "  ") + label) for at, label in _ATTACK_LABELS.items()]
        r = btn.region
        x = r.x
        y = r.y + 1
        screen = self
        t_id = tab.tab_id

        def _on_select(action: str) -> None:
            # The attack type belongs to the tab the menu was opened from. While
            # the callback took ``_active_tab`` but painted by ``t_id``, switching
            # tabs with the menu open changed one tab and showed another.
            tab = screen._tc_panel.get_state(t_id)
            if tab is None:
                return
            try:
                tab.attack_type = AttackType(action)
            except ValueError as exc:
                logger.warning("_on_select attack type: %s", exc)
                return
            screen._sync_attack_type_ui(tab)
            screen._update_payload_select(tab)
            screen._auto_save_state(tab)

        self.app.show_context_menu(items, x, y, callback=_on_select)

    def _open_payload_set_menu(self, btn: ToolbarButton) -> None:
        tab = self._active_tab
        if tab is None:
            return
        n = len(tab.payload_sources) or 1
        items = [(str(i), ("✓ " if i == tab.active_set_idx else "  ") + f"Set {i + 1}") for i in range(n)]
        r = btn.region
        x = r.x
        y = r.y + 1
        t_id = tab.tab_id

        def _on_select(action: str) -> None:
            # The set belongs to the tab the menu was opened from: while the
            # callback took ``_active_tab``, switching tabs with the menu open
            # changed one tab's set and redrew another tab's list.
            tab = self._tc_panel.get_state(t_id)
            if tab is None:
                return
            try:
                tab.active_set_idx = int(action)
            except ValueError as exc:
                logger.debug("_open_payload_set_menu: bad action %r: %s", action, exc)
                return
            # The label and list are recomputed by _update_payload_select: it
            # also clamps the index to the set bounds and tops up missing sets.
            self._update_payload_select(tab)
            self._highlight_nth_marker(tab.active_set_idx, tab)

        self.app.show_context_menu(items, x, y, callback=_on_select)

    # ── Marker operations ───────────────────────────────────────────────

    def _add_marker_around_selection(self) -> None:
        try:
            editor = self._template_editor()
            w = editor.content_widget
            if not isinstance(w, TextArea):
                return
            text = w.text
            if self._last_editor_selection is not None:
                raw_start, raw_end = self._last_editor_selection
            else:
                sel = w.selection
                raw_start, raw_end = sel.start, sel.end
            start, end = (raw_start, raw_end) if raw_start <= raw_end else (raw_end, raw_start)
            lines = text.split("\n")

            def to_offset(row: int, col: int) -> int:
                return sum(len(lines[i]) + 1 for i in range(row)) + col

            s = to_offset(*start)
            e = to_offset(*end)
            if s == e:
                new_text = text[:s] + "§§" + text[s:]
            else:
                new_text = text[:s] + "§" + text[s:e] + "§" + text[e:]
            w.load_text(new_text)
            _load_into_textarea(w, new_text, ["§"])
            w.move_cursor(start)
            self._update_payload_select()
        except Exception as exc:
            from pentool.core.error_guard import err

            err(exc, "Intruder ADD error", self, severity="error")

    def _clear_markers(self) -> None:
        try:
            editor = self._template_editor()
            w = editor.content_widget
            if not isinstance(w, TextArea):
                return
            text = w.text
            cleaned = re.sub(r"§([^§]*)§", r"\1", text)
            cleaned = cleaned.replace("§", "")
            w.load_text(cleaned)
            self._update_payload_select()
        except Exception as exc:
            logger.debug("op: %s", exc)

    def _prompt_auto_mark(self) -> None:
        try:
            editor = self._template_editor()
            w = editor.content_widget
            if not isinstance(w, TextArea):
                return
            text = w.text
        except Exception:
            return
        if not text:
            return
        lines = text.split("\n")
        has_header_body_sep = False
        content_type = ""
        has_json = False
        has_xml = False
        has_urlencoded = False
        body_start = 0
        for i, line in enumerate(lines):
            if line.strip() == "" and i > 0:
                has_header_body_sep = True
                body_start = i + 1
                break
        for line in lines[1:body_start]:
            if line.lower().startswith("content-type:"):
                raw = line.split(":", 1)[1].strip().lower()
                content_type = raw
                has_json = "json" in raw
                has_xml = "xml" in raw
                has_urlencoded = "urlencoded" in raw
                break
        if not has_json and has_header_body_sep and body_start < len(lines):
            body_text = "\n".join(lines[body_start:]).strip()
            if body_text and (body_text.startswith("{") or body_text.startswith("[")):
                try:
                    import json as _json

                    _json.loads(body_text)
                    has_json = True
                except (ValueError, TypeError) as exc:
                    logger.debug("op: %s", exc)
        has_query = "?" in lines[0] if lines else False
        has_cookie = any(line.lower().startswith("cookie:") for line in lines[1:body_start])
        from pentool.tui.dialogs.intruder_auto_mark import IntruderAutoMarkDialog

        self.app.push_screen(
            IntruderAutoMarkDialog(
                has_json=has_json,
                has_xml=has_xml,
                has_urlencoded=has_urlencoded or (not content_type),
                has_query=has_query,
                has_cookie=has_cookie,
                has_header=True,
            ),
            lambda result: self._mark_all_params(result) if result else None,
        )

    def _mark_all_params(self, options: dict | None = None) -> None:
        # A full copy from the original file (all the marking methods)
        try:
            editor = self._template_editor()
            w = editor.content_widget
            if not isinstance(w, TextArea):
                return
            text = w.text
        except Exception:
            return
        if not text:
            return
        lines = text.split("\n")
        if not lines:
            return
        content_type = ""
        body_lines_start = None
        for i, line in enumerate(lines):
            if line.strip() == "" and i > 0:
                body_lines_start = i + 1
                break
        for line in lines[1:]:
            if line.strip() == "":
                break
            if line.lower().startswith("content-type:"):
                content_type = line.split(":", 1)[1].strip().lower()
                break

        def _mark_query_params(line: str) -> str:
            def mark_val(m: re.Match) -> str:
                key = m.group(1)
                val = m.group(2)
                if "§" in val:
                    return m.group(0)
                return f"{key}=§{val}§"

            if "?" in line:
                pre, qs = line.split("?", 1)
                qs_marked = re.sub(r"([^&=\s]+)=([^&\s§]+)", mark_val, qs)
                return f"{pre}?{qs_marked}"
            return line

        if options is None or options.get("query", True):
            if lines:
                lines[0] = _mark_query_params(lines[0])
        if (
            (options is None or options.get("body_form", True))
            and "urlencoded" in content_type
            and body_lines_start is not None
        ):
            for i in range(body_lines_start, len(lines)):
                if lines[i].strip():

                    def mark_val_body(m: re.Match) -> str:
                        key = m.group(1)
                        val = m.group(2)
                        if "§" in val:
                            return m.group(0)
                        return f"{key}=§{val}§"

                    lines[i] = re.sub(r"([^&=\s]+)=([^&\s§]+)", mark_val_body, lines[i])
        if "json" in content_type and body_lines_start is not None:
            body_text = "\n".join(lines[body_lines_start:])
            import json as _json

            try:
                parsed = _json.loads(body_text)
                mark_keys = options is None or options.get("json_keys", True)
                mark_vals = options is None or options.get("json_vals", True)

                def _mark_json(obj):
                    if isinstance(obj, dict):
                        marked = {}
                        for k, v in obj.items():
                            k_str = str(k)
                            if mark_keys and "§" not in k_str and k_str.strip():
                                k_str = f"§{k_str}§"
                            marked[k_str] = _mark_json(v)
                        return marked
                    elif isinstance(obj, list):
                        return [_mark_json(item) for item in obj]
                    elif isinstance(obj, str):
                        if mark_vals and obj.strip() and "§" not in obj:
                            return f"§{obj}§"
                        return obj
                    elif obj is True:
                        return "§true§" if mark_vals else True
                    elif obj is False:
                        return "§false§" if mark_vals else False
                    elif obj is None:
                        return "§null§" if mark_vals else None
                    elif isinstance(obj, (int, float)):
                        return f"§{obj}§" if mark_vals else obj
                    return obj

                marked_body = _json.dumps(_mark_json(parsed), indent=2, ensure_ascii=False)
                new_lines = lines[:body_lines_start] + marked_body.split("\n")
                lines = new_lines
            except Exception as exc:
                # The body is declared as JSON but did not parse — no markers
                # went into it, and the attack will run without positions there.
                logger.debug("payload markers: JSON body not marked: %s", exc)
        if options is None or options.get("cookie", True):
            for i, line in enumerate(lines):
                if line.lower().startswith("cookie:"):
                    prefix = line[:7]
                    rest = line[7:]

                    def mark_cookie_val(m: re.Match) -> str:
                        key = m.group(1)
                        val = m.group(2)
                        if "§" in val:
                            return m.group(0)
                        return f"{key}=§{val}§"

                    lines[i] = prefix + re.sub(r"([^;=\s]+)=([^;§\s]+)", mark_cookie_val, rest)
        if options is None or options.get("header", True):
            for i, line in enumerate(lines):
                if i == 0:
                    continue
                if line.strip() == "":
                    break
                if ":" in line and not line.lower().startswith("cookie:"):
                    name, _, val = line.partition(":")
                    val_stripped = val.strip()
                    if val_stripped and "§" not in val_stripped:
                        lines[i] = f"{name}: §{val_stripped}§"
        _xml_selected = options is None or options.get("xml_tags", False) or options.get("xml_content", False)
        if _xml_selected and "xml" in content_type and body_lines_start is not None:
            body_text = "\n".join(lines[body_lines_start:])
            if "<" in body_text and ">" in body_text:
                import xml.etree.ElementTree as ET

                try:
                    root = ET.fromstring(body_text)
                    mark_tags = options is None or options.get("xml_tags", True)
                    mark_content = options is None or options.get("xml_content", True)

                    def _mark_xml(elem):
                        if mark_tags and "§" not in elem.tag:
                            elem.tag = f"§{elem.tag}§"
                        if mark_content and elem.text and elem.text.strip() and "§" not in elem.text:
                            elem.text = f"§{elem.text.strip()}§"
                        for child in elem:
                            _mark_xml(child)

                    _mark_xml(root)
                    marked_xml = ET.tostring(root, encoding="unicode", short_empty_elements=False)
                    try:
                        import xml.dom.minidom

                        marked_xml = xml.dom.minidom.parseString(marked_xml).toprettyxml(indent="  ")
                    except Exception as exc:
                        logger.debug("op: %s", exc)
                    new_lines = lines[:body_lines_start] + [ln for ln in marked_xml.split("\n") if ln.strip()]
                    lines = new_lines
                except Exception as exc:
                    # The XML body failed to parse or to serialise back — no
                    # positions are marked, so Intruder has nothing to inject.
                    logger.debug("payload markers: XML body not marked: %s", exc)
        new_text = "\n".join(lines)
        try:
            w.load_text(new_text)
            self._update_payload_select()
            n = new_text.count("§") // 2
            self.app.notify(f"Marked {n} parameter(s)", timeout=2)
            tab = self._active_tab
            if n > 1 and (tab is None or tab.attack_type == AttackType.SNIPER):
                if tab:
                    tab.attack_type = AttackType.BATTERING_RAM
                    self._sync_attack_type_ui(tab)
                self.app.notify(
                    f"Marked {n} positions — switched to Battering Ram "
                    "(Sniper only fills one position per request; change "
                    "back via the attack-type menu if you really want Sniper)",
                    severity="warning",
                    timeout=6,
                )
                self._auto_save_state()
            self._highlight_nth_marker(self._active_set_idx)
        except Exception as exc:
            logger.debug("op: %s", exc)

    # ── Payload list management ──────────────────────────────────────────

    def _update_payload_select(self, tab: _IntruderTabState | None = None) -> None:
        """Recompute the payload sets and the "Set N" label for a tab.

        An explicit ``tab`` covers the case when the action targets a non-active
        tab (a menu opened before switching). Without it the active one is used.
        """
        tab = tab if tab is not None else self._active_tab
        if tab is None:
            return
        if not self._tab_body_mounted(tab.tab_id):
            # The tab body is not assembled yet (tab created, pane not mounted).
            # This is call order, not a failure: nothing to count and nothing to
            # complain about — otherwise the log fills with a warning per tab.
            logger.debug("intruder: payload select skipped — tab %s not mounted yet", tab.tab_id)
            return
        try:
            editor = self._template_editor(tab)
            w = editor.content_widget
            template = w.text if isinstance(w, TextArea) else ""
        except NoMatches as exc:
            # The tab is mounted but the template panel is gone — a DOM/state
            # mismatch; count against an empty template, but leave a trace.
            logger.debug("intruder: template panel missing for %s: %s", tab.tab_id, exc)
            template = ""
        except Exception:
            logger.warning("intruder: template not read for payload select", exc_info=True)
            template = ""
        if tab.attack_type in (AttackType.SNIPER, AttackType.BATTERING_RAM):
            n = 1
        else:
            n = max(1, count_markers(template))
        while len(tab.payload_sources) < n:
            tab.payload_sources.append([])
        idx = min(tab.active_set_idx, n - 1)
        tab.active_set_idx = idx
        try:
            label = f"Set {idx + 1} ▼" if n <= 1 else f"Set {idx + 1}/{n} ▼"
            self.query_one(f"#{self._wid(tab.tab_id, _TabId.BTN_PAYLOAD_SET)}", ToolbarButton).label = label
        except NoMatches as exc:
            logger.debug("intruder: payload set button missing for %s: %s", tab.tab_id, exc)
        except Exception:
            logger.warning("intruder: payload set label not updated", exc_info=True)
        self._refresh_payload_list(tab)

    def _tab_body_mounted(self, tab_id: str) -> bool:
        """Whether the tab body is assembled (its toolbar and template panel in the DOM).

        Needed to tell "not mounted yet" (the normal order when a tab is
        created) from "mounted, but the widget is missing" (a real mismatch).
        Without that distinction any call before assembly logged a warning.
        """
        marker = self._wid(tab_id, _TabId.PAYLOAD_BUTTONS_TOOLBAR)
        return bool(self.query(f"#{marker}"))

    def _tab_id_for_widget(self) -> str | None:
        t = self._active_tab
        return t.tab_id if t else None

    def _refresh_payload_list(self, tab: _IntruderTabState | None = None) -> None:
        tab = tab if tab is not None else self._active_tab
        if tab is None:
            return
        tab_id = tab.tab_id
        try:
            lv = self.query_one(f"#{self._wid(tab_id, _TabId.PAYLOAD_LIST)}", ListView)
            lv.clear()
            active = tab.payload_sources[tab.active_set_idx] if tab.active_set_idx < len(tab.payload_sources) else []
            if isinstance(active, FilePayloadSource):
                preview = active.head(_PAYLOAD_LIST_PREVIEW_LIMIT)
                for p in preview:
                    lv.append(ListItem(Label(p)))
                if active.is_count_known and active.cached_count > len(preview):
                    lv.append(
                        ListItem(
                            Label(
                                f"… {active.cached_count - len(preview)} more line(s) "
                                f"not shown (file: {Path(active.path).name})"
                            )
                        )
                    )
                elif not active.is_count_known:
                    lv.append(ListItem(Label("(counting lines…)")))
            elif isinstance(active, (NumericPayloadSource, CharPayloadSource, ChainedPayloadSource)):
                total = len(active)
                preview = active.head(_PAYLOAD_LIST_PREVIEW_LIMIT)
                for p in preview:
                    lv.append(ListItem(Label(p)))
                if total > len(preview):
                    lv.append(ListItem(Label(f"… {total - len(preview):,} more value(s) not shown")))
            else:
                for p in active:
                    lv.append(ListItem(Label(p)))
            self._update_payload_count_label()
        except Exception as exc:
            logger.debug("op: %s", exc)

    def _update_payload_count_label(self) -> None:
        tab = self._active_tab
        if tab is None:
            return
        tab_id = tab.tab_id
        try:
            label = self.query_one(f"#{self._wid(tab_id, _TabId.PAYLOAD_COUNT_LABEL)}", Static)
        except NoMatches as exc:
            # The "N line(s)" label was not updated — when a file loads it keeps
            # the previous set's value, and the payload size is a lie.
            logger.debug("intruder: payload count label not found: %s", exc)
            return
        active = tab.payload_sources[tab.active_set_idx] if tab.active_set_idx < len(tab.payload_sources) else []
        if isinstance(active, FilePayloadSource):
            if active.is_count_known:
                label.update(f"[dim]{active.cached_count:,} line(s) — {esc(Path(active.path).name)}[/dim]")
            else:
                label.update(f"[dim]counting… — {esc(Path(active.path).name)}[/dim]")
        elif isinstance(active, (NumericPayloadSource, CharPayloadSource, ChainedPayloadSource)):
            n = len(active)
            label.update(f"[dim]{n:,} value(s)[/dim]" if n else "")
        else:
            n = len(active)
            label.update(f"[dim]{n:,} line(s)[/dim]" if n else "")

    def _highlight_nth_marker(self, n: int, tab: _IntruderTabState | None = None) -> None:
        try:
            from textual.widgets.text_area import Selection

            editor = self._template_editor(tab)
            w = editor.content_widget
            if not isinstance(w, TextArea):
                return
            text = w.text
            lines = text.split("\n")

            def to_rowcol(offset: int):
                row = 0
                for line in lines:
                    line_len = len(line) + 1
                    if offset < line_len:
                        return (row, offset)
                    offset -= line_len
                    row += 1
                return (row, 0)

            pairs = []
            i = 0
            while i < len(text):
                s = text.find("§", i)
                if s == -1:
                    break
                e = text.find("§", s + 1)
                if e == -1:
                    break
                pairs.append((s, e + 1))
                i = e + 1

            if n < len(pairs):
                s_off, e_off = pairs[n]
                start_rc = to_rowcol(s_off)
                end_rc = to_rowcol(e_off)
                w.selection = Selection(start_rc, end_rc)
        except Exception as exc:
            logger.debug("op: %s", exc)

    def _add_payload_manual(self) -> None:
        tab = self._active_tab
        if tab is None:
            return
        if tab.active_set_idx < len(tab.payload_sources) and isinstance(
            tab.payload_sources[tab.active_set_idx], _LAZY_SOURCE_TYPES
        ):
            self.app.notify(
                "This set is generated/loaded from a file — click Clear first to switch it to a manually-edited list.",
                severity="warning",
                timeout=4,
            )
            return

        def _on_add(value: str) -> None:
            tab = self._active_tab
            if tab is None:
                return
            while tab.active_set_idx >= len(tab.payload_sources):
                tab.payload_sources.append([])
            tab.payload_sources[tab.active_set_idx].append(value)
            self._refresh_payload_list()
            self._auto_save_state()

        self.app.push_screen(InputDialog("Add payload", "Enter payload value:", on_add=_on_add))

    def _remove_selected_payload(self) -> None:
        tab = self._active_tab
        if tab is None:
            return
        if tab.active_set_idx < len(tab.payload_sources) and isinstance(
            tab.payload_sources[tab.active_set_idx], _LAZY_SOURCE_TYPES
        ):
            self.app.notify(
                "This set is generated/loaded from a file — individual lines "
                "can't be removed. Click Clear to remove the whole set.",
                severity="warning",
                timeout=4,
            )
            return
        try:
            lv = self.query_one(f"#{self._wid(tab.tab_id, _TabId.PAYLOAD_LIST)}", ListView)
            idx = lv.index
            if idx is not None and tab.active_set_idx < len(tab.payload_sources):
                payloads = tab.payload_sources[tab.active_set_idx]
                if 0 <= idx < len(payloads):
                    payloads.pop(idx)
                    self._refresh_payload_list()
                    self._auto_save_state()
        except Exception:
            logger.error("intruder: selected payloads not refreshed/saved", exc_info=True)

    def _clear_payloads(self) -> None:
        tab = self._active_tab
        if tab is None:
            return
        if tab.active_set_idx < len(tab.payload_sources):
            tab.payload_sources[tab.active_set_idx] = []
            self._refresh_payload_list()
            self._auto_save_state()

    _EAGER_LOAD_MAX_BYTES = 20 * 1024 * 1024

    def _load_payloads_from_file(self) -> None:
        tab = self._active_tab
        if tab is None:
            return
        if tab.payload_load_in_progress:
            self.app.notify("A payload file is already loading — please wait", severity="warning", timeout=3)
            return
        from pentool.tui.dialogs.file_selector import FileSelectorDialog, FileSelectorMode

        captured_idx = tab.active_set_idx

        def _on_file(path: str | None) -> None:
            if path:
                self.run_worker(
                    self._load_file_async(path, captured_idx),
                    exclusive=False,
                    name="payload-load",
                    exit_on_error=False,
                )

        self.app.push_screen(
            FileSelectorDialog(
                mode=FileSelectorMode.OPEN,
                filter_ext=["*.txt", "*.yaml", "*.yml"],
                title="Select payload file",
            ),
            _on_file,
        )

    async def _load_file_async(self, path: str, target_idx: int) -> None:
        tab = self._active_tab
        try:
            size = await asyncio.get_running_loop().run_in_executor(None, lambda: Path(path).stat().st_size)
        except Exception as exc:
            from pentool.core.error_guard import err

            err(exc, "Failed to load payload file", self, severity="error")
            return
        if tab:
            while target_idx >= len(tab.payload_sources):
                tab.payload_sources.append([])
            if size <= self._EAGER_LOAD_MAX_BYTES:
                await self._load_file_eager(path, target_idx)
            else:
                await self._load_file_streamed(path, target_idx, size)

    async def _load_file_eager(self, path: str, target_idx: int) -> None:
        tab = self._active_tab
        if tab is None:
            return
        try:
            loop = asyncio.get_running_loop()
            content = await loop.run_in_executor(None, self._read_file_sync, path)
            payloads: list[str] = []
            for line in content.splitlines():
                line = line.strip()
                if line and not line.startswith("#"):
                    payloads.append(line)
        except Exception as exc:
            from pentool.core.error_guard import err

            err(exc, "Failed to load payload (eager)", self, severity="error")
            return
        existing = tab.payload_sources[target_idx]
        if isinstance(existing, _LAZY_SOURCE_TYPES):
            tab.payload_sources[target_idx] = payloads
        else:
            existing.extend(payloads)
        if target_idx == tab.active_set_idx:
            self._refresh_payload_list()
        name = Path(path).name
        self.app.notify(f"Loaded {len(payloads)} payloads from {name}", timeout=3)
        self._auto_save_state()

    async def _load_file_streamed(self, path: str, target_idx: int, size_bytes: int) -> None:
        tab = self._active_tab
        if tab is None:
            return
        tab.payload_load_in_progress = True
        source = FilePayloadSource(path)
        tab.payload_sources[target_idx] = source
        if target_idx == tab.active_set_idx:
            self._refresh_payload_list()
        size_mb = size_bytes / (1024 * 1024)
        name = Path(path).name
        self.app.notify(
            f"Loading {name} ({size_mb:.0f} MB) — streaming, counting lines in background…",
            timeout=4,
        )

        def _on_progress(count: int, bytes_read: int, total_bytes: int) -> None:
            self.app.call_from_thread(self._on_payload_count_progress, target_idx, count, bytes_read, total_bytes)

        try:
            loop = asyncio.get_running_loop()
            final_count = await loop.run_in_executor(None, count_lines_with_progress, path, "utf-8", _on_progress)
            source.set_count(final_count)
        except Exception as exc:
            from pentool.core.error_guard import err

            err(exc, "Payload line count failed (still usable)", self, severity="warning")
        finally:
            tab.payload_load_in_progress = False
            if target_idx == tab.active_set_idx:
                self._update_payload_count_label()
            self._auto_save_state()

    def _on_payload_count_progress(self, target_idx: int, count: int, bytes_read: int, total_bytes: int) -> None:
        tab = self._active_tab
        if tab is None:
            return
        active = tab.payload_sources[target_idx] if target_idx < len(tab.payload_sources) else None
        if not isinstance(active, FilePayloadSource):
            return
        tab_id = tab.tab_id
        try:
            label = self.query_one(f"#{self._wid(tab_id, _TabId.PAYLOAD_COUNT_LABEL)}", Static)
            pct = f" ({bytes_read / total_bytes * 100:.0f}%)" if total_bytes else ""
            if target_idx == tab.active_set_idx:
                label.update(f"[dim]{count:,} line(s) counted so far{pct}…[/dim]")
        except Exception:
            logger.warning("intruder: payload count progress not shown", exc_info=True)

    @staticmethod
    def _read_file_sync(path: str) -> str:
        return Path(path).read_text(encoding="utf-8", errors="replace")

    def _append_to_active_set(self, new_source) -> int:
        tab = self._active_tab
        if tab is None:
            return 0
        while tab.active_set_idx >= len(tab.payload_sources):
            tab.payload_sources.append([])
        existing = tab.payload_sources[tab.active_set_idx]
        added = len(new_source) if hasattr(new_source, "__len__") else 1
        if isinstance(existing, list) and isinstance(new_source, list):
            existing.extend(new_source)
        elif isinstance(existing, list) and not existing:
            tab.payload_sources[tab.active_set_idx] = new_source
        else:
            tab.payload_sources[tab.active_set_idx] = ChainedPayloadSource(existing, new_source)
        return added

    def _open_generate_dialog(self) -> None:
        self.app.push_screen(GenerateDialog(), self._on_payloads_generated)

    def _on_payloads_generated(self, source) -> None:
        if source:
            added = self._append_to_active_set(source)
            self._refresh_payload_list()
            self.app.notify(f"Generated {added:,} payload(s)", timeout=2)

    def _open_smart_payloads_dialog(self) -> None:
        from pentool.core.license import get_session_license

        info = get_session_license()
        if not info.has_feature("payloads_pro"):
            self.app.notify(
                "🔒 Smart Payloads requires PRO license — go to Settings → License",
                severity="warning",
                timeout=4,
            )
            return
        self.app.push_screen(SmartPayloadsDialog(), self._on_smart_payloads_generated)

    def _on_smart_payloads_generated(self, payloads: list[str] | None) -> None:
        if payloads:
            added = self._append_to_active_set(payloads)
            self._refresh_payload_list()
            self.app.notify(f"🧠 Smart: added {added:,} payloads", timeout=3)

    # ── Attack start/stop/pause/resume ────────────────────────────────────

    def action_start_attack(self) -> None:
        tab = self._active_tab
        if tab is None:
            return
        running_tab = self._active_tab
        running = bool(running_tab and running_tab.running)
        logger.info("INTRUDER: action_start_attack called, running=%s", running)
        if running:
            return
        if tab.payload_load_in_progress:
            self.app.notify(
                "A payload file is still being counted — wait for it to finish before starting",
                severity="warning",
                timeout=4,
            )
            return
        try:
            editor = self._template_editor()
            w = editor.content_widget
            template = w.text if isinstance(w, TextArea) else ""
            logger.info("INTRUDER: template len=%d", len(template))
        except (LookupError, NoMatches) as e:
            # No tab, or its body is not mounted. This used to be a bare
            # `except Exception`; it caught both this pair and a typo in a field
            # name — but a typo would have produced "cannot get template"
            # instead of the real cause, so the pair is named explicitly.
            logger.error("INTRUDER: cannot get template: %s", e)
            return
        if not template.strip():
            self.app.notify("Template is empty", severity="warning", timeout=3)
            return
        if count_markers(template) == 0:
            self.app.notify(
                "No §§ markers in template — use Auto §§ or Add §§ to mark positions first",
                severity="warning",
                timeout=5,
            )
            return
        logger.info("INTRUDER: action_start: attack_type=%s", tab.attack_type)

        processing_ops = self._get_processing_ops()
        payload_sets = []
        for ps in tab.payload_sources:
            if len(ps) == 0:
                processed = [""]
            else:
                processed = ProcessedPayloads(ps, processing_ops, self._apply_processing)
            payload_sets.append(processed)

        logger.info("INTRUDER: payload_sets sizes=%s", [len(ps) for ps in payload_sets])
        if not any(p.strip() for ps in payload_sets for p in ps):
            self.app.notify("No payloads configured", severity="warning", timeout=3)
            return

        from pentool.core.license import get_session_license

        license_info = get_session_license()
        is_pro = license_info.is_pro() if license_info else False

        try:
            threads = int(self.query_one("#intruder-threads", Input).value or "10")
            if not is_pro:
                threads = max(1, min(threads, 5))
            else:
                threads = max(1, min(threads, 200))
        except (NoMatches, ValueError) as exc:
            # The field is missing or not a number — the attack runs on 5/10
            # threads while the screen keeps showing what was typed.
            logger.debug("intruder: thread count not usable, falling back: %s", exc)
            threads = 5 if not is_pro else 10

        try:
            delay_ms = int(self.query_one("#intruder-delay", Input).value or "0")
            if not is_pro:
                delay_ms = max(100, delay_ms)
            else:
                delay_ms = max(0, delay_ms)
        except (NoMatches, ValueError) as exc:
            # Same for the delay: the attack will use a different pace than the
            # delay field shows, and the screen gives no hint of that.
            logger.debug("intruder: delay not usable, falling back: %s", exc)
            delay_ms = 100 if not is_pro else 0

        turb_cb = self.query_one("#intruder-turbo", Checkbox)
        turbo_mode = bool(turb_cb.value) if is_pro else False
        if not is_pro:
            turb_cb.value = False
        tab.turbo_mode = turbo_mode

        # Store the active tab's parameters in its state
        tab.thread_count = threads
        tab.delay_ms = delay_ms

        config = IntruderConfig(
            template=template,
            attack_type=tab.attack_type,
            payload_sets=payload_sets,
            threads=threads,
            delay_ms=delay_ms,
            follow_redirects=False,
            timeout=30,
        )

        api = self._get_api()
        if api is None:
            self.app.notify("No project open", severity="warning", timeout=3)
            return

        # Create an isolated attack for THIS tab (parallel to the others)
        attack = api.make_attack(config, turbo_mode=turbo_mode)
        tab.attack = attack

        # Capture the tab: results are written into it, not into the active one
        self.refresh_header()
        tab.running = True
        tab.paused = False
        tab.all_results = []
        self._clear_results()

        total_payloads = sum(len(ps) for ps in payload_sets)
        mode_label = " [⚡ Turbo]" if turbo_mode else ""
        limit_label = "" if is_pro else " [FREE: limited]"
        self.app.notify(
            f"Attack started: {total_payloads} payload(s){mode_label}{limit_label}",
            severity="success",
            title="Intruder",
        )
        group = self._attack_group(tab.tab_id)
        self._live_attacks[tab.tab_id] = attack
        self.run_worker(self._run_attack(tab, attack), exclusive=False, name=group, group=group)

    @staticmethod
    def _attack_group(tab_id: str) -> str:
        """Worker group of a tab's attack — tab close cancels the attack by it.

        Name and group intentionally match: ``on_worker_state_changed`` parses
        the name, ``cancel_group`` looks up the group, and a second string with
        the same letters would drift apart on the first rename.
        """
        return f"intruder-attack-{tab_id}"

    def _stop_tab_attack(self, tab: _IntruderTabState) -> None:
        """Stop a tab's attack: cancel the worker and ask the attack to stop.

        The worker is cancelled first: ``attack.stop()`` does not return at once
        on a long network loop, and a closed tab must not wait for it.
        """
        try:
            self.workers.cancel_group(self, self._attack_group(tab.tab_id))
        except Exception:
            # The attack worker survived: the closed tab will keep sending requests.
            logger.exception("_stop_tab_attack: cancel_group failed for %s", tab.tab_id)
        attack = getattr(tab, "attack", None)
        self._live_attacks.pop(tab.tab_id, None)
        tab.running = False
        tab.paused = False
        if attack is not None:
            # On the App, not the screen: the screen may be leaving (on_unmount),
            # and then its own cancel_node would kill the stop worker before it
            # had a chance to run — the attack would stay alive.
            try:
                self.app.run_worker(attack.stop(), exit_on_error=False)  # type: ignore[attr-defined]
            except Exception:
                # `tab.running` is already False yet the attack keeps running:
                # the screen considers it closed and Stop is no longer available.
                logger.exception("_stop_tab_attack: attack.stop failed for %s", tab.tab_id)

    async def _run_attack(self, tab: _IntruderTabState, attack: "IntruderAttack") -> None:
        """Run the tab's isolated attack.

        ``tab`` is captured at start — results go into it, not into _active_tab,
        so that with parallel attacks switching tabs does not scramble the data.
        """
        logger.info("INTRUDER: _run_attack started tab=%s type=%s", tab.tab_id, tab.attack_type)
        set_activity("intruder", True)

        # Keep a reference to the working tab
        _tab = tab

        def on_result(result: IntruderResult) -> None:
            self.call_after_refresh(self._on_result, result, _tab)

        def on_progress(done: int, total: int) -> None:
            self.call_after_refresh(self._on_progress, done, total, _tab)

        try:
            tab.running = True
            await attack.run(on_result, on_progress)
        except Exception as exc:
            from pentool.core.error_guard import err

            err(exc, "Intruder attack error", self, severity="error")
        finally:
            _tab.running = False
            self._live_attacks.pop(_tab.tab_id, None)
            set_activity("intruder", bool(self._live_attacks))
            _tab.paused = False
            _tab.attack = None
            logger.info(
                "INTRUDER: _run_attack tab=%s finished, results=%d",
                _tab.tab_id,
                len(_tab.all_results),
            )
            # The toolbar status is updated only if this is the active tab.
            # Background tabs get their status pulled on switch (_sync_toolbar).
            if _tab is self._active_tab:
                self.refresh_header()
                self.app.notify(
                    f"Attack finished: {len(_tab.all_results)} requests",
                    severity="information",
                    timeout=4,
                )

    def _on_result(self, result: IntruderResult, tab: _IntruderTabState | None = None) -> None:
        """A result from a tab's attack — written into that tab (not _active_tab).

        With parallel attacks the tab is captured at start and passed in here,
        otherwise the result would land in whatever tab is active at the moment.
        """
        if tab is None:
            tab = self._active_tab
        if tab is None:
            return
        tab.all_results.append(result)
        row_dict = {
            "status": str(result.response_status),
            "length": result.response_length or 0,
            "payload": " ".join(result.payload_values),
        }
        passes = True
        if tab.filter_spec and not tab.filter_spec.is_empty:
            passes = tab.filter_spec.apply([row_dict]) == [row_dict]
        if passes and tab.grep_only_match and tab.grep_match_patterns:
            text = f"{result.response_status} {result.response_length} {' '.join(result.payload_values)}"
            import re

            passes = any(re.search(pat, text, re.IGNORECASE) for pat in tab.grep_match_patterns)
        if passes:
            tab.filtered_results.append(result)
            self._add_result_row(result, tab)
        self._auto_save_result(result, tab)

    def _on_progress(self, done: int, total: int, tab: _IntruderTabState | None = None) -> None:
        if tab is None:
            tab = self._active_tab
        if tab is None:
            return
        try:
            pb = self.query_one(f"#{self._wid(tab.tab_id, _TabId.ATTACK_PROGRESS)}", ProgressBar)
            if done == 0:
                pb.update(total=max(1, total), progress=0)
            else:
                pb.advance(done - pb.progress)
        except Exception as exc:
            logger.debug("op: %s", exc)
        try:
            pct = f"{done / total * 100:.1f}%" if total > 0 else "0%"
            self.query_one(f"#{self._wid(tab.tab_id, _TabId.PROGRESS_LABEL)}", Static).update(f"{done}/{total} ({pct})")
        except Exception as exc:
            logger.debug("op: %s", exc)

    def action_toggle_pause(self) -> None:
        tab = self._active_tab
        if tab is None or not tab.running or tab.attack is None:
            return
        should_pause = not tab.paused
        if should_pause:
            self.run_worker(tab.attack.pause(), exit_on_error=False)
        else:
            self.run_worker(tab.attack.resume(), exit_on_error=False)
        tab.paused = should_pause
        self.refresh_header()
        self.app.notify("Paused" if should_pause else "Resumed", timeout=2)

    def action_resume(self) -> None:
        logger.info("INTRUDER: action_resume tab=%s", self._active_tab.tab_id if self._active_tab else None)
        self.refresh_header()
        self.action_start_attack()

    def action_stop(self) -> None:
        tab = self._active_tab
        if tab is not None:
            self._stop_tab_attack(tab)
        self.refresh_header()
        self.app.notify("Attack stopped", severity="warning")

    def on_worker_state_changed(self, event) -> None:
        from textual.worker import WorkerState

        name = getattr(event.worker, "name", "") or ""
        if not name.startswith("intruder-attack-"):
            return
        # Derive the tab from the worker name: intruder-attack-<tab_id>
        tid = name[len("intruder-attack-") :]
        tab = self._tc_panel.get_state(tid)
        if event.state in (WorkerState.SUCCESS, WorkerState.CANCELLED, WorkerState.ERROR):
            if tab is not None and tab.running:
                tab.paused = False
                # If this is the active tab — sync the toolbar
                if tab is self._active_tab:
                    self.refresh_header()
                    self.refresh_header()

    @staticmethod
    def _row_from_result(result: IntruderResult) -> list[str]:
        payloads_str = " | ".join(result.payload_values)
        if len(payloads_str) > 40:
            payloads_str = payloads_str[:37] + "…"
        return [
            str(result.request_number),
            payloads_str,
            str(result.response_status or "-"),
            str(result.response_length or "-"),
            str(result.response_time_ms or "-"),
            result.error or "",
        ]

    def _add_result_row(self, result: IntruderResult, tab: _IntruderTabState | None = None) -> None:
        if tab is None:
            tab = self._active_tab
        if tab is None:
            return
        try:
            row = self._row_from_result(result)
            if tab.grep_extract_patterns:
                extract_val = ""
                resp_body = getattr(result, "request_raw", "") or ""
                for pat in tab.grep_extract_patterns:
                    try:
                        m = re.search(pat, resp_body)
                        if m:
                            extract_val = m.group(1) if m.lastindex else m.group(0)
                            extract_val = extract_val[:30]
                            break
                    except re.error as exc:
                        logger.debug("extract val: %s", exc)
                row.append(extract_val)
            table = self._results_table()
            if table is None:
                return
            table.add_rows([tuple(row)])
        except Exception as exc:
            logger.debug("_add_result_row: %s", exc)

    def _clear_results(self) -> None:
        tab = self._active_tab
        if tab is None:
            return
        try:
            table = self._results_table()
            if table is None:
                return
            table.clear_data()
        except Exception as exc:
            logger.debug("_clear_results: %s", exc)
        tab.all_results = []
        tab.filtered_results = []
        try:
            self.query_one(f"#{self._wid(tab.tab_id, _TabId.PROGRESS_LABEL)}", Static).update("0/0 (0%)")
            self.query_one(f"#{self._wid(tab.tab_id, _TabId.ATTACK_PROGRESS)}", ProgressBar).update(total=100)
        except NoMatches as exc:
            # The results are cleared but the progress and the "N/M" counter
            # still show the previous attack — the screen claims data it lacks.
            logger.debug("intruder: progress not reset with results: %s", exc)

    def _results_table(self) -> DataTable | None:
        tab = self._active_tab
        if tab is None:
            return None
        try:
            return self.query_one(f"#{self._wid(tab.tab_id, _TabId.RESULTS_TABLE)}", DataTable)
        except Exception:
            return None

    def _rebuild_table_data(self) -> None:
        tab = self._active_tab
        if tab is None:
            return
        table = self._results_table()
        if table is None:
            return
        try:
            if not tab.filtered_results:
                if tab.all_results:
                    self._apply_and_display(tab.all_results, table)
                else:
                    table.clear_data()
                return
            display_rows = []
            for r in tab.filtered_results:
                row = self._row_from_result(r)
                if tab.grep_extract_patterns:
                    extract_val = self._extract_grep_value(r, tab.grep_extract_patterns)
                    row.append(extract_val)
                display_rows.append(row)
            import pyarrow as pa

            cols = _RESULTS_COL_NAMES
            if tab.grep_extract_patterns:
                cols = cols + ["Extract"]
            data = {c: pa.array([row[i] for row in display_rows], type=pa.string()) for i, c in enumerate(cols)}
            arrow = pa.table(data)
            table.set_data(arrow)
        except Exception as exc:
            logger.error("_rebuild_table_data failed: %s", exc)

    def _apply_and_display(self, results: list[IntruderResult], table: DataTable) -> None:
        tab = self._active_tab
        if tab is None:
            return
        filtered = []
        for r in results:
            row_dict = {
                "status": str(r.response_status),
                "length": r.response_length or 0,
                "payload": " ".join(r.payload_values),
            }
            passes = True
            if tab.filter_spec and not tab.filter_spec.is_empty:
                passes = tab.filter_spec.apply([row_dict]) == [row_dict]
            if passes and tab.grep_only_match and tab.grep_match_patterns:
                text = f"{r.response_status} {r.response_length} {' '.join(r.payload_values)}"
                import re

                passes = any(re.search(pat, text, re.IGNORECASE) for pat in tab.grep_match_patterns)
            if passes:
                filtered.append(r)
        tab.filtered_results = filtered
        if not filtered:
            table.clear_data()
            return
        display_rows = []
        for r in filtered:
            row = self._row_from_result(r)
            if tab.grep_extract_patterns:
                extract_val = self._extract_grep_value(r, tab.grep_extract_patterns)
                row.append(extract_val)
            display_rows.append(row)
        import pyarrow as pa

        cols = _RESULTS_COL_NAMES
        if tab.grep_extract_patterns:
            cols = cols + ["Extract"]
        data = {c: pa.array([row[i] for row in display_rows], type=pa.string()) for i, c in enumerate(cols)}
        arrow = pa.table(data)
        table.set_data(arrow)

    @staticmethod
    def _extract_grep_value(result: IntruderResult, patterns: list[str] | None = None) -> str:
        import re

        for pat in patterns or []:
            try:
                m = re.search(pat, result.request_raw or "")
                if m:
                    return (m.group(1) if m.lastindex else m.group(0))[:30]
            except re.error as exc:
                logger.debug("extract grep: %s", exc)
        return ""

    def _redraw_results(self) -> None:
        self._rebuild_table_data()

    def _result_at_row(self, table: DataTable, row_index: int) -> IntruderResult | None:
        tab = self._active_tab
        if tab is None:
            return None
        try:
            from textual.coordinate import Coordinate

            coord = Coordinate(row_index, 0)
            cell = table.get_cell_at(coord)
            row_number = int(str(cell))
        except (ValueError, TypeError, IndexError):
            row_number = -1
        if row_number >= 0:
            for r in tab.filtered_results:
                if r.request_number == row_number:
                    return r
        if 0 <= row_index < len(tab.filtered_results):
            return tab.filtered_results[row_index]
        return None

    def on_data_table_header_selected(self, event: DataTable.HeaderSelected) -> None:
        tab = self._active_tab
        if tab is None:
            return
        table_id = self._wid(tab.tab_id, _TabId.RESULTS_TABLE)
        if event.data_table.id != table_id:
            return
        self._sort_table_sql(
            event,
            _RESULTS_COL_NAMES,
            order_by_map={
                "#": "request_number",
                "Payload(s)": "payload_values",
                "Status": "response_status",
                "Length": "response_length",
                "Time(ms)": "response_time_ms",
                "Error": "error",
            },
            reload_cb=lambda order_by, order_dir: (
                self._do_load_results(self._get_api(), order_by=order_by, order_dir=order_dir)
                if self._get_api()
                else None
            ),
        )

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        tab = self._active_tab
        if tab is None:
            return
        table_id = self._wid(tab.tab_id, _TabId.RESULTS_TABLE)
        if event.data_table.id != table_id:
            return
        result = self._result_at_row(event.data_table, event.cursor_row)
        if result is None:
            return
        self._show_detail(result)

    def on_data_table_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        if not event.data_table.id:
            return
        # Check whether this belongs to our results-table (per-tab)
        tab = self._active_tab
        if tab is None:
            return
        table_id = self._wid(tab.tab_id, _TabId.RESULTS_TABLE)
        if event.data_table.id != table_id:
            return
        result = self._result_at_row(event.data_table, event.cursor_row)
        if result is None:
            return
        self._show_detail(result)

    def _show_detail(self, result: IntruderResult) -> None:
        tab = self._active_tab
        if tab is None:
            return
        tab.current_result = result
        req_raw = result.request_raw or ""
        resp_raw = result.response_raw or ""
        try:
            panel = self.query_one(f"#{self._wid(tab.tab_id, _TabId.INTRUDER_DETAIL_PANEL)}")
            panel.display = True
        except Exception as exc:
            logger.warning("INTRUDER: _show_detail panel query failed: %s", exc)
        self.call_after_refresh(self._load_detail_content, req_raw, resp_raw)

    def _load_detail_content(self, req_raw: str, resp_raw: str) -> None:
        tab = self._active_tab
        if tab is None:
            return
        try:
            req_view = self.query_one(f"#{self._wid(tab.tab_id, _TabId.DETAIL_REQUEST)}", HttpView)
            req_view.load_raw_http(req_raw)
        except Exception:
            logger.warning("intruder: detail request view not filled", exc_info=True)
        try:
            resp_view = self.query_one(f"#{self._wid(tab.tab_id, _TabId.DETAIL_RESPONSE)}", HttpView)
            if resp_raw:
                resp_view.load_raw_http(resp_raw)
            else:
                resp_view.clear()
        except Exception:
            logger.warning("intruder: detail response view not filled", exc_info=True)

    def action_hide_detail(self) -> None:
        tab = self._active_tab
        if tab is None:
            return
        try:
            panel = self.query_one(f"#{self._wid(tab.tab_id, _TabId.INTRUDER_DETAIL_PANEL)}")
            panel.display = False
            tab.current_result = None
        except NoMatches as exc:
            # The detail panel is not in the tree (the tab is not mounted).
            # `current_result` is reset in the same `try`, so the selected result
            # stays alongside the panel — hence a log line, not silence.
            logger.debug("intruder: detail panel not hidden: %s", exc)

    # ── Context menu ───────────────────────────────────────────────────

    def on__base_http_widget_context_menu_request(self, event) -> None:
        self.cm_open_text_menu(event.screen_x, event.screen_y)

    def _cm_get_raw_request(self) -> str:
        if self._current_result:
            return self._current_result.request_raw
        return ""

    def on_mouse_down(self, event) -> None:
        if not (event.button == 1 and event.ctrl):
            return
        self._open_context_menu(event.screen_x, event.screen_y)

    def _open_context_menu(self, x: int, y: int) -> None:
        items = [
            ("send_repeater", "Send to Repeater"),
            ("send_scanner", "Send to Scanner"),
            ("copy_payload", "Copy Payload"),
        ]
        self.app.show_context_menu(items, x, y, callback=self._on_ctx_action)

    def _on_ctx_action(self, action: str) -> None:
        if action == "send_repeater":
            self._send_selected_to_repeater()
        elif action == "send_scanner":
            self._send_selected_to_scanner()
        elif action == "copy_payload":
            self._copy_selected_payload()

    def on_context_menu_item_selected(self, event) -> None:
        self._on_ctx_action(event.action)

    def _send_selected_to_repeater(self) -> None:
        try:
            table = self._results_table()
            result = self._result_at_row(table, table.cursor_row)
            if result is not None:
                self.app.post_message(SendToRepeater(result.request_raw))
        except Exception as exc:
            logger.debug("op: %s", exc)

    def _send_selected_to_scanner(self) -> None:
        try:
            from pentool.tui.messages import SendHostToScanner

            table = self._results_table()
            result = self._result_at_row(table, table.cursor_row)
            if result is not None:
                raw = result.request_raw or ""
                host = ""
                for line in raw.splitlines():
                    if line.lower().startswith("host:"):
                        host = line.split(":", 1)[1].strip()
                        break
                if host:
                    self.app.post_message(SendHostToScanner(host))
                    self.app.notify(f"Sent {host} to Scanner", timeout=2)
                else:
                    self.app.notify("Could not extract host from request", severity="warning")
        except Exception as exc:
            logger.debug("_send_selected_to_scanner: %s", exc)

    def action_open_in_browser(self) -> None:
        try:
            table = self._results_table()
            result = self._result_at_row(table, table.cursor_row)
            if result is not None and result.url:
                import webbrowser

                webbrowser.open(result.url)
        except NoMatches as exc:
            # There is no results table in the tree — nothing to open. The hotkey
            # will stay silent, but this is "screen not assembled", not a break.
            logger.debug("intruder: open in browser — no results table: %s", exc)
        except Exception:
            # The browser did not open: from the outside it looks like "the key
            # does not work", and the user can retry it endlessly.
            logger.exception("intruder: open in browser failed")

    def _copy_selected_payload(self) -> None:
        try:
            table = self._results_table()
            result = self._result_at_row(table, table.cursor_row)
            if result is not None:
                payload_str = " | ".join(result.payload_values)
                from pentool.utils.copy_as import copy_to_clipboard

                copy_to_clipboard(payload_str)
                self.app.notify("Payload copied", timeout=2)
        except Exception:
            logger.warning("intruder: payload not copied to clipboard", exc_info=True)

    def _export_csv(self) -> None:
        tab = self._active_tab
        if not tab or not tab.all_results:
            self.app.notify("No results to export", severity="warning", timeout=3)
            return
        from pentool.tui.dialogs.file_selector import FileSelectorDialog, FileSelectorMode

        def _on_path(path: str | None) -> None:
            if not path:
                return
            if not path.endswith(".csv"):
                path += ".csv"
            try:
                import csv

                with open(path, "w", newline="", encoding="utf-8") as f:
                    writer = csv.writer(f)
                    writer.writerow(["#", "Payloads", "Status", "Length", "Time(ms)", "Error", "Timestamp"])
                    tab = self._active_tab
                    if tab:
                        for r in tab.all_results:
                            writer.writerow(
                                [
                                    r.request_number,
                                    " | ".join(r.payload_values),
                                    r.response_status or "",
                                    r.response_length or "",
                                    r.response_time_ms or "",
                                    r.error or "",
                                    r.timestamp.isoformat(),
                                ]
                            )
                self.app.notify(f"Exported to {path}", timeout=4)
            except Exception as exc:
                from pentool.core.error_guard import err

                err(exc, "Intruder export failed", self, severity="error")

        self.app.push_screen(
            FileSelectorDialog(mode=FileSelectorMode.SAVE, title="Save CSV"),
            _on_path,
        )

    def _get_processing_ops(self) -> list[str]:
        tab = self._active_tab
        if tab is None:
            return []
        ops = []
        try:
            if self.query_one(f"#{self._wid(tab.tab_id, _TabId.PROC_URL_ENCODE)}", Checkbox).value:
                ops.append("url_encode")
            if self.query_one(f"#{self._wid(tab.tab_id, _TabId.PROC_BASE64)}", Checkbox).value:
                ops.append("base64_encode")
            if self.query_one(f"#{self._wid(tab.tab_id, _TabId.PROC_HTML_ENCODE)}", Checkbox).value:
                ops.append("html_encode")
            if self.query_one(f"#{self._wid(tab.tab_id, _TabId.PROC_MD5)}", Checkbox).value:
                ops.append("md5")
        except Exception as exc:
            logger.debug("op: %s", exc)
        return ops

    def _apply_processing(self, payload: str, ops: list[str]) -> str:
        return process_payload(payload, ops)

    def load_request(self, raw: str) -> None:
        tab = self._active_tab
        if tab is None:
            return
        try:
            self._clear_results()
        except Exception:
            logger.warning("intruder: old results not cleared on request load", exc_info=True)
        try:
            editor = self._template_editor()
            w = editor.content_widget
            if isinstance(w, TextArea):
                _load_into_textarea(w, raw, ["§"])
                self._update_payload_select()
                self._highlight_nth_marker(self._active_set_idx)
        except Exception:
            logger.error("intruder: template not loaded into tab", exc_info=True)

    def get_intruder_export(self) -> dict:
        api = getattr(self, "_api", None)
        if api is None:
            return {"results": []}
        try:
            return api.export_project_data()
        except Exception:
            logger.error("intruder: results not exported", exc_info=True)
            return {"results": []}

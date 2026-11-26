"""Repeater screen — manual HTTP request sender."""

from __future__ import annotations

import re
from pathlib import Path

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.css.query import NoMatches
from textual.widgets import Static, TabbedContent, TabPane, TextArea
from textual.widgets.text_area import Selection

from pentool.core.logging import get_logger
from pentool.services.repeater_service import RepeaterService
from pentool.tui.header import HeaderAction, HeaderSpec
from pentool.tui.hotkeys.defaults import REPEATER_BINDINGS
from pentool.tui.mixins.autosave import AutoSaveMixin
from pentool.tui.mixins.request_context_menu import RequestContextMenuMixin
from pentool.tui.screens.base import BaseModuleScreen
from pentool.tui.screens.module_screen import ModuleScreen
from pentool.tui.widgets.diff_panel import DiffPanel
from pentool.tui.widgets.request_editor import RequestEditor, ResponseViewer
from pentool.tui.widgets.resize_handle import ResizeHandle
from pentool.tui.widgets.search_bar import SearchBar
from pentool.tui.widgets.toolbar_button import ToolbarButton

_CSS = (Path(__file__).parent / "screen.tcss").read_text(encoding="utf-8")

logger = get_logger(__name__)

#: Frames to wait for a freshly mounted editor to compose its TextArea. Mount
#: is asynchronous and `call_after_refresh` runs once per frame, so a couple
#: of attempts is already generous; the cap exists so a genuinely broken
#: compose fails loudly instead of rescheduling forever.
_MOUNT_ATTEMPTS = 5


class _TabState:
    """State of a single Repeater tab."""

    def __init__(self, tab_id: str, name: str, tab_uid: str = "") -> None:
        self.tab_id = tab_id
        self.name = name
        import uuid as _uuid

        # Stable tab identity: survives a rename and a restart. For a restored
        # tab the uid comes from the DB instead of being generated anew — else
        # every reload would create new rows while the old ones stayed behind as
        # orphans.
        self.tab_uid: str = tab_uid or _uuid.uuid4().hex
        self.request_text: str = "GET / HTTP/1.1\r\nHost: example.com\r\n\r\n"
        self.response_text: str = ""
        self.sending: bool = False
        # Snapshot of request_text at the moment of the last successful
        # Send. None means "never sent yet" — used both for the "*" dirty
        # marker on the tab label and for the Ctrl+D diff panel.
        self.last_sent_text: str | None = None
        self.is_dirty: bool = False
        # True only once the tab's editor has been created and filled from
        # `request_text`. Until then the editor is empty for a reason — it does
        # not exist yet — and reading it back would overwrite the default
        # request with "". `TabbedContent` announces a fresh tab twice, and the
        # second announcement lands before the editor is filled, so without
        # this flag every new tab opened empty.
        self.ui_ready: bool = False


class RepeaterScreen(AutoSaveMixin, BaseModuleScreen, RequestContextMenuMixin, ModuleScreen):
    """Repeater module screen."""

    DEFAULT_CSS = _CSS

    BINDINGS = REPEATER_BINDINGS

    _sort_col_idx: int | None = None
    _sort_reverse: bool = False
    _HIST_COL_LABELS = ["ID", "Method", "URL", "Status", "Length", "Time"]

    # TabRenameMixin config
    _rename_input_id: str = "rename-input"
    _rename_tab_prefix: str = "tab-"
    _rename_tabs_widget_id: str = "repeater-tabs"
    # The field is mounted on first use: this screen's tabs are a plain
    # TabbedContent, not a TabbedContentPanel that ships the input itself.
    _rename_input_host: str = "#tabs-area"

    # RequestContextMenuMixin config — Repeater: Send to Intruder + Scanner, no nmap
    _cm_show_nmap = False
    _cm_show_send_intruder = True
    _cm_show_send_scanner = True

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._tabs: list[_TabState] = []
        self._tab_counter: int = 0
        self._active_tab_id: str | None = None
        self._sending: bool = False
        self._follow_redirects: bool = True
        self._search_matches: list[int] = []
        self._search_current: int = 0
        self._search_query: str = ""
        self._search_regex: bool = False
        self._search_target: str = "request"  # "request" | "response" — syncs with the SearchBar
        self._tab_click_time: float = 0.0
        self._tab_click_id: str | None = None
        # Generation counter to stale-load protection — bumped on every
        # reset_for_new_project()/reload_from_project() so deferred workers
        # from a prior project no-op instead of resurrecting stale tabs.
        self._tabs_generation: int = 0
        self._running_save_tasks: list[str] = []  # worker names for auto-save, cancelled on exit
        # Single persistent RepeaterAPI — created lazily via _get_api()
        self._repeater_api = None
        # The screen is being torn down (app stopped or left the module):
        # deferred call_after_refresh must not create tabs any more.
        self._tearing_down: bool = False

    # ── Query-one short-hands ──────────────────────────────────────────────
    # All 43 query_one() calls replaced with property/helper accessors below
    # so selector strings live in one place and the logic reads concisely.

    @property
    def _tabs_w(self) -> TabbedContent:
        return self.query_one("#repeater-tabs", TabbedContent)

    @property
    def _search_bar(self) -> SearchBar:
        return self.query_one("#repeater-search-bar", SearchBar)

    @property
    def _cancel_btn(self) -> ToolbarButton:
        """Kept for external callers; the button itself is in the module header.

        Send/Cancel moved to the header (`header_spec`), so nothing inside this
        screen should poke them directly — use `refresh_header()`.
        """
        return self.app.query_one("#hdr-state-2", ToolbarButton)

    @property
    def _send_btn(self) -> ToolbarButton:
        """See `_cancel_btn`: Send is a header state button now."""
        return self.app.query_one("#hdr-state-1", ToolbarButton)

    @property
    def _status_bar(self) -> Static:
        return self.query_one("#status-bar", Static)

    @property
    def _diff_panel(self) -> DiffPanel:
        return self.query_one("#repeater-diff-panel", DiffPanel)

    def _notify(self, msg: str, severity: str = "information", timeout: float = 2) -> None:
        """Safe notification through the app-level NotificationsMixin."""
        try:
            app = self.app
            if hasattr(app, "notify"):
                app.notify(msg, severity=severity, timeout=timeout)
        except Exception:
            # The notification was not shown — so the user learned neither of
            # the send error nor of the result. Silence is especially costly
            # here, so this is a warning with a traceback, not debug.
            logger.warning("repeater: notify(%r) failed", msg[:60], exc_info=True)

    def _editor(self, tab_id: str | None = None) -> RequestEditor:
        tid = tab_id or self._active_tab_id
        return self.query_one(f"#req-editor-{tid}", RequestEditor)

    def _viewer(self, tab_id: str | None = None) -> ResponseViewer:
        tid = tab_id or self._active_tab_id
        return self.query_one(f"#resp-viewer-{tid}", ResponseViewer)

    # ── Module header (see pentool/tui/header.py) ─────────────────────────
    def header_spec(self) -> HeaderSpec:
        """One row of actions, in the order they are used.

        Send / Cancel / Follow first, then the tab pair, then the "send to
        another module" group — no `⋯` menu, everything is one click. Repeater's
        own tabs are *documents* (one per request), not module sub-sections, so
        they stay in the TabbedContent.
        """
        sending = self._sending
        return HeaderSpec(
            actions=(
                HeaderAction("send", "⚡ Send", enabled=not sending),
                HeaderAction("cancel", "✖ Cancel", enabled=sending),
                HeaderAction(
                    "follow",
                    "↪ Follow: ON" if self._follow_redirects else "↪ Follow: OFF",
                    enabled=self._follow_redirects,
                ),
                HeaderAction("new_tab", "➕ Tab"),
                HeaderAction("close_tab", "➖ Tab"),
                HeaderAction("decoder", "→ Decoder"),
                HeaderAction("comparer", "→ Comparer"),
                HeaderAction("intruder", "→ Intruder"),
            ),
        )

    #: Header buttons (see `header_spec`) → methods that run them.
    ACTIONS = {
        "send": "action_send",
        "cancel": "action_cancel",
        "follow": "_header_toggle_follow",
        "decoder": "_header_send_to_decoder",
        "comparer": "_header_send_to_comparer",
        "intruder": "_send_to_intruder",
        "new_tab": "action_new_tab",
        "close_tab": "action_close_tab",
    }

    def _header_toggle_follow(self) -> None:
        """Flip redirect-following; the header render reads the flag."""
        self._follow_redirects = not self._follow_redirects

    def _header_send_to_decoder(self) -> None:
        """The action needs the active tab's text, so it cannot be a bare method name."""
        self.run_worker(self._send_to_decoder(self._get_active_text()))

    def _header_send_to_comparer(self) -> None:
        self.run_worker(self._send_to_comparer(self._get_active_text(), label="Repeater Request"))

    def header_tab_selected(self, tab_id: str) -> None:
        """Request tabs are documents — switching them stays in TabbedContent."""
        return None

    def compose(self) -> ComposeResult:
        # Send / Cancel / Follow and the sub-tab actions live in the module header
        # (`header_spec()` below) — the toolbar row is gone, request tabs stay.
        with Horizontal(id="content-row"):
            with Vertical(id="tabs-area"):
                yield TabbedContent(id="repeater-tabs")
            yield DiffPanel(id="repeater-diff-panel")

        yield SearchBar(id="repeater-search-bar")

    def on_mount(self) -> None:
        # Load tabs from database first, then create default tab if empty
        self._load_tabs_from_db()

    def _get_api(self):
        """Return this screen's single persistent RepeaterAPI instance.

        Created lazily on first use and reused for every subsequent call
        (send, history read, auto-save) — mirrors IntruderScreen._get_api /
        ProxyService holding one HttpStorage for the app's lifetime.
        Returns None when no project DB is configured yet.
        """
        if self._repeater_api is None:
            from pentool.api.repeater_api import RepeaterAPI
            from pentool.core.config import get_config

            db_path = self._get_db_path()
            if not db_path:
                return None
            cfg = get_config()
            self._repeater_api = RepeaterAPI(
                db_path=db_path,
                timeout=cfg.request_timeout,
                verify_ssl=cfg.verify_ssl,
            )
        return self._repeater_api

    def on_unmount(self) -> None:
        """The screen is torn down: deferred tab builds and auto-save are no longer needed.

        Without the flag, `_new_tab_if_current`, queued via `call_after_refresh`,
        still managed to run once the app was already stopping and crashed it
        with an exception from `tabs.active`.
        """
        self._tearing_down = True
        self._cancel_save_workers()

    def _load_tabs_from_db(self) -> None:
        """Load saved tabs from database on mount."""
        generation = self._tabs_generation
        db_path = self._get_db_path()
        if not db_path:
            # No DB — create default tab
            self.action_new_tab()
            return

        repeater_api = self._get_api()
        if repeater_api is None:
            self.action_new_tab()
            return
        self.run_worker(self._do_load_tabs(repeater_api, generation), exclusive=False)

    async def _do_load_tabs(self, repeater_api, generation: int | None = None) -> None:
        """Load tabs from DB (generation guards against stale callbacks after project switch)."""
        if generation is None:
            generation = self._tabs_generation
        try:
            # The set of tabs is the `repeater_tabs` table, not the send
            # history: history is append-only, and deriving tabs from it meant
            # resurrecting closed ones after a restart (F-053).
            tabs = await repeater_api.get_tabs()
            if generation != self._tabs_generation:
                return
            if not tabs:
                # Project created before the registry existed: its tabs lived
                # in the history. Build the registry from it once, otherwise
                # after the update the user would see one empty tab.
                tabs = await repeater_api.seed_tabs_from_history()
                if generation != self._tabs_generation:
                    return
            if not tabs:
                self.call_after_refresh(self._new_tab_if_current, generation)
                return

            for row in tabs:
                self._tab_counter += 1
                tab_id = f"tab-{self._tab_counter}"
                state = _TabState(tab_id, row["tab_name"], tab_uid=row["tab_uid"])
                state.request_text = row["request_text"] or state.request_text
                self._tabs.append(state)
                self.call_after_refresh(self._create_tab_ui, tab_id, state, generation)

            if not self._tabs:
                self.call_after_refresh(self._new_tab_if_current, generation)

        except Exception:
            # The project's tabs were not restored — the user will see one empty
            # tab and conclude the data is lost. That is data loss, hence error.
            logger.error("_do_load_tabs: tabs not restored", exc_info=True)
            self.call_after_refresh(self._new_tab_if_current, generation)

    def _new_tab_if_current(self, generation: int) -> None:
        if generation != self._tabs_generation:
            return
        if self._tearing_down or not getattr(self, "is_attached", True):
            # The screen is already being torn down. Creating a tab here got as
            # far as `add_pane` and failed on `tabs.active` — i.e. it crashed app
            # shutdown with an exception from a deferred callback.
            return
        self.action_new_tab()

    def _create_tab_ui(self, tab_id: str, state: _TabState, generation: int | None = None) -> None:
        """Create tab UI and mount widgets."""
        if generation is not None and generation != self._tabs_generation:
            # Stale — a project switch reset the screen after this was
            # scheduled. Drop the now-orphaned state too so it doesn't
            # linger in _tabs from a generation nothing else references.
            self._tabs = [t for t in self._tabs if t is not state]
            return
        try:
            tabs = self._tabs_w
            pane = TabPane(state.name, id=tab_id)
            tabs.add_pane(pane)
            self._active_tab_id = tab_id
            tabs.active = tab_id
            self.call_after_refresh(self._mount_tab_widgets, tab_id, state)
        except Exception as exc:
            logger.debug("_create_tab_ui failed: %s", exc)

    def action_new_tab(self) -> None:
        if self._tearing_down:
            return
        # Commit the outgoing tab BEFORE the new one takes over `_active_tab_id`:
        # `_save_current_tab_state()` reads that field, and assigning it here
        # (as this method and `_create_tab_ui` do) makes the TabActivated that
        # follows save the *new* tab instead — whose editor is not built yet, so
        # it is a no-op and the text typed in the old tab never reaches its
        # state or the database. The widget keeps it until a project reload,
        # which is exactly where the loss surfaces.
        self._save_current_tab_state()
        self._tab_counter += 1
        tab_id = f"tab-{self._tab_counter}"
        name = f"Tab {self._tab_counter}"
        state = _TabState(tab_id, name)
        self._tabs.append(state)

        tabs = self._tabs_w
        pane = TabPane(name, id=tab_id)
        tabs.add_pane(pane)
        try:
            tabs.active = tab_id
        except ValueError as exc:
            # The app stopped between add_pane and activation: the pane is
            # already added but there is nothing to activate it with. Roll the
            # tab back entirely, otherwise state and DOM drift apart.
            logger.debug("repeater: tab %s not activated during teardown: %s", tab_id, exc)
            self._tabs = [t for t in self._tabs if t.tab_id != tab_id]
            return
        self._active_tab_id = tab_id
        self.call_after_refresh(self._mount_tab_widgets, tab_id, state)

    def _mount_tab_widgets(self, tab_id: str, state: _TabState) -> None:
        try:
            pane = self.query_one(f"#{tab_id}", TabPane)
            body = Vertical(classes="tab-body")
            pane.mount(body)
            self.call_after_refresh(self._fill_tab_body, tab_id, state, body)
        except Exception as exc:
            # First step of building the tab body. Breaking here leaves an
            # empty tab — exactly the defect class the audit is looking for.
            logger.error("repeater: tab %s body not mounted: %s", tab_id, exc, exc_info=True)
            self._notify(f"Tab {tab_id}: body could not be built — see the log", severity="error")

    def _fill_tab_body(self, tab_id: str, state: _TabState, body: Vertical) -> None:
        try:
            row = Horizontal(classes="req-resp-row", id=f"req-resp-row-{tab_id}")
            log_area = Static("", classes="log-area", id=f"log-area-{tab_id}")
            body.mount(row)
            body.mount(
                ResizeHandle(
                    f"req-resp-row-{tab_id}",
                    f"log-area-{tab_id}",
                    vertical=True,
                    id=f"resize-bottom-{tab_id}",
                )
            )
            body.mount(log_area)
            self.call_after_refresh(self._fill_req_resp, tab_id, state, row)
        except Exception as exc:
            logger.error("repeater: tab %s layout not filled: %s", tab_id, exc, exc_info=True)

    def _fill_req_resp(self, tab_id: str, state: _TabState, row: Horizontal) -> None:
        try:
            req_panel = Vertical(classes="req-panel card", id=f"req-panel-{tab_id}")
            resp_panel = Vertical(classes="resp-panel card", id=f"resp-panel-{tab_id}")
            row.mount(req_panel)
            row.mount(
                ResizeHandle(
                    f"req-panel-{tab_id}",
                    f"resp-panel-{tab_id}",
                    id=f"resize-{tab_id}",
                )
            )
            row.mount(resp_panel)
            self.call_after_refresh(self._fill_panels, tab_id, state, req_panel, resp_panel)
        except Exception as exc:
            logger.error("repeater: tab %s request/response split failed: %s", tab_id, exc, exc_info=True)

    def _fill_panels(
        self,
        tab_id: str,
        state: _TabState,
        req_panel: Vertical,
        resp_panel: Vertical,
    ) -> None:
        try:
            editor = RequestEditor(
                label="Request Editor",
                role="request-editable",
                id=f"req-editor-{tab_id}",
            )
            req_panel.mount(editor)

            viewer = ResponseViewer(id=f"resp-viewer-{tab_id}")
            resp_panel.mount(viewer)

            self.call_after_refresh(self._init_tab_content, tab_id, state)
        except Exception as exc:
            # Without the editor and the response panel the tab stays empty:
            # Send can be pressed, but there is nowhere to type.
            logger.error("repeater: tab %s editor/viewer not mounted: %s", tab_id, exc, exc_info=True)

    def _init_tab_content(self, tab_id: str, state: _TabState, attempt: int = 0) -> None:
        try:
            editor = self._editor(tab_id)
        except Exception as exc:
            logger.error("repeater: tab %s editor not reachable: %s", tab_id, exc, exc_info=True)
            return
        if not editor.content_mounted:
            # The editor widget exists but its TextArea has not been composed
            # yet — `req_panel.mount(editor)` returns before the children are
            # in the DOM. Loading now raises `NoMatches` inside `load_raw`,
            # which reports it as a failed load and leaves the tab empty while
            # `state.request_text` still holds the request. Wait for the mount
            # instead of guessing.
            if attempt >= _MOUNT_ATTEMPTS:
                logger.error(
                    "repeater: tab %s editor body never composed; request text not shown",
                    tab_id,
                )
                return
            self.call_after_refresh(self._init_tab_content, tab_id, state, attempt + 1)
            return
        try:
            editor.load_raw(state.request_text)
        except Exception as exc:
            # The restored tab is empty even though its text sits in state —
            # i.e. auto-save worked but the load did not.
            logger.error("repeater: tab %s request text not restored: %s", tab_id, exc, exc_info=True)
        else:
            # From here the editor is the source of truth for this tab; only
            # now may its text be read back into `state.request_text`.
            state.ui_ready = True
            # The tab must survive a restart right away, not only after the first
            # edit: a row in `repeater_tabs` is what the project's set of tabs
            # is made of.
            self._auto_save_tab_to_db(state)
        # load_raw() -> TextArea.load_text() posts a Changed event; this
        # initial load must NOT mark the tab dirty. Clear it back to False
        # after the (already-scheduled) Changed handler has run.
        self.call_after_refresh(self._clear_dirty, tab_id)

    def _clear_dirty(self, tab_id: str) -> None:
        state = self._get_tab_state(tab_id)
        if state is None:
            return
        state.is_dirty = False
        self._update_tab_label(state)

    def action_close_tab(self) -> None:
        if len(self._tabs) <= 1:
            return
        tab_id = self._active_tab_id
        if tab_id is None:
            return
        tabs = self._tabs_w
        tabs.remove_pane(tab_id)
        closing = self._get_tab_state(tab_id)
        self._tabs = [t for t in self._tabs if t.tab_id != tab_id]
        if closing is not None:
            self._delete_tab_from_db(closing)
        if self._tabs:
            self._active_tab_id = self._tabs[-1].tab_id
            tabs.active = self._active_tab_id

    # ── Project lifecycle ──────────────────────────────────────────────────────

    async def close_storage(self) -> None:
        """Close the RepeaterAPI handle (contract: ProjectReloadable)."""
        api = self._repeater_api
        if api is None:
            return
        self._repeater_api = None
        await api.close()

    async def reset_for_new_project(self) -> None:
        """Remove all tabs and create a single clean one. Called on Ctrl+N."""
        await self._close_all_tabs()
        self.action_new_tab()

    async def reload_from_project(self, db_path: str) -> None:
        """Load the tabs from the DB. Called when opening an existing project."""
        await self._close_all_tabs()
        # Cancel any in-flight workers (auto-save, _do_load_tabs) from a
        # previous on_mount or project switch BEFORE calling switch_db().
        # switch_db() closes the old connection (close() → self._db = None),
        # and a worker still running against the old connection would hit
        # ProgrammingError('Cannot operate on a closed database.'), which
        # with exit_on_error=True (the default) propagated as a FATAL
        # exception that crashed the whole TUI. Cancelling first lets
        # CancelledError propagate through the worker instead, which Textual
        # handles silently. Mirrors IntruderScreen.reload_from_project.
        try:
            self.workers.cancel_node(self)
        except Exception:
            # A worker that outlived switch_db will touch the closed connection
            # and crash the TUI — that is exactly why cancellation comes first.
            # The crash would happen elsewhere, so the traceback is needed here,
            # where the real cause is visible.
            logger.exception("repeater: in-flight workers not cancelled")
        generation = self._tabs_generation
        # Point the persistent RepeaterAPI at the new project's DB instead of
        # constructing a fresh one — switch_db() closes the old connection
        # (reusing BaseSqliteStorage.switch_db), so no connection to the
        # previous project's file lingers across switches.
        if self._repeater_api is None:
            self._repeater_api = self._get_api()
        if self._repeater_api is not None:
            await self._repeater_api.switch_db(db_path)
        repeater_api = self._repeater_api
        self.run_worker(self._do_load_tabs(repeater_api, generation), exclusive=True)

    async def _close_all_tabs(self) -> None:
        """Remove all tabs and reset state.

        `TabbedContent.clear_panes()` is the proper way to drop all panes at once.
        Removing them one by one left the internal `Tabs` updating `active` for a
        pane that was already gone (`ValueError: No Tab with id '--content-tab-tab-N'`);
        this surfaced on project reload, when the screen holds a single tab.
        """
        self._cancel_save_workers()

        self._tabs_generation += 1  # invalidate any in-flight _do_load_tabs from on_mount
        try:
            await self._tabs_w.clear_panes()
        except Exception as exc:
            # The panes were not removed — yet the list below is cleared anyway,
            # so the tabs in the tree become orphans without state.
            logger.debug("repeater: panes not cleared: %s", exc)
        self._tabs = []
        self._active_tab_id = None
        self._tab_counter = 0  # counter reset — numbering always starts at 1

    def on_tabbed_content_tab_activated(self, event: TabbedContent.TabActivated) -> None:
        if event.tabbed_content.id != "repeater-tabs":
            return
        pane = event.pane
        if pane is None:
            return
        self._save_current_tab_state()
        self._active_tab_id = pane.id
        self._refresh_diff_panel_if_visible()

    def _rename_state(self, tab_id: str) -> object | None:
        """A tab of this screen (the mixin reads `.name` from it)."""
        return self._get_tab_state(tab_id)

    def _apply_tab_rename(self, tab_id: str, new_name: str) -> None:
        state = self._get_tab_state(tab_id)
        if state is None:
            return
        state.name = new_name
        self._update_tab_label(state)
        self._auto_save_tab_to_db(state)

    def _update_tab_label(self, state: _TabState) -> None:
        """Refresh the Tab widget's label to reflect state.name + dirty marker.

        Called after rename, after a successful Send (clears "*"), and after
        an edit is detected (adds "*") — see on_text_area_changed.
        """
        try:
            tabs = self._tabs_w
            tab_widget = tabs.get_tab(state.tab_id)
            if tab_widget is not None:
                suffix = "*" if state.is_dirty else ""
                tab_widget.label = f"{state.name}{suffix}"
        except Exception as exc:
            # The tab label stops reflecting the dirty state — and that is the
            # only sign of an unsaved request (F-031).
            logger.debug("repeater: label not updated for tab %s: %s", state.tab_id, exc)

    def on_text_area_changed(self, event) -> None:
        """Mark the active tab dirty ("*") when its request text changes.

        Only reacts to the editor of the CURRENTLY active tab — inactive
        tabs' TextAreas aren't edited by the user, but load_raw() on a
        background tab (e.g. project reload) would otherwise also fire this.

        The TextArea lives inside ``ContentPanel`` as ``#cp-body-widget``;
        this handler used to look for ``#editor-area``, which no widget has,
        and the resulting ``NoMatches`` was swallowed by ``except Exception``.
        The "*" marker was therefore never set (F-031), and only an e2e test
        running the real app could see it.
        """
        tab_id = self._active_tab_id
        if tab_id is None:
            return
        try:
            editor = self._editor(tab_id)
        except NoMatches:
            return
        area = editor.content_widget
        if event.text_area is not area:
            return
        state = self._get_tab_state(tab_id)
        if state is None:
            return
        was_dirty = state.is_dirty
        if state.last_sent_text is None:
            # Never sent yet — nothing to compare against, no "*" needed.
            new_dirty = False
        else:
            new_dirty = editor.get_text() != state.last_sent_text
        if new_dirty != was_dirty:
            state.is_dirty = new_dirty
            self._update_tab_label(state)
        # If the diff panel is currently open, keep it live-updated as the
        # user types (cheap: compare() runs on small HTTP request texts).
        self._refresh_diff_panel_if_visible()

    def action_toggle_diff(self) -> None:
        """Ctrl+D — toggle the side diff panel: current editor text vs. the
        text of the tab's last successful Send."""
        try:
            panel = self._diff_panel
        except NoMatches as exc:
            # No panel — Ctrl+D will do nothing. Expected only if the screen is
            # not composed yet; `NoMatches` is exactly that case, while a typo in
            # the id would surface as `NoMatches` with a different selector.
            logger.debug("repeater: diff panel not found for toggle: %s", exc)
            return
        now_visible = panel.toggle()
        if now_visible:
            self._refresh_diff_panel_if_visible()

    def _refresh_diff_panel_if_visible(self) -> None:
        try:
            panel = self._diff_panel
        except Exception as exc:
            logger.debug("repeater: diff panel not found for refresh: %s", exc)
            return
        if "-visible" not in panel.classes:
            return
        tab_id = self._active_tab_id
        state = self._get_tab_state(tab_id) if tab_id else None
        if state is None:
            panel.clear()
            return
        if state.last_sent_text is None:
            panel.clear()
            self.app.notify("This tab has not been sent yet — nothing to diff", severity="warning", timeout=3)
            return
        current_text = self._get_active_text()
        panel.show_diff(state.last_sent_text, current_text)

    def action_toggle_search(self) -> None:
        try:
            bar = self._search_bar
            if bar.display:
                bar.hide()
            else:
                bar.show()
        except NoMatches as exc:
            # Ctrl+F did not show the search bar — the key looks dead; the bar is
            # not in the tree, i.e. the screen is not composed yet.
            logger.debug("repeater: search bar not toggled: %s", exc)

    def on_search_bar_search(self, event: SearchBar.Search) -> None:
        """User submitted a search query via SearchBar."""
        self._search_query = event.query
        self._search_regex = event.regex
        self._run_search(event.direction)

    def on_search_bar_target_toggle(self, event: SearchBar.TargetToggle) -> None:
        """User toggled search target (Req/Resp) in SearchBar — sync state."""
        try:
            bar = self._search_bar
            self._search_target = bar._search_target
        except NoMatches as exc:
            # The search target stays as it was: the user switched Req/Resp, but
            # the search will run in the other panel — silently, which misleads.
            # The search bar is absent from the tree, the only `NoMatches` here.
            logger.debug("repeater: search target not synced: %s", exc)

    def on_search_bar_closed(self, event: SearchBar.Closed) -> None:
        self._search_matches = []
        self._search_current = 0

    def _run_search(self, direction: int = 1) -> None:
        """Find matches in the active TextArea and jump to the next one."""
        text = self._get_active_text()
        if not text or not self._search_query:
            return
        try:
            if self._search_regex:
                matches = [m.start() for m in re.finditer(self._search_query, text, re.IGNORECASE)]
            else:
                q = self._search_query.lower()
                t = text.lower()
                matches = []
                start = 0
                while True:
                    idx = t.find(q, start)
                    if idx == -1:
                        break
                    matches.append(idx)
                    start = idx + 1
        except Exception as exc:
            # An invalid regex is normal: we show "no matches". This log entry
            # tells it apart from a real search error.
            logger.debug("repeater: search pattern %r unusable: %s", self._search_query, exc)
            matches = []

        self._search_matches = matches
        if not matches:
            try:
                self._search_bar.set_count(0, 0)
            except Exception as exc:
                # The "0/0" counter was not set — the bar keeps the previous
                # "3/7" while the search is empty.
                logger.debug("repeater: search count not reset: %s", exc)
            return

        if direction == 1:
            self._search_current = (self._search_current + 1) % len(matches)
        else:
            self._search_current = (self._search_current - 1) % len(matches)

        self._jump_to_match(text, matches[self._search_current])
        try:
            self._search_bar.set_count(self._search_current + 1, len(matches))
        except Exception as exc:
            # The cursor jumped but the match number did not.
            logger.debug("repeater: search count not updated: %s", exc)

    def _get_active_text(self) -> str:
        """Text of the panel the search is pointed at (request or response)."""
        if self._active_tab_id is None:
            return ""
        try:
            panel = (
                self._viewer(self._active_tab_id)
                if self._search_target == "response"
                else self._editor(self._active_tab_id)
            )
            return panel.get_text()
        except Exception as exc:
            logger.debug("_get_active_text failed: %s", exc)
            return ""

    def _jump_to_match(self, text: str, offset: int) -> None:
        """Move the TextArea cursor to the found match."""
        if self._active_tab_id is None:
            return
        try:
            panel = (
                self._viewer(self._active_tab_id)
                if self._search_target == "response"
                else self._editor(self._active_tab_id)
            )
            area = panel.content_widget
            if not isinstance(area, TextArea):
                return
            lines = text[:offset].split("\n")
            row = len(lines) - 1
            col = len(lines[-1])
            q_len = len(self._search_query)
            end_lines = text[: offset + q_len].split("\n")
            end_row = len(end_lines) - 1
            end_col = len(end_lines[-1])
            area.move_cursor((row, col), center=True)
            area.selection = Selection((row, col), (end_row, end_col))
        except Exception as exc:
            # N matches found, but the cursor did not jump — the search looks
            # broken even though it did find something.
            logger.debug("repeater: cursor not moved to match at %d: %s", offset, exc)

    def _save_current_tab_state(self) -> None:
        """Save current tab's request text to memory AND database."""
        if self._active_tab_id is None:
            return
        state = self._get_tab_state(self._active_tab_id)
        if state is None:
            return
        if not state.ui_ready:
            # The editor for this tab does not exist yet, so `get_text()`
            # returns "" — saving it would replace the tab's own request text
            # with an empty string. TabbedContent fires TabActivated twice for
            # a new tab and the second one arrives before the editor is built;
            # that is the path that emptied every freshly opened tab.
            return
        try:
            editor = self._editor(self._active_tab_id)
            state.request_text = editor.get_text()
            # Auto-save to DB (async, fire-and-forget)
            self._auto_save_tab_to_db(state)
        except Exception:
            # The tab text never reached state — switching tabs will lose it,
            # which is exactly the loss auto-save exists to prevent. Error level
            # and a traceback: data loss must not be left at debug.
            logger.error("repeater: tab %s state not saved", self._active_tab_id, exc_info=True)

    def _auto_save_tab_to_db(self, state: _TabState) -> None:
        """Persist one tab (upsert by `tab_uid`), fire-and-forget.

        Worker is tracked in _running_save_tasks and cancelled on
        _close_all_tabs() / reset_for_new_project() / reload_from_project()
        so that an in-flight commit doesn't hit a closed database when the
        user exits or switches projects.
        """
        try:
            repeater_api = self._get_api()
            if repeater_api is None:
                return

            order = next((i for i, t in enumerate(self._tabs) if t is state), 0)
            self._start_save_worker(
                repeater_api.save_tab(state.tab_uid, state.name, state.request_text, order),
                self._save_worker_name(f"save-{state.tab_id}"),
            )
        except Exception:
            # The tab never reached the registry: after a restart it will be
            # gone even though the user worked in it.
            logger.error("_auto_save_tab_to_db: tab not persisted", exc_info=True)

    def _delete_tab_from_db(self, state: _TabState) -> None:
        """Forget the tab in the database so it does not return on restart (F-053).

        The send history (`repeater_entries`) is deliberately left alone: it is
        a log of what was sent, not a registry of open tabs.
        """
        try:
            repeater_api = self._get_api()
            if repeater_api is None:
                return
            self._start_save_worker(
                repeater_api.delete_tab(state.tab_uid),
                self._save_worker_name(f"delete-{state.tab_id}"),
            )
        except Exception as exc:
            logger.debug("_delete_tab_from_db: %s", exc)

    def _get_tab_state(self, tab_id: str) -> _TabState | None:
        for t in self._tabs:
            if t.tab_id == tab_id:
                return t
        return None

    def action_send(self) -> None:
        if self._sending:
            return
        tab_id = self._active_tab_id
        if tab_id is None:
            return
        try:
            editor = self._editor(tab_id)
            raw = editor.get_text()
        except NoMatches as exc:
            # Send was pressed but the editor is not in the tree (tab not
            # mounted) — the request was not read, so there is nothing to send.
            logger.debug("repeater: editor not found for send: %s", exc)
            self._notify("Could not read the request — see the log", severity="error")
            return
        except Exception:
            # Same outcome, different cause: the text could not be read from an
            # editor that was found. To the user it is still "not read", but we
            # need a traceback — this is a defect, not an unmounted panel.
            logger.exception("repeater: request text not read for send")
            self._notify("Could not read the request — see the log", severity="error")
            return
        if not raw.strip():
            return
        self._sending = True
        self._set_status("Sending...")
        # Send/Cancel live in the header now: redraw instead of poking buttons
        # that are no longer in this screen's DOM.
        self.refresh_header()
        self.run_worker(self._do_send(tab_id, raw), exclusive=False, name="repeater-send")

    def action_cancel(self) -> None:
        """Cancel the in-flight send (Cancel header button)."""
        # `cancel_group` is a no-op when nothing is running, so no try/except.
        self.workers.cancel_group(self, "repeater-send")
        self._sending = False
        self._set_status("Cancelled")
        self.refresh_header()

    async def _do_send(self, tab_id: str, raw: str) -> None:
        repeater_api = self._get_api()
        service = RepeaterService(repeater_api=repeater_api)

        state = self._get_tab_state(tab_id)
        tab_name = state.name if state else "Tab"

        resp, elapsed_ms, error = await service.send_request(
            raw, tab_name=tab_name, follow_redirects=self._follow_redirects
        )

        if error:
            self._set_status(f"[red]{error}[/red]")
            self._sending = False
            return

        if resp is None:
            self._set_status("[red]Error: empty response[/red]")
            self._sending = False
            return

        try:
            viewer = self._viewer(tab_id)
            viewer.load_response(resp)
        except Exception as exc:
            # The request went out and a response came back, but the panel did not show
            # it — from outside that is "Send is broken" while the status bar says HTTP 200.
            logger.debug("repeater: response not shown for tab %s: %s", tab_id, exc)

        # Successful send — snapshot the sent text and clear the "*" marker.
        if state is not None:
            state.last_sent_text = raw
            state.is_dirty = False
            self._update_tab_label(state)

        self._set_status(f"[green]HTTP {resp.status}[/green] — {len(resp.body)} bytes — {elapsed_ms}ms")
        self._sending = False
        self.refresh_header()
        self.app.notify(f"HTTP {resp.status} — {elapsed_ms}ms", timeout=2)
        await service.close()

    def on_worker_state_changed(self, event) -> None:
        from textual.worker import WorkerState

        if getattr(event.worker, "name", None) != "repeater-send":
            return
        if event.state in (WorkerState.SUCCESS, WorkerState.CANCELLED, WorkerState.ERROR):
            # No `if self._sending` guard: the success path in `_do_send` clears
            # the flag BEFORE this event, so the Send button stayed grey forever
            # (exactly what shows up in manual testing).
            self._sending = False
            # Send/Cancel are header buttons now: one redraw resets both.
            self.refresh_header()

    def action_clear(self) -> None:
        tab_id = self._active_tab_id
        if tab_id is None:
            return
        try:
            self._editor(tab_id).clear()
            self._viewer(tab_id).clear()
        except NoMatches as exc:
            # The status below says "Cleared" while the old request stays on
            # screen — a direct contradiction between word and deed. The panels
            # are absent from the tree, i.e. the tab is not mounted.
            logger.debug("repeater: tab %s not cleared: %s", tab_id, exc)
        self._set_status("Cleared")

    def _send_to_intruder(self) -> None:
        try:
            from pentool.tui.messages import SendToIntruder

            text = self._get_active_text()
            if not text:
                self.app.notify("No request text to send", severity="warning")
                return
            self.app.post_message(SendToIntruder(text))
        except Exception as exc:
            self.err(exc, "Could not send to Intruder")

    def load_request(self, raw: str) -> None:
        """Load a request into the active tab."""
        if self._active_tab_id is None:
            return
        try:
            editor = self._editor(self._active_tab_id)
            editor.load_raw(raw)
        except Exception:
            # The request was not loaded — the tab keeps the previous text, while
            # the user believes the new one was sent. Data loss → error.
            logger.error("repeater: request not loaded into tab %s", self._active_tab_id, exc_info=True)

    def load_request_in_new_tab(self, raw: str) -> None:
        """Open a new tab and load the request into it.

        Used when a request arrives from another module (Proxy, Scanner…)
        so that the user's current work is not overwritten.
        """
        self.action_new_tab()
        # New tab mounts asynchronously — wait via call_after_refresh
        self.call_after_refresh(self._load_into_latest_tab, raw)

    def _load_into_latest_tab(self, raw: str) -> None:
        """Load raw into the most recently created tab (used from load_request_in_new_tab)."""
        if self._active_tab_id is None:
            return
        try:
            editor = self._editor(self._active_tab_id)
            editor.load_raw(raw)
        except Exception:  # logging-ok: expected path — retry via timer
            # Widget not yet mounted — retry with an extra defer
            logger.debug("repeater: editor not ready, retrying via timer")
            state = self._get_tab_state(self._active_tab_id)
            if state is not None:
                state.request_text = raw
            self.set_timer(0.12, lambda: self._load_into_latest_tab_retry(raw))

    def _load_into_latest_tab_retry(self, raw: str) -> None:
        """Retry loading after a delay (widget not yet mounted)."""
        if self._active_tab_id is None:
            return
        try:
            editor = self._editor(self._active_tab_id)
            editor.load_raw(raw)
        except Exception:
            # The retry failed too: the text is already in state but not on
            # screen. Silence here would mean "the request got lost" with no trace.
            logger.warning(
                "repeater: request still not loaded into tab %s after retry",
                self._active_tab_id,
                exc_info=True,
            )

    def _set_status(self, msg: str) -> None:
        try:
            bar = self._status_bar
            bar.update(msg)
        except Exception as exc:
            # The status bar is the only place showing "Sending…", the HTTP code
            # and send errors. Losing it makes the screen mute.
            logger.debug("repeater: status bar not updated: %s", exc)

    # ── context menu ───────────────────────────────────────────────────────────

    def on__base_http_widget_context_menu_request(self, event) -> None:
        """Ctrl+click / right-click on any _BaseHttpWidget → context menu."""
        self.cm_open_text_menu(event.screen_x, event.screen_y)

    def _cm_get_raw_request(self) -> str:
        """Raw HTTP from the active RequestEditor."""
        tab_id = self._active_tab_id
        if not tab_id:
            return ""
        try:
            return self._editor(tab_id).get_text()
        except Exception as exc:
            # An empty string is returned — the menu items will send "nothing",
            # and that will look like the app refusing.
            logger.debug("repeater: request text not read for context menu: %s", exc)
            return ""

    # ── Hotkey action methods ───────────────────────────────────────────

    def action_next_tab(self) -> None:
        """Switch to the next tab (ctrl+tab)."""
        from textual.widgets import TabbedContent

        try:
            tabs = self.query_one(TabbedContent)
            ids = list(tabs._tab_count_index)
            if len(ids) < 2:
                return
            current = self._active_tab_id or ids[0]
            idx = ids.index(current) if current in ids else 0
            next_idx = (idx + 1) % len(ids)
            tabs.active = ids[next_idx]
        except NoMatches as exc:
            # Ctrl+Tab did not switch the tab — the key looks dead; the tab strip
            # is not in the tree.
            logger.debug("repeater: next tab not activated: %s", exc)

    def action_send_to_scanner(self) -> None:
        """Send the active request to Scanner."""
        text = self._get_active_text()
        if not text:
            self.app.notify("No request text to send", severity="warning")
            return
        from pentool.tui.messages import SendToScanner

        self.app.post_message(SendToScanner(text))

    def action_open_in_browser(self) -> None:
        """Open the request URL in the default browser."""
        text = self._get_active_text()
        if not text:
            self.app.notify("No request to open", severity="warning")
            return
        from pentool.utils.parser import ParsedRequest

        parsed = ParsedRequest.from_raw(text)
        if parsed and parsed.url:
            import webbrowser

            webbrowser.open(parsed.url)

"""Repeater screen — manual HTTP request sender."""

from __future__ import annotations

import re
from pathlib import Path

from textual import on
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.widgets import Input, Static, TabbedContent, TabPane
from textual.widgets.text_area import Selection

from pentool.core.logging import get_logger
from pentool.services.repeater_service import RepeaterService
from pentool.tui.widgets.toolbar_button import ToolbarButton

_CSS = (Path(__file__).parent / "screen.tcss").read_text(encoding="utf-8")

logger = get_logger(__name__)

from pentool.tui.mixins.app_mixin import AppMixin
from pentool.tui.mixins.request_context_menu import RequestContextMenuMixin
from pentool.tui.screens.base import BaseModuleScreen
from pentool.tui.widgets.request_editor import RequestEditor, ResponseViewer
from pentool.tui.widgets.resize_handle import ResizeHandle
from pentool.tui.widgets.search_bar import SearchBar


class _TabState:
    """State of a single Repeater tab."""

    def __init__(self, tab_id: str, name: str) -> None:
        self.tab_id = tab_id
        self.name = name
        self.request_text: str = "GET / HTTP/1.1\r\nHost: example.com\r\n\r\n"
        self.response_text: str = ""
        self.sending: bool = False

class RepeaterScreen(BaseModuleScreen, RequestContextMenuMixin, AppMixin):
    """Repeater module screen."""

    DEFAULT_CSS = _CSS

    BINDINGS = [
        Binding("ctrl+f", "toggle_search", "Search", show=False, priority=True),
    ]

    _sort_col_idx: int | None = None
    _sort_reverse: bool = False
    _HIST_COL_LABELS = ["ID", "Method", "URL", "Status", "Length", "Time"]

    # TabRenameMixin config
    _rename_input_id: str = "rename-input"
    _rename_tab_prefix: str = "tab-"
    _rename_tabs_widget_id: str = "repeater-tabs"

    # RequestContextMenuMixin config — Repeater: Send to Intruder + Scanner, no nmap
    _cm_show_nmap          = False
    _cm_show_send_intruder = True
    _cm_show_send_scanner  = True

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._tabs: list[_TabState] = []
        self._tab_counter: int = 0
        self._active_tab_id: str | None = None
        self._sending: bool = False
        self._follow_redirects: bool = True
        self._show_special_chars: bool = False
        self._search_matches: list[int] = []
        self._search_current: int = 0
        self._search_query: str = ""
        self._search_regex: bool = False
        self._tab_click_time: float = 0.0
        self._tab_click_id: str | None = None
        # Bumped by reset_for_new_project()/reload_from_project()/_close_all_tabs().
        # on_mount()'s initial _load_tabs_from_db() reads whatever DB was
        # configured at app startup (before the user creates/opens a
        # project) and schedules tab creation via call_after_refresh — those
        # deferred callbacks used to fire even after a project switch had
        # already reset the screen, resurrecting a stale tab (e.g. one
        # named "Example" from a previous session) alongside the fresh
        # project's tab. Each loader captures the generation at call time
        # and no-ops if it no longer matches when its callback runs.
        self._tabs_generation: int = 0

    def compose(self) -> ComposeResult:
        with Horizontal(id="top-bar"):
            yield ToolbarButton("⚡ Send",      "btn-send")
            yield Static(" │ ", classes="toolbar-sep")
            yield ToolbarButton("✖ Cancel",    "btn-cancel", classes="disabled")
            yield Static(" │ ", classes="toolbar-sep")
            yield ToolbarButton("↪ Follow: ON", "btn-follow", classes="active")
            yield Static(" │ ", classes="toolbar-sep")
            yield ToolbarButton("➕ Tab",   "btn-new-tab")
            yield Static(" │ ", classes="toolbar-sep")
            yield ToolbarButton("➖ Tab", "btn-close-tab")
            yield Static(" │ ", classes="toolbar-sep")
            yield ToolbarButton("⏎ Special: OFF", "btn-special-chars")
            yield Static(" │ ", classes="toolbar-sep")
            yield ToolbarButton(
                "✨ Beautify", "btn-beautify",
                tooltip="Format request and response body (JSON/XML)"
            )
            yield Static(" │ ", classes="toolbar-sep")
            yield ToolbarButton("→ Decoder",  "btn-send-decoder")
            yield Static(" │ ", classes="toolbar-sep")
            yield ToolbarButton("→ Comparer", "btn-send-comparer")
            yield Static(" │ ", classes="toolbar-sep")
            yield ToolbarButton("→ Intruder", "btn-send-intruder")

        with Vertical(id="tabs-area"):
            yield TabbedContent(id="repeater-tabs")

        yield SearchBar(id="repeater-search-bar")
        yield Static("Ctrl+Space: Send  │  Ctrl+F: Search  │  Double-click tab to rename", id="status-bar")

    def on_mount(self) -> None:
        # Load tabs from database first, then create default tab if empty
        self._load_tabs_from_db()

    def _load_tabs_from_db(self) -> None:
        """Load saved tabs from database on mount."""
        generation = self._tabs_generation
        db_path = self._get_db_path()
        if not db_path:
            # No DB — create default tab
            self.action_new_tab()
            return

        from pentool.api.repeater_api import RepeaterAPI
        from pentool.core.config import get_config
        cfg = get_config()
        repeater_api = RepeaterAPI(db_path=db_path, timeout=cfg.request_timeout, verify_ssl=cfg.verify_ssl)
        self.run_worker(self._do_load_tabs(repeater_api, generation), exclusive=False)

    async def _do_load_tabs(self, repeater_api, generation: int | None = None) -> None:
        """Async worker to load tabs from DB.

        `generation` pins this call to the _tabs_generation value at the
        time it was scheduled — if reset_for_new_project()/reload_from_project()
        bump the counter before this worker's deferred UI callbacks run
        (e.g. the startup load racing a just-created/opened project), those
        callbacks silently no-op instead of resurrecting a stale tab.
        """
        if generation is None:
            generation = self._tabs_generation
        try:
            entries = await repeater_api.get_history(limit=20)
            if generation != self._tabs_generation:
                return
            if not entries:
                self.call_after_refresh(self._new_tab_if_current, generation)
                return

            # Group entries by tab_name — keep the most recent entry per tab
            tabs_dict: dict = {}
            for entry in reversed(entries):  # oldest first → newest wins
                tabs_dict[entry.tab_name] = entry

            for tab_name, entry in tabs_dict.items():
                self._tab_counter += 1
                tab_id = f"tab-{self._tab_counter}"
                from pentool.utils.parser import build_http_request
                raw = build_http_request(entry.request)
                state = _TabState(tab_id, tab_name)
                state.request_text = raw
                self._tabs.append(state)
                self.call_after_refresh(self._create_tab_ui, tab_id, state, generation)

            if not self._tabs:
                self.call_after_refresh(self._new_tab_if_current, generation)

        except Exception as exc:
            # Table may not exist yet in a brand-new project — that's fine
            logger.debug("_do_load_tabs: %s", exc)
            self.call_after_refresh(self._new_tab_if_current, generation)

    def _new_tab_if_current(self, generation: int) -> None:
        if generation == self._tabs_generation:
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
            tabs = self.query_one("#repeater-tabs", TabbedContent)
            pane = TabPane(state.name, id=tab_id)
            tabs.add_pane(pane)
            self._active_tab_id = tab_id
            tabs.active = tab_id
            self.call_after_refresh(self._mount_tab_widgets, tab_id, state)
        except Exception as exc:
            logger.debug("_create_tab_ui failed: %s", exc)

    def action_new_tab(self) -> None:
        self._tab_counter += 1
        tab_id = f"tab-{self._tab_counter}"
        name = f"Tab {self._tab_counter}"
        state = _TabState(tab_id, name)
        self._tabs.append(state)

        tabs = self.query_one("#repeater-tabs", TabbedContent)
        pane = TabPane(name, id=tab_id)
        tabs.add_pane(pane)
        tabs.active = tab_id
        self._active_tab_id = tab_id
        self.call_after_refresh(self._mount_tab_widgets, tab_id, state)

    def _mount_tab_widgets(self, tab_id: str, state: _TabState) -> None:
        try:
            pane = self.query_one(f"#{tab_id}", TabPane)
            body = Vertical(classes="tab-body")
            pane.mount(body)
            self.call_after_refresh(self._fill_tab_body, tab_id, state, body)
        except Exception:
            pass

    def _fill_tab_body(self, tab_id: str, state: _TabState, body: Vertical) -> None:
        try:
            row = Horizontal(classes="req-resp-row", id=f"req-resp-row-{tab_id}")
            log_area = Static("", classes="log-area", id=f"log-area-{tab_id}")
            body.mount(row)
            body.mount(ResizeHandle(
                f"req-resp-row-{tab_id}", f"log-area-{tab_id}",
                vertical=True,
                id=f"resize-bottom-{tab_id}",
            ))
            body.mount(log_area)
            self.call_after_refresh(self._fill_req_resp, tab_id, state, row)
        except Exception:
            pass

    def _fill_req_resp(self, tab_id: str, state: _TabState, row: Horizontal) -> None:
        try:
            req_panel = Vertical(classes="req-panel", id=f"req-panel-{tab_id}")
            resp_panel = Vertical(classes="resp-panel", id=f"resp-panel-{tab_id}")
            row.mount(req_panel)
            row.mount(ResizeHandle(
                f"req-panel-{tab_id}", f"resp-panel-{tab_id}",
                id=f"resize-{tab_id}",
            ))
            row.mount(resp_panel)
            self.call_after_refresh(self._fill_panels, tab_id, state, req_panel, resp_panel)
        except Exception:
            pass

    def _fill_panels(
        self,
        tab_id: str,
        state: _TabState,
        req_panel: Vertical,
        resp_panel: Vertical,
    ) -> None:
        try:
            editor = RequestEditor(label="Request Editor", id=f"req-editor-{tab_id}")
            req_panel.mount(editor)

            viewer = ResponseViewer(id=f"resp-viewer-{tab_id}")
            resp_panel.mount(viewer)

            self.call_after_refresh(self._init_tab_content, tab_id, state)
        except Exception:
            pass

    def _init_tab_content(self, tab_id: str, state: _TabState) -> None:
        try:
            editor = self.query_one(f"#req-editor-{tab_id}", RequestEditor)
            editor.load_raw(state.request_text)
        except Exception:
            pass

    def action_close_tab(self) -> None:
        if len(self._tabs) <= 1:
            return
        tab_id = self._active_tab_id
        if tab_id is None:
            return
        tabs = self.query_one("#repeater-tabs", TabbedContent)
        tabs.remove_pane(tab_id)
        self._tabs = [t for t in self._tabs if t.tab_id != tab_id]
        if self._tabs:
            self._active_tab_id = self._tabs[-1].tab_id
            tabs.active = self._active_tab_id

    # ── Project lifecycle ──────────────────────────────────────────────────────

    async def reset_for_new_project(self) -> None:
        """Удалить все вкладки и создать одну чистую. Вызывается при Ctrl+N."""
        await self._close_all_tabs()
        self.action_new_tab()

    async def reload_from_project(self, db_path: str) -> None:
        """Загрузить вкладки из БД. Вызывается при открытии существующего проекта."""
        await self._close_all_tabs()
        generation = self._tabs_generation
        from pentool.api.repeater_api import RepeaterAPI
        from pentool.core.config import get_config
        cfg = get_config()
        repeater_api = RepeaterAPI(db_path=db_path, timeout=cfg.request_timeout, verify_ssl=cfg.verify_ssl)
        self.run_worker(self._do_load_tabs(repeater_api, generation), exclusive=True)

    async def _close_all_tabs(self) -> None:
        """Удалить все существующие вкладки из TabbedContent и сбросить состояние.

        remove_pane() returns an AwaitComplete (Textual schedules the actual
        tab/pane removal, it does not happen synchronously) — this was
        previously called without awaiting it, so action_new_tab() right
        after could create a new pane with the same id (e.g. "tab-1", since
        _tab_counter is reset to 0) before the old one had actually been
        removed from the DOM. That raced with Textual's own ID uniqueness
        check and produced a stray, blank/unlabeled tab to the left of the
        first real tab — reproducible specifically right after creating a
        new project (reset_for_new_project), not after a full app restart.
        """
        self._tabs_generation += 1  # invalidate any in-flight _do_load_tabs from on_mount
        try:
            tabs = self.query_one("#repeater-tabs", TabbedContent)
            for state in list(self._tabs):
                try:
                    await tabs.remove_pane(state.tab_id)
                except Exception:
                    pass
        except Exception:
            pass
        self._tabs = []
        self._active_tab_id = None
        self._tab_counter = 0  # сброс счётчика — нумерация всегда с 1

    def on_tabbed_content_tab_activated(self, event: TabbedContent.TabActivated) -> None:
        if event.tabbed_content.id != "repeater-tabs":
            return
        pane = event.pane
        if pane is None:
            return
        self._save_current_tab_state()
        self._active_tab_id = pane.id

    def _start_rename(self, tab_id: str) -> None:
        state = self._get_tab_state(tab_id)
        if state is None:
            return
        try:
            try:
                inp = self.query_one("#rename-input", Input)
            except Exception:
                inp = Input(id="rename-input", placeholder="Tab name...", compact=True)
                self.query_one("#tabs-area").mount(inp)
            inp.value = state.name
            inp.display = True
            inp.focus()
            inp.action_select_all()
            inp._rename_tab_id = tab_id  # type: ignore[attr-defined]
        except Exception:
            pass

    def _rename_tab(self, tab_id: str, new_name: str) -> None:
        state = self._get_tab_state(tab_id)
        if state is None:
            return
        state.name = new_name
        try:
            tabs = self.query_one("#repeater-tabs", TabbedContent)
            tab_widget = tabs.get_tab(tab_id)
            if tab_widget is not None:
                tab_widget.label = new_name
        except Exception:
            pass
        self._auto_save_tab_to_db(state)

    def action_toggle_search(self) -> None:
        try:
            bar = self.query_one("#repeater-search-bar", SearchBar)
            if bar.display:
                bar.hide()
            else:
                bar.show()
        except Exception:
            pass

    def on_search_bar_search(self, event: SearchBar.Search) -> None:
        """User submitted a search query via SearchBar."""
        self._search_query = event.query
        self._search_regex = event.regex
        self._run_search(event.direction)

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
        except Exception:
            matches = []

        self._search_matches = matches
        if not matches:
            try:
                self.query_one("#repeater-search-bar", SearchBar).set_count(0, 0)
            except Exception:
                pass
            return

        if direction == 1:
            self._search_current = (self._search_current + 1) % len(matches)
        else:
            self._search_current = (self._search_current - 1) % len(matches)

        self._jump_to_match(text, matches[self._search_current])
        try:
            self.query_one("#repeater-search-bar", SearchBar).set_count(
                self._search_current + 1, len(matches)
            )
        except Exception:
            pass

    def _get_active_text(self) -> str:
        if self._active_tab_id is None:
            return ""
        try:
            editor = self.query_one(f"#req-editor-{self._active_tab_id}", RequestEditor)
            return editor.get_text()
        except Exception:
            return ""

    def _jump_to_match(self, text: str, offset: int) -> None:
        """Move the TextArea cursor to the found match."""
        if self._active_tab_id is None:
            return
        try:
            from textual.widgets import TextArea
            editor = self.query_one(f"#req-editor-{self._active_tab_id}", RequestEditor)
            area = editor.query_one("#editor-area", TextArea)
            lines = text[:offset].split("\n")
            row = len(lines) - 1
            col = len(lines[-1])
            q_len = len(self._search_query)
            end_lines = text[:offset + q_len].split("\n")
            end_row = len(end_lines) - 1
            end_col = len(end_lines[-1])
            area.move_cursor((row, col), center=True)
            area.selection = Selection((row, col), (end_row, end_col))
        except Exception:
            pass

    def _save_current_tab_state(self) -> None:
        """Save current tab's request text to memory AND database."""
        if self._active_tab_id is None:
            return
        state = self._get_tab_state(self._active_tab_id)
        if state is None:
            return
        try:
            editor = self.query_one(f"#req-editor-{self._active_tab_id}", RequestEditor)
            state.request_text = editor.get_text()
            # Auto-save to DB (async, fire-and-forget)
            self._auto_save_tab_to_db(state)
        except Exception:
            pass

    def _auto_save_tab_to_db(self, state: _TabState) -> None:
        """Save tab state to database (non-blocking, fire-and-forget)."""
        try:
            from pentool.utils.parser import ParsedResponse, parse_http_request
            parsed = parse_http_request(state.request_text)
            # Don't save empty or placeholder requests
            if not parsed or not parsed.url or not parsed.method:
                return

            response = ParsedResponse(status=0, headers={}, body="")

            db_path = self._get_db_path()
            if not db_path:
                return

            from pentool.api.repeater_api import RepeaterAPI
            from pentool.core.config import get_config
            cfg = get_config()
            repeater_api = RepeaterAPI(db_path=db_path, timeout=cfg.request_timeout, verify_ssl=cfg.verify_ssl)
            self.run_worker(
                repeater_api.save_to_history(parsed, response, tab_name=state.name),
                exclusive=False,
            )
        except Exception as exc:
            logger.debug("_auto_save_tab_to_db: %s", exc)

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
            editor = self.query_one(f"#req-editor-{tab_id}", RequestEditor)
            raw = editor.get_text()
        except Exception:
            return
        if not raw.strip():
            return
        self._sending = True
        self._set_status("Sending...")
        try:
            self.query_one("#btn-cancel", ToolbarButton).disabled = False
        except Exception:
            pass
        self.run_worker(self._do_send(tab_id, raw), exclusive=False, name="repeater-send")

    async def _do_send(self, tab_id: str, raw: str) -> None:
        db_path = self._get_db_path()
        from pentool.api.repeater_api import RepeaterAPI
        from pentool.core.config import get_config
        cfg = get_config()
        repeater_api = (
            RepeaterAPI(db_path=db_path, timeout=cfg.request_timeout, verify_ssl=cfg.verify_ssl)
            if db_path else None
        )
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

        try:
            viewer = self.query_one(f"#resp-viewer-{tab_id}", ResponseViewer)
            viewer.load_response(resp)
        except Exception:
            pass

        self._set_status(
            f"[green]HTTP {resp.status}[/green] — {len(resp.body)} bytes — {elapsed_ms}ms"
        )
        self._sending = False
        try:
            self.query_one("#btn-cancel", ToolbarButton).disabled = True
        except Exception:
            pass
        self.app.notify(f"HTTP {resp.status} — {elapsed_ms}ms", timeout=2)
        await service.close()

    def on_worker_state_changed(self, event) -> None:
        from textual.worker import WorkerState
        if getattr(event.worker, "name", None) != "repeater-send":
            return
        if event.state in (WorkerState.SUCCESS, WorkerState.CANCELLED, WorkerState.ERROR):
            if self._sending:
                self._sending = False
                try:
                    self.query_one("#btn-send", ToolbarButton).disabled = False
                    self.query_one("#btn-cancel", ToolbarButton).disabled = True
                except Exception:
                    pass

    def action_clear(self) -> None:
        tab_id = self._active_tab_id
        if tab_id is None:
            return
        try:
            self.query_one(f"#req-editor-{tab_id}", RequestEditor).clear()
            self.query_one(f"#resp-viewer-{tab_id}", ResponseViewer).clear()
        except Exception:
            pass
        self._set_status("Cleared")

    @on(ToolbarButton.Pressed, "#btn-send")
    def on_btn_send(self, _: ToolbarButton.Pressed) -> None:
        self.action_send()

    @on(ToolbarButton.Pressed, "#btn-follow")
    def on_btn_follow(self, event: ToolbarButton.Pressed) -> None:
        self._follow_redirects = not self._follow_redirects
        btn = event.button
        if self._follow_redirects:
            btn.update("↪ Follow: ON")
            btn.add_class("active")
        else:
            btn.update("↪ Follow: OFF")
            btn.remove_class("active")

    @on(ToolbarButton.Pressed, "#btn-new-tab")
    def on_btn_new_tab(self, _: ToolbarButton.Pressed) -> None:
        self.action_new_tab()

    @on(ToolbarButton.Pressed, "#btn-close-tab")
    def on_btn_close_tab(self, _: ToolbarButton.Pressed) -> None:
        self.action_close_tab()

    @on(ToolbarButton.Pressed, "#btn-special-chars")
    def on_btn_special_chars(self, event: ToolbarButton.Pressed) -> None:
        self._toggle_special_chars(event.button)

    @on(ToolbarButton.Pressed, "#btn-beautify")
    def on_btn_beautify(self, _: ToolbarButton.Pressed) -> None:
        self._beautify_active_request()

    def _beautify_active_request(self) -> None:
        """Beautify both Request and Response panels of the active tab —
        previously this only reformatted the request body."""
        if self._active_tab_id is None:
            return
        req_ok = False
        resp_ok = False
        try:
            editor = self.query_one(f"#req-editor-{self._active_tab_id}", RequestEditor)
            req_ok = editor.beautify_body()
        except Exception:
            pass
        try:
            viewer = self.query_one(f"#resp-viewer-{self._active_tab_id}", ResponseViewer)
            resp_ok = viewer.beautify_body()
        except Exception:
            pass

        if req_ok and resp_ok:
            self.notify("Request and response beautified", timeout=2)
        elif req_ok:
            self.notify("Request beautified (response body not valid JSON/XML)", timeout=2)
        elif resp_ok:
            self.notify("Response beautified (request body not valid JSON/XML)", timeout=2)
        else:
            self.notify("Nothing to beautify — no valid JSON/XML body found", severity="warning", timeout=3)

    @on(ToolbarButton.Pressed, "#btn-send-decoder")
    def on_btn_send_decoder(self, _: ToolbarButton.Pressed) -> None:
        self._send_to_decoder(self._get_active_text())

    @on(ToolbarButton.Pressed, "#btn-send-comparer")
    def on_btn_send_comparer(self, _: ToolbarButton.Pressed) -> None:
        self._send_to_comparer(self._get_active_text(), label="Repeater Request")

    @on(ToolbarButton.Pressed, "#btn-send-intruder")
    def on_btn_send_intruder(self, _: ToolbarButton.Pressed) -> None:
        self._send_to_intruder()

    def _send_to_intruder(self) -> None:
        try:
            from pentool.tui.messages import SendToIntruder
            text = self._get_active_text()
            if not text:
                self.app.notify("No request text to send", severity="warning")
                return
            self.app.post_message(SendToIntruder(text))
        except Exception as exc:
            logger.debug("_send_to_intruder: %s", exc)
            self.app.notify(f"Could not send to Intruder: {exc}", severity="error")

    def on_key(self, event) -> None:
        if event.key == "ctrl+j":
            self.action_send()
            event.prevent_default()

    def load_request(self, raw: str) -> None:
        """Load a request into the active tab."""
        if self._active_tab_id is None:
            return
        try:
            editor = self.query_one(f"#req-editor-{self._active_tab_id}", RequestEditor)
            editor.load_raw(raw)
        except Exception:
            pass

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
            editor = self.query_one(f"#req-editor-{self._active_tab_id}", RequestEditor)
            editor.load_raw(raw)
        except Exception:
            # Widget not yet mounted — retry with an extra defer
            state = self._get_tab_state(self._active_tab_id)
            if state is not None:
                state.request_text = raw
            self.set_timer(0.12, lambda: self._load_into_latest_tab_retry(raw))

    def _load_into_latest_tab_retry(self, raw: str) -> None:
        """Retry loading after a delay (widget not yet mounted)."""
        if self._active_tab_id is None:
            return
        try:
            editor = self.query_one(f"#req-editor-{self._active_tab_id}", RequestEditor)
            editor.load_raw(raw)
        except Exception:
            pass

    def _toggle_special_chars(self, btn: ToolbarButton) -> None:
        """Toggle display of special characters \r\n in the editor."""
        # Sync _raw_body from the current TextArea state before switching
        self._sync_raw_body_from_editor()
        self._show_special_chars = not self._show_special_chars
        if self._show_special_chars:
            btn.update("⏎ Special: ON")
            btn.add_class("active")
        else:
            btn.update("⏎ Special: OFF")
            btn.remove_class("active")
        self._apply_special_chars_to_active_tab()

    def _sync_raw_body_from_editor(self) -> None:
        """Commit the current text as _raw_full before switching mode."""
        tab_id = self._active_tab_id
        if tab_id is None:
            return
        try:
            editor = self.query_one(f"#req-editor-{tab_id}", RequestEditor)
            editor._raw_full = editor.get_text()
        except Exception:
            pass

    def _apply_special_chars_to_active_tab(self) -> None:
        tab_id = self._active_tab_id
        if tab_id is None:
            return
        try:
            from textual.widgets import TextArea
            from pentool.tui.widgets.request_editor import visualize_special_chars
            editor = self.query_one(f"#req-editor-{tab_id}", RequestEditor)
            area = editor.query_one("#editor-area", TextArea)
            if self._show_special_chars:
                raw = editor._raw_full or editor.get_text()
                displayed = visualize_special_chars(raw)
                editor._special_chars_mode = True
                area.load_text(displayed)
            else:
                decoded = RequestEditor._decode_special_chars(area.text)
                editor._raw_full = decoded
                editor._special_chars_mode = False
                editor.load_raw(decoded)
        except Exception:
            pass


    def _set_status(self, msg: str) -> None:
        try:
            bar = self.query_one("#status-bar", Static)
            bar.update(msg)
        except Exception:
            pass

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
            from pentool.tui.widgets.request_editor import RequestEditor
            return self.query_one(f"#req-editor-{tab_id}", RequestEditor).get_text()
        except Exception:
            return ""

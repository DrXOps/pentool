"""Intruder screen — automated attacks with payloads.

Табы организованы через TabbedContentPanel: каждый таб (TabPane) содержит
свои per-tab виджеты (template editor, payloads panel, processing bar).
Глобальные секции (toolbar, results, detail panel) остаются снаружи.
"""

from __future__ import annotations

import asyncio
import re
import time
from dataclasses import dataclass, field
from pathlib import Path

from textual import events as _tevents
from textual import on
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import (
    Input,
    Label,
    ListItem,
    ListView,
    ProgressBar,
    Static,
    TabPane,
    TabbedContent,
    TextArea,
)

_CSS = (Path(__file__).parent / "screen.tcss").read_text(encoding="utf-8")

from pentool.api.intruder_api import (
    AttackType,
    ChainedPayloadSource,
    CharPayloadSource,
    FilePayloadSource,
    IntruderConfig,
    IntruderResult,
    NumericPayloadSource,
    ProcessedPayloads,
    count_lines_with_progress,
    count_markers,
    process_payload,
)
from pentool.api.payload_serialization import deserialize_payloads, serialize_payloads
from pentool.collections.filter_predicate import FilterOp, FilterPredicate, FilterSpec
from pentool.core.logging import get_logger
from pentool.tui.hotkeys.defaults import INTRUDER_BINDINGS
from pentool.tui.messages import SendToRepeater

from pentool.tui.mixins.app_mixin import AppMixin
from pentool.tui.mixins.autosave import AutoSaveMixin
from pentool.tui.mixins.content_clipboard_mixin import ContentClipboardMixin
from pentool.tui.mixins.dialog_cancel import DialogCancelMixin
from pentool.tui.mixins.request_context_menu import RequestContextMenuMixin
from pentool.tui.screens.base import BaseModuleScreen
from pentool.tui.widgets.data_table_mixins import SortableTableMixin
from pentool.tui.widgets.nice_checkbox import NiceCheckbox as Checkbox
from pentool.tui.widgets.start_stop_widget import StartStopWidget
from pentool.tui.widgets.option_cycler import OptionCycler
from pentool.tui.widgets.request_editor import HttpView, _load_into_textarea
from pentool.tui.widgets.resize_handle import ResizeHandle
from pentool.tui.widgets.content_panel import ContentPanel
from pentool.tui.widgets.toolbar_button import ToolbarButton
from pentool.tui.widgets.toolbar import Toolbar
from pentool.tui.widgets.intruder_filter_bar import IntruderFilterBar as _IntruderFilterBar
from pentool.tui.widgets.intruder_results_table import IntruderResultsTable
from pentool.tui.widgets.tab_panel import TabbedContentPanel
from pentool.tui.dialogs.intruder_input import InputDialog
from pentool.tui.dialogs.intruder_generate import GenerateDialog
from pentool.tui.dialogs.intruder_smart_payloads import SmartPayloadsDialog

logger = get_logger(__name__)


# Module constants
_ATTACK_LABELS = {
    AttackType.SNIPER:        "Sniper",
    AttackType.BATTERING_RAM: "Battering Ram",
    AttackType.PITCHFORK:     "Pitchfork",
    AttackType.CLUSTER_BOMB:  "Cluster Bomb",
}
_ATTACK_DESCRIPTIONS = {
    AttackType.SNIPER:        "One payload set, one position at a time",
    AttackType.BATTERING_RAM: "One payload set, all positions simultaneously",
    AttackType.PITCHFORK:     "Multiple sets, parallel (zip)",
    AttackType.CLUSTER_BOMB:  "Cartesian product of all sets",
}

_RESULTS_COL_NAMES = ["#", "Payload(s)", "Status", "Length", "Time(ms)", "Error"]

_PAYLOAD_LIST_PREVIEW_LIMIT = 500
_LAZY_SOURCE_TYPES = (FilePayloadSource, NumericPayloadSource, CharPayloadSource, ChainedPayloadSource)
DataTable = IntruderResultsTable


@dataclass
class _IntruderTabState:
    """Состояние одного таба Intruder."""

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
    payload_load_in_progress: bool = False
    last_payload_sets: list | None = None


class IntruderScreen(BaseModuleScreen, AppMixin, ContentClipboardMixin, AutoSaveMixin,
                     SortableTableMixin, RequestContextMenuMixin):
    """Intruder module screen with per-tab isolated widgets."""

    DEFAULT_CSS = _CSS
    BINDINGS = INTRUDER_BINDINGS

    # TabRenameMixin config (оставлено для совместимости, но делегирует в TabbedContentPanel)
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
        # Старый _tabs для обратной совместимости (тесты)
        self._tabs: list[_IntruderTabState] = []
        self._active_tab_id: str | None = None
        self._tab_counter: int = 0
        # ── Фабрика табов для TabbedContentPanel ──
        # Когда TabbedContentPanel создаёт дефолтный таб (без state),
        # использует _IntruderTabState вместо _DummyState.
        import uuid as _uuid
        def _factory(tab_id: str, name: str) -> _IntruderTabState:
            return _IntruderTabState(
                tab_id=tab_id,
                name=name,
                tab_uid=_uuid.uuid4().hex,
            )
        self._tab_factory = _factory
        # ── API ──
        self._api = None
        # Grep-состояние (глобальное, для фильтрации результатов)
        self._grep_match_patterns: list[str] = []
        self._grep_extract_patterns: list[str] = []
        self._grep_only_match: bool = False
        # Saved selection in template-editor (for ADD §§ after focus loss)
        self._last_editor_selection: tuple | None = None
        self._last_click_time: float = 0.0
        # Auto-save state
        self._state_loaded: bool = False
        self._running_save_tasks: list[str] = []

    # ── Active tab state ─────────────────────────────────────────────────

    @property
    def _tc_panel(self) -> TabbedContentPanel:
        """TabbedContentPanel виджет."""
        return self.query_one("#intruder-tabs", TabbedContentPanel)

    @property
    def _active_tab(self) -> _IntruderTabState | None:
        """Return active tab state, with fallback to old _tabs list for tests."""
        try:
            panel = self._tc_panel
            st = panel.active_state
            if st is not None:
                return st  # type: ignore[return-value]
        except Exception:
            pass
        # Fallback для тестов (без compose)
        if hasattr(self, "_tabs") and self._active_tab_id:
            for t in self._tabs:
                if t.tab_id == self._active_tab_id:
                    return t
        return None

    # Прокси-свойства для обратной совместимости (все читают из _active_tab)
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

    @property
    def _ssw(self) -> StartStopWidget:
        return self.query_one(StartStopWidget)

    # ── StartStopWidget handlers ───────────────────────────────────────────

    @on(StartStopWidget.StartRequested)
    def _on_start_requested(self, _: StartStopWidget.StartRequested) -> None:
        self.action_start_attack()

    @on(StartStopWidget.StopRequested)
    def _on_stop_requested(self, _: StartStopWidget.StopRequested) -> None:
        self.action_stop()

    @on(StartStopWidget.PauseRequested)
    def _on_pause_requested(self, _: StartStopWidget.PauseRequested) -> None:
        self.action_toggle_pause()

    @on(StartStopWidget.ResumeRequested)
    def _on_resume_requested(self, _: StartStopWidget.ResumeRequested) -> None:
        self.action_resume()

    # ── Per-tab widget helpers ────────────────────────────────────────────

    @staticmethod
    def _wid(tab_id: str, suffix: str) -> str:
        return f"{suffix}-{tab_id}"

    def _tab_widget(self, tab_id: str, suffix: str, widget_cls: type) -> object:
        return self.query_one(f"#{self._wid(tab_id, suffix)}", widget_cls)

    def _template_editor(self) -> ContentPanel:
        """Вернуть ContentPanel активного таба (геттер per-tab)."""
        tab = self._active_tab
        if tab is None:
            raise LookupError("no active tab")
        wid = self._wid(tab.tab_id, "template-panel")
        return self.query_one(f"#{wid}", ContentPanel)

    # ── BUILD TAB UI ──────────────────────────────────────────────────────
    # Вызывается из TabbedContentPanel._do_build_ui ПОСЛЕ add_pane()
    # TabPane уже в DOM → mount() работает.

    @staticmethod
    def _mount_tab_ui(state: _IntruderTabState, tab_id: str) -> None:
        """Смонтировать per-tab виджеты в TabPane (TabPane уже в DOM)."""
        from textual.widgets import TabbedContent, TabPane as _TabPane
        import inspect
        # Ищем TabPane через DOM — используем query_one по id
        # Это будет из контекста TabbedContentPanel → find
        try:
            # Stack: _mount_tab_ui <- _do_build_ui <- _post_tab_messages <- call_after_refresh
            # У нас нет self экрана.
            # Единственный путь: TabPane уже в DOM как #id
            # Вызывающий — TabbedContentPanel, он в DOM.
            # Найти через корень DOM не можем без self.
            #
            # РЕШЕНИЕ: передавать self в callback или сделать
            # _mount_tab_ui методом экрана. НО это статик.
            #
            # Самый простой путь: _build_tab_ui возвращает TabPane
            # с детьми через *children, без отдельного mount.
            pass
        except Exception:
            pass

    @staticmethod
    def _build_tab_ui(state: _IntruderTabState, tab_id: str) -> TabPane:
        """Создать TabPane с per-tab виджетами.

        Использует *children — Textual разместит детей после
        того как TabPane попадёт в DOM (через add_pane).
        """
        template = ContentPanel(
            title=f"Request Template — {state.name}",
            widget_type="textarea",
            initial_text=state.template_text or "GET / HTTP/1.1\r\nHost: example.com\r\n\r\n",
            buttons=["copy", "paste", "clear"],
            id=f"template-panel-{tab_id}",
            classes="intruder-template-panel",
        )

        pldiv = Vertical(
            Static("Payloads", classes="section-title"),
            ListView(id=f"payload-list-{tab_id}", classes="intruder-payload-list"),
            Static("", id=f"payload-count-label-{tab_id}", classes="payload-count-label"),
            classes="intruder-payloads-panel",
            id=f"payloads-panel-{tab_id}",
        )

        proc = Horizontal(
            Label("Processing:", classes="proc-label"),
            Checkbox("URL encode",  id=f"proc-url-encode-{tab_id}",  value=False),
            Checkbox("Base64",      id=f"proc-base64-{tab_id}",      value=False),
            Checkbox("HTML encode", id=f"proc-html-encode-{tab_id}", value=False),
            Checkbox("MD5",         id=f"proc-md5-{tab_id}",         value=False),
            classes="proc-bar",
            id=f"processing-bar-{tab_id}",
        )

        return TabPane(state.name, template, pldiv, proc, id=tab_id)

    # ── TabbedContentPanel message handlers ───────────────────────────────
    # Когда пользователь переключает таб — TabbedContentPanel постит
    # TabDeactivated (старый таб) и TabActivated (новый таб).

    @on(TabbedContentPanel.TabDeactivated, "#intruder-tabs")
    def _on_tab_deactivated(self, event: TabbedContentPanel.TabDeactivated) -> None:
        """Сохранить состояние старого таба перед переключением."""
        state = event.tab_state
        if not isinstance(state, _IntruderTabState):
            return
        # Save template text from per-tab editor
        try:
            wid = self._wid(state.tab_id, "template-panel")
            panel = self.query_one(f"#{wid}", ContentPanel)
            w = panel.content_widget
            if isinstance(w, TextArea):
                state.template_text = w.text
        except Exception:
            pass
        self._auto_save_tab(state)

    @on(TabbedContentPanel.TabActivated, "#intruder-tabs")
    def _on_tab_activated(self, event: TabbedContentPanel.TabActivated) -> None:
        """Загрузить состояние нового таба в глобальные виджеты."""
        self._load_tab_into_ui(event.tab_state)

    def _load_tab_into_ui(self, state) -> None:
        """Загрузить состояние таба в глобальные виджеты.

        Вызывается из @on(TabActivated) и вручную из _on_tab_closed (после
        закрытия таба, чтобы синхронизировать UI с новым активным табом).
        """
        if not isinstance(state, _IntruderTabState):
            return
        # Restore grep state
        self._grep_match_patterns = list(state.grep_match_patterns)
        self._grep_extract_patterns = list(state.grep_extract_patterns)
        self._grep_only_match = state.grep_only_match
        # Rebuild results table
        self._rebuild_table_data()
        # Update attack description
        self._update_attack_description()

    @on(TabbedContentPanel.TabCreated, "#intruder-tabs")
    def _on_tab_created(self, event: TabbedContentPanel.TabCreated) -> None:
        """Новый таб создан — синхронизировать UI."""
        self.call_after_refresh(self._load_active_tab_content)

    @on(TabbedContentPanel.TabClosed, "#intruder-tabs")
    def _on_tab_closed(self, event: TabbedContentPanel.TabClosed) -> None:
        """Таб закрыт — загрузить оставшийся."""
        state = self._active_tab
        if state:
            self._load_tab_into_ui(state)

    # ── ContentPanel handlers ─────────────────────────────────────────────────

    @on(ContentPanel.PasteRequested)
    def _on_cp_paste(self, event: ContentPanel.PasteRequested) -> None:
        """Вставка в ContentPanel из буфера обмена."""
        from pentool.utils.copy_as import paste_from_clipboard
        clipboard = paste_from_clipboard()
        if clipboard:
            panel = event.panel
            w = panel.content_widget
            if isinstance(w, TextArea):
                sel = w.selection
                is_selected = (
                    sel is not None
                    and sel.start != sel.end
                )
                if is_selected:
                    start_row, start_col = sel.start
                    end_row, end_col = sel.end
                    lines = w.text.splitlines(keepends=True)
                    if start_row == end_row:
                        line = lines[start_row]
                        lines[start_row] = line[:start_col] + clipboard + line[end_col:]
                    else:
                        lines[start_row] = lines[start_row][:start_col] + clipboard
                        lines = lines[:start_row + 1] + lines[end_row:]
                        if end_row < len(lines):
                            lines[end_row] = lines[end_row][end_col:]
                        else:
                            lines.append('')
                    w.load_text(''.join(lines))
                else:
                    w.load_text(clipboard)
        else:
            self.app.notify("Nothing in clipboard", severity="warning")

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
                except Exception as exc:
                    logger.debug("op: %s", exc)
                return
            self._last_click_time = now
        await super().on_event(event)

    # ── Compose ──────────────────────────────────────────────────────────

    def compose(self) -> ComposeResult:
        # ── Toolbar (глобальный) ─────────────────────────────────────────────
        yield Toolbar(
            ToolbarButton("➕ Tab", "btn-new-tab"),
            Toolbar.sep(),
            ToolbarButton("➖ Tab", "btn-close-tab"),
            Toolbar.sep(),
            StartStopWidget(),
            Toolbar.sep(),
            ToolbarButton("Clear results", "btn-clear-results"),
            Toolbar.sep(),
            ToolbarButton("Export CSV", "btn-export-csv"),
            Toolbar.sep(),
            Label("Attack:", classes="toolbar-label"),
            ToolbarButton("Sniper ▼", "btn-attack-type"),
            Toolbar.sep(),
            ToolbarButton("Add §§",    "btn-add-marker"),
            ToolbarButton("Clear §§",  "btn-clear-markers"),
            Toolbar.sep(),
            ToolbarButton("Auto §§",   "btn-mark-params"),
            Toolbar.sep(),
            Static(
                _ATTACK_DESCRIPTIONS[AttackType.SNIPER],
                id="attack-type-desc",
            ),
            Toolbar.sep(),
            Label("Threads:", classes="toolbar-label"),
            Input("10", id="input-threads", placeholder="10", compact=True, type="integer"),
            Label("Delay(ms):", classes="toolbar-label"),
            Input("0",  id="input-delay",   placeholder="0",  compact=True, type="integer"),
            Toolbar.sep(),
            Checkbox("⚡ Turbo", id="chk-turbo", value=False),
        )

        # ── TabbedContentPanel (строит TabbedContent + per-tab виджеты) ────
        yield TabbedContentPanel[_IntruderTabState](
            id="intruder-tabs",
            tab_id_prefix="intruder-tab-",
            build_tab_ui=self._build_tab_ui,
            save_tab=None,  # используем сообщения TabDeactivated
            load_tabs=None, # используем ручную загрузку через _do_load_tabs_from_db
            rename_input_id="intruder-rename-input",
        )

        # ── Payload buttons toolbar (глобальный) ──────────────────────────
        yield Toolbar(
            Toolbar.sep(),
            Label("Payload set:"),
            ToolbarButton("Set 1 ▼", "btn-payload-set"),
            Toolbar.sep(),
            ToolbarButton("Add",           "btn-payload-add"),
            ToolbarButton("Remove",        "btn-payload-remove"),
            ToolbarButton("Clear",         "btn-payload-clear"),
            ToolbarButton("Load from file…", "btn-payload-load"),
            ToolbarButton("Generate…",     "btn-payload-generate"),
            ToolbarButton("🧠 Smart…",     "btn-payload-smart", classes="pro-locked"),
            id="payload-buttons-toolbar",
        )

        # ── Results + progress (глобальные) ─────────────────────────────────
        with Vertical(id="results-area"):
            with Horizontal(id="progress-row"):
                yield ProgressBar(total=100, id="attack-progress", show_eta=False)
                yield Static("0/0 (0%)", id="progress-label")

            yield DataTable(
                id="results-table",
                columns=_RESULTS_COL_NAMES,
                column_widths=[5, 45, 8, 10, 10, 30],
                cursor_type="row",
                zebra_stripes=True,
                max_column_content_width=120,
            )

        yield _IntruderFilterBar(id="intruder-filter-bar")

        with Horizontal(id="intruder-detail-panel", classes="intruder-detail-panel"):
            with Vertical(id="detail-request-col", classes="detail-col"):
                yield HttpView("Request", id="detail-request", classes="detail-view")
            yield ResizeHandle("detail-request-col", "detail-response-col")
            with Vertical(id="detail-response-col", classes="detail-col"):
                yield HttpView("Response", id="detail-response", classes="detail-view")

    # ── Tab lifecycle (action_*) — делегируют в TabbedContentPanel ─────

    def action_new_tab(self) -> None:
        """Создать новый таб с дефолтным состоянием."""
        self._tab_counter_adjust()
        tab_id = self._tc_panel.action_new_tab()
        self.call_after_refresh(self._load_active_tab_content)

    def _tab_counter_adjust(self) -> None:
        """Подстроить _tab_counter под TabbedContentPanel (для совместимости тестов)."""
        # TabbedContentPanel сам управляет счётчиком

    def action_close_tab(self) -> None:
        self._tc_panel.action_close_tab()

    def _load_active_tab_content(self) -> None:
        """Подгрузить данные активного таба в глобальные виджеты.

        Вызывается после создания/переключения таба.
        """
        tab = self._active_tab
        if tab is None:
            return
        # 1. Restore grep
        self._grep_match_patterns = list(tab.grep_match_patterns)
        self._grep_extract_patterns = list(tab.grep_extract_patterns)
        self._grep_only_match = tab.grep_only_match
        # 2. Rebuild results
        self._rebuild_table_data()
        # 3. Attack description
        self._update_attack_description()

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
            pass
        self._auto_save_tab(tab)

    # ── DB persistence ────────────────────────────────────────────────────────

    def _get_db_path(self) -> str | None:
        return getattr(self.app, "db_path", None) or getattr(self.app, "_db_path", "")

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
        except Exception as exc:
            logger.debug("_auto_save_tab: %s", exc)

    def _load_tabs_from_db(self) -> None:
        """Load saved tabs from database and restore them."""
        if self._api is None:
            return
        self.run_worker(
            self._do_load_tabs_from_db(self._api),
            exclusive=False, exit_on_error=False,
        )

    async def _do_load_tabs_from_db(self, api: "IntruderAPI") -> None:
        """Async: load tabs from DB and create TabPane widgets."""
        try:
            tabs_data = await api.get_tabs()
        except Exception as exc:
            logger.debug("_do_load_tabs_from_db: get_tabs: %s", exc)
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

            # Create state
            tab_id = f"intruder-tab-{self._counter_gen()}"
            name = td.get("name", f"Tab {self._counter_gen()}")
            state = _IntruderTabState(
                tab_id=tab_id,
                tab_uid=tab_uid,
                name=name,
                target_url=td.get("target_url", ""),
                template_text=td.get("template", ""),
            )
            at_str = td.get("attack_type", "sniper")
            try:
                state.attack_type = AttackType(at_str)
            except Exception:
                state.attack_type = AttackType.SNIPER
            payloads_raw = td.get("payloads", [[]])
            if payloads_raw and isinstance(payloads_raw, list):
                state.payload_sources = deserialize_payloads(payloads_raw)

            # Add tab via TabbedContentPanel
            self._tc_panel.action_new_tab(state=state)

    def _counter_gen(self) -> int:
        """Подстроиться под счётчик TabbedContentPanel."""
        return 0  # TabbedContentPanel генерирует tab_id сам

    # ── Rename (BaseModuleScreen interface) ───────────────────────────────────

    def _start_rename(self, tab_id: str) -> None:
        """Делегировать в TabbedContentPanel (уже сделано в _start_rename таб-панели,
        но BaseModuleScreen.on_click вызывает сюда)."""
        state = None
        for t in self._tc_panel.all_states:
            if getattr(t, "tab_id", None) == tab_id:
                state = t
                break
        if state is None:
            return
        try:
            inp = Input(id=self._rename_input_id, placeholder="Tab name...", compact=True)
            inp.value = getattr(state, "name", "Tab")
            inp.display = True
            self.query_one("#intruder-tabs", TabbedContentPanel).parent.mount(inp)
            inp.focus()
            inp.action_select_all()
            inp._rename_tab_id = tab_id
        except Exception:
            pass

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

    def on_mount(self) -> None:
        # Create the first tab via TabbedContentPanel
        tc = self._tc_panel
        tc.set_default_state_factory(self._tab_factory)
        tc.action_new_tab()
        # Reset StartStopWidget on mount
        try:
            self._ssw.set_running(False)
        except Exception:
            pass
        self._setup_tooltips()
        self._load_state_from_db()
        self._apply_license_limits()
        self._init_ai_sync()

    def on_show(self) -> None:
        self._rebuild_table_data()
        self._sync_ai_ui()

    # ── AI sync ──────────────────────────────────────────────────────────

    def _init_ai_sync(self) -> None:
        from pentool.core.event_bus import get_event_bus
        from pentool.core.events import AiModeChanged
        def _on_ai_mode(event: AiModeChanged) -> None:
            self._sync_ai_ui()
        get_event_bus().subscribe(AiModeChanged, _on_ai_mode)
        self._sync_ai_ui()

    def _sync_ai_ui(self) -> None:
        try:
            from pentool.core.config import get_config
            ai_on = bool(get_config().ai_enabled)
            btn = self.query_one("#btn-payload-smart", ToolbarButton)
            btn.display = ai_on
        except Exception as exc:
            logger.debug("op: %s", exc)

    def _update_attack_description(self) -> None:
        try:
            tab = self._active_tab
            if tab:
                desc = _ATTACK_DESCRIPTIONS.get(tab.attack_type, "")
                self.query_one("#attack-type-desc", Static).update(desc)
        except Exception as exc:
            logger.debug("_update_attack_description: %s", exc)

    def _setup_tooltips(self) -> None:
        tips = {
            "btn-start":         "Start attack (Ctrl+Enter)",
            "btn-pause":         "Pause / Resume attack (Ctrl+P)",
            "btn-stop":          "Stop attack",
            "btn-add-marker":    "Wrap selected text in §markers§",
            "btn-clear-markers": "Remove all §markers§ from template",
            "btn-payload-add":   "Add new payload manually",
            "btn-payload-load":  "Load payloads from file",
        }
        for btn_id, tip in tips.items():
            try:
                self.query_one(f"#{btn_id}", ToolbarButton).tooltip = tip
            except Exception as exc:
                logger.debug("op: %s", exc)

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
        except Exception as exc:
            logger.debug("op: %s", exc)

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
        """Загрузить результаты из SQL с учётом FilterSpec и ORDER BY."""
        try:
            sql_predicates: list[FilterPredicate] = []
            if self._filter_spec and not self._filter_spec.is_empty:
                for p in self._filter_spec.predicates:
                    if p.field in ("status", "length"):
                        db_field = "response_status" if p.field == "status" else "response_length"
                        sql_predicates.append(FilterPredicate(db_field, p.operator, p.value))
            sql_filter = FilterSpec(predicates=sql_predicates) if sql_predicates else None
            results = await api.get_results_from_db(
                limit=100000, filters=sql_filter,
                order_by=order_by, desc=(order_dir == "desc"),
            )
        except Exception as exc:
            logger.debug("_do_load_results: %s", exc)
            return
        if not results:
            self._all_results = []
            self._filtered_results = []
            self._redraw_results()
            return
        if order_by:
            self._all_results = list(results)
        else:
            self._all_results = list(reversed(results))
        self._filtered_results = list(self._all_results)
        self._redraw_results()

    def _load_state_from_db(self) -> None:
        api = self._get_api()
        if api is None:
            return
        self.run_worker(self._do_load_state(api), exclusive=False, exit_on_error=False)

    def _apply_license_limits(self) -> None:
        from pentool.core.license import get_session_license
        license_info = get_session_license()
        is_pro = license_info.is_pro() if license_info else False
        try:
            threads_input = self.query_one("#input-threads", Input)
            delay_input = self.query_one("#input-delay", Input)
            turbo_checkbox = self.query_one("#chk-turbo", Checkbox)
            if not is_pro:
                threads_input.placeholder = "Max 5"
                delay_input.placeholder = "Min 100"
                turbo_checkbox.disabled = True
                turbo_checkbox.tooltip = "⚡ Turbo mode requires PRO license"
            else:
                threads_input.placeholder = "Max 200"
                delay_input.placeholder = "0"
                turbo_checkbox.disabled = False
                turbo_checkbox.tooltip = "⚡ Turbo: HTTP pipelining, connection pooling"
        except Exception as exc:
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
                    pass
            attack_type_str = state.get("attack_type", "sniper")
            try:
                self._attack_type = AttackType(attack_type_str)
                btn = self.query_one("#btn-attack-type", ToolbarButton)
                btn.label = f"⚡ {self._attack_type.value.replace('_', ' ').title()}"
            except Exception as exc:
                logger.debug("op: %s", exc)
            payloads = state.get("payloads", [[]])
            if payloads and isinstance(payloads, list):
                self._payloads = deserialize_payloads(payloads)
                self._update_payload_select()
                self.call_after_refresh(self._refresh_payload_list)
            self._state_loaded = True
        except Exception as exc:
            logger.debug("_do_load_state: %s", exc)

    def _auto_save_state(self) -> None:
        api = self._get_api()
        if api is None:
            return
        try:
            tab = self._active_tab
            if tab is None:
                return
            # Читаем template из per-tab editor
            template = ""
            try:
                editor = self._template_editor()
                w = editor.content_widget
                if isinstance(w, TextArea):
                    template = w.text
            except Exception:
                template = tab.template_text
            worker_name = f"intruder-save-state-{time.monotonic_ns()}"
            self._running_save_tasks.append(worker_name)
            self.run_worker(
                self._do_auto_save(
                    api.save_state(
                        tab_name=tab.name,
                        template=template,
                        attack_type=self._attack_type.value,
                        payloads=serialize_payloads(self._payloads),
                        tab_uid=tab.tab_uid,
                    ),
                    worker_name,
                ),
                exclusive=False, exit_on_error=False,
            )
        except Exception as exc:
            logger.debug("op: %s", exc)

    def _auto_save_result(self, result: IntruderResult) -> None:
        api = self._get_api()
        if api is None:
            return
        try:
            project_id = getattr(self.app, "project_id", None)
            worker_name = f"intruder-save-result-{time.monotonic_ns()}"
            self._running_save_tasks.append(worker_name)
            self.run_worker(
                self._do_auto_save(
                    api.save_result(result, project_id=project_id),
                    worker_name,
                ),
                exclusive=False, exit_on_error=False,
            )
        except Exception as exc:
            logger.debug("op: %s", exc)

    # ── @on handlers for global buttons ─────────────────────────────────

    @on(ToolbarButton.Pressed, "#btn-clear-results")
    def on_btn_clear_results(self, _: ToolbarButton.Pressed) -> None:
        self._clear_results()

    @on(ToolbarButton.Pressed, "#btn-export-csv")
    def on_btn_export_csv(self, _: ToolbarButton.Pressed) -> None:
        self._export_csv()

    @on(ToolbarButton.Pressed, "#btn-new-tab")
    def on_btn_new_tab(self, _: ToolbarButton.Pressed) -> None:
        self.action_new_tab()

    @on(ToolbarButton.Pressed, "#btn-close-tab")
    def on_btn_close_tab(self, _: ToolbarButton.Pressed) -> None:
        self.action_close_tab()

    @on(ToolbarButton.Pressed, "#btn-add-marker")
    def on_btn_add_marker(self, _: ToolbarButton.Pressed) -> None:
        self._add_marker_around_selection()

    @on(ToolbarButton.Pressed, "#btn-clear-markers")
    def on_btn_clear_markers(self, _: ToolbarButton.Pressed) -> None:
        self._clear_markers()

    @on(ToolbarButton.Pressed, "#btn-mark-params")
    def on_btn_mark_params(self, _: ToolbarButton.Pressed) -> None:
        self._prompt_auto_mark()

    @on(ToolbarButton.Pressed, "#btn-attack-type")
    def on_btn_attack_type(self, event: ToolbarButton.Pressed) -> None:
        self._open_attack_type_menu(event.button)

    @on(ToolbarButton.Pressed, "#btn-payload-set")
    def on_btn_payload_set(self, event: ToolbarButton.Pressed) -> None:
        self._open_payload_set_menu(event.button)

    @on(ToolbarButton.Pressed, "#btn-payload-add")
    def on_btn_payload_add(self, _: ToolbarButton.Pressed) -> None:
        self._add_payload_manual()

    @on(ToolbarButton.Pressed, "#btn-payload-remove")
    def on_btn_payload_remove(self, _: ToolbarButton.Pressed) -> None:
        self._remove_selected_payload()

    @on(ToolbarButton.Pressed, "#btn-payload-clear")
    def on_btn_payload_clear(self, _: ToolbarButton.Pressed) -> None:
        self._clear_payloads()

    @on(ToolbarButton.Pressed, "#btn-payload-load")
    def on_btn_payload_load(self, _: ToolbarButton.Pressed) -> None:
        self._load_payloads_from_file()

    @on(ToolbarButton.Pressed, "#btn-payload-generate")
    def on_btn_payload_generate(self, _: ToolbarButton.Pressed) -> None:
        self._open_generate_dialog()

    @on(ToolbarButton.Pressed, "#btn-payload-smart")
    def on_btn_payload_smart(self, _: ToolbarButton.Pressed) -> None:
        self._open_smart_payloads_dialog()

    # ── TextArea handlers ───────────────────────────────────────────────

    @on(TextArea.SelectionChanged)
    def on_template_selection_changed(self, event: TextArea.SelectionChanged) -> None:
        """Remember the selection in template-editor."""
        try:
            our_editor = self._template_editor()
            if event.widget is not our_editor.content_widget:
                return
        except Exception:
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
            if event.widget is not our_editor.content_widget:
                return
        except Exception:
            return
        self._update_payload_select()
        if self._state_loaded:
            self._auto_save_state()

    # ── Filter bar handlers ──────────────────────────────────────────────

    @on(_IntruderFilterBar.FilterChanged)
    def on_intruder_filter_bar_changed(self, event: _IntruderFilterBar.FilterChanged) -> None:
        spec = event.spec
        filter_predicates: list[FilterPredicate] = []
        self._grep_match_patterns = []
        self._grep_extract_patterns = []
        self._grep_only_match = False
        had_extract = bool(self._grep_extract_patterns)
        if spec and not spec.is_empty:
            for p in spec.predicates:
                match p.field:
                    case "grep_match":
                        self._grep_match_patterns = [str(p.value)]
                    case "grep_extract":
                        self._grep_extract_patterns = [str(p.value)]
                    case "grep_only_match":
                        self._grep_only_match = bool(p.value)
                    case _:
                        filter_predicates.append(p)
        self._filter_spec = FilterSpec(predicates=filter_predicates) if filter_predicates else None
        logger.info(
            "INTRUDER: filter applied — predicates=%d match=%d extract=%d only_match=%s",
            len(filter_predicates), len(self._grep_match_patterns),
            len(self._grep_extract_patterns), self._grep_only_match,
        )
        has_extract = bool(self._grep_extract_patterns)
        if has_extract != had_extract:
            try:
                table = self._results_table()
                if has_extract:
                    table.add_column("Extract")
                else:
                    table.remove_column("Extract")
            except Exception as exc:
                logger.debug("op: %s", exc)
        if not self._ssw.running:
            api = self._get_api()
            if api:
                self.run_worker(self._do_load_results(api), exclusive=False, exit_on_error=False)
            else:
                self._redraw_results()
        else:
            self._redraw_results()

    # ── Attack type menu ────────────────────────────────────────────────

    def _open_attack_type_menu(self, btn: ToolbarButton) -> None:
        items = [
            (at.value, ("✓ " if at == self._attack_type else "  ") + label)
            for at, label in _ATTACK_LABELS.items()
        ]
        r = btn.region
        x = r.x
        y = r.y + 1
        screen = self

        def _on_select(action: str) -> None:
            try:
                at = AttackType(action)
                screen._attack_type = at
                new_label = f"{_ATTACK_LABELS[at]} ▼"
                try:
                    b = screen.query_one("#btn-attack-type", ToolbarButton)
                    b.label = new_label
                except Exception as e:
                    logger.warning("attack-type btn update failed: %s", e)
                desc = _ATTACK_DESCRIPTIONS.get(at, "")
                try:
                    screen.query_one("#attack-type-desc", Static).update(desc)
                except Exception as exc:
                    logger.debug("op: %s", exc)
                screen._update_payload_select()
                screen._auto_save_state()
            except Exception as e:
                logger.warning("_on_select attack type failed: %s", e)

        self.app.show_context_menu(items, x, y, callback=_on_select)

    def _open_payload_set_menu(self, btn: ToolbarButton) -> None:
        n = len(self._payloads) or 1
        items = [
            (str(i), ("✓ " if i == self._active_set_idx else "  ") + f"Set {i+1}")
            for i in range(n)
        ]
        r = btn.region
        x = r.x
        y = r.y + 1

        def _on_select(action: str) -> None:
            try:
                idx = int(action)
                self._active_set_idx = idx
                label = f"Set {idx+1} ▼" if n <= 1 else f"Set {idx+1}/{n} ▼"
                self.query_one("#btn-payload-set", ToolbarButton).label = label
                self._refresh_payload_list()
                self._highlight_nth_marker(idx)
            except Exception as exc:
                logger.debug("op: %s", exc)

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
                except Exception as exc:
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
        # Полная копия из оригинального файла (все методы маркировки)
        # ... (сохранён оригинальный метод)
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
        if (options is None or options.get("body_form", True)) and "urlencoded" in content_type and body_lines_start is not None:
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
            except (_json.JSONDecodeError, Exception):
                pass
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
                    new_lines = lines[:body_lines_start] + [l for l in marked_xml.split("\n") if l.strip()]
                    lines = new_lines
                except (ET.ParseError, Exception):
                    pass
        new_text = "\n".join(lines)
        try:
            w.load_text(new_text)
            self._update_payload_select()
            n = new_text.count("§") // 2
            self.app.notify(f"Marked {n} parameter(s)", timeout=2)
            if n > 1 and self._attack_type == AttackType.SNIPER:
                self._attack_type = AttackType.BATTERING_RAM
                try:
                    btn = self.query_one("#btn-attack-type", ToolbarButton)
                    btn.label = f"{_ATTACK_LABELS[AttackType.BATTERING_RAM]} ▼"
                    self.query_one("#attack-type-desc", Static).update(
                        _ATTACK_DESCRIPTIONS[AttackType.BATTERING_RAM]
                    )
                except Exception as exc:
                    logger.debug("op: %s", exc)
                self.app.notify(
                    f"Marked {n} positions — switched to Battering Ram "
                    "(Sniper only fills one position per request; change "
                    "back via the attack-type menu if you really want Sniper)",
                    severity="warning", timeout=6,
                )
                self._auto_save_state()
            self._highlight_nth_marker(self._active_set_idx)
        except Exception as exc:
            logger.debug("op: %s", exc)

    # ── Payload list management ──────────────────────────────────────────

    def _update_payload_select(self) -> None:
        tab = self._active_tab
        if tab is None:
            return
        try:
            editor = self._template_editor()
            w = editor.content_widget
            template = w.text if isinstance(w, TextArea) else ""
        except Exception:
            template = ""
        if self._attack_type in (AttackType.SNIPER, AttackType.BATTERING_RAM):
            n = 1
        else:
            n = max(1, count_markers(template))
        while len(self._payloads) < n:
            self._payloads.append([])
        idx = min(self._active_set_idx, n - 1)
        self._active_set_idx = idx
        try:
            label = f"Set {idx+1} ▼" if n <= 1 else f"Set {idx+1}/{n} ▼"
            self.query_one("#btn-payload-set", ToolbarButton).label = label
        except Exception as exc:
            logger.debug("op: %s", exc)
        self._refresh_payload_list()

    def _tab_id_for_widget(self) -> str | None:
        t = self._active_tab
        return t.tab_id if t else None

    def _refresh_payload_list(self) -> None:
        tab_id = self._tab_id_for_widget()
        if tab_id is None:
            return
        try:
            lv = self.query_one(f"#{self._wid(tab_id, 'payload-list')}", ListView)
            lv.clear()
            active = (
                self._payloads[self._active_set_idx]
                if self._active_set_idx < len(self._payloads)
                else []
            )
            if isinstance(active, FilePayloadSource):
                preview = active.head(_PAYLOAD_LIST_PREVIEW_LIMIT)
                for p in preview:
                    lv.append(ListItem(Label(p)))
                if active.is_count_known and active.cached_count > len(preview):
                    lv.append(ListItem(Label(
                        f"… {active.cached_count - len(preview)} more line(s) "
                        f"not shown (file: {Path(active.path).name})"
                    )))
                elif not active.is_count_known:
                    lv.append(ListItem(Label("(counting lines…)")))
            elif isinstance(active, (NumericPayloadSource, CharPayloadSource, ChainedPayloadSource)):
                total = len(active)
                preview = active.head(_PAYLOAD_LIST_PREVIEW_LIMIT)
                for p in preview:
                    lv.append(ListItem(Label(p)))
                if total > len(preview):
                    lv.append(ListItem(Label(
                        f"… {total - len(preview):,} more value(s) not shown"
                    )))
            else:
                for p in active:
                    lv.append(ListItem(Label(p)))
            self._update_payload_count_label()
        except Exception as exc:
            logger.debug("op: %s", exc)

    def _update_payload_count_label(self) -> None:
        tab_id = self._tab_id_for_widget()
        if tab_id is None:
            return
        try:
            label = self.query_one(f"#{self._wid(tab_id, 'payload-count-label')}", Static)
        except Exception:
            return
        active = (
            self._payloads[self._active_set_idx]
            if self._active_set_idx < len(self._payloads)
            else []
        )
        if isinstance(active, FilePayloadSource):
            if active.is_count_known:
                label.update(f"[dim]{active.cached_count:,} line(s) — {Path(active.path).name}[/dim]")
            else:
                label.update(f"[dim]counting… — {Path(active.path).name}[/dim]")
        elif isinstance(active, (NumericPayloadSource, CharPayloadSource, ChainedPayloadSource)):
            n = len(active)
            label.update(f"[dim]{n:,} value(s)[/dim]" if n else "")
        else:
            n = len(active)
            label.update(f"[dim]{n:,} line(s)[/dim]" if n else "")

    def _highlight_nth_marker(self, n: int) -> None:
        try:
            from textual.widgets.text_area import Selection
            editor = self._template_editor()
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
        if self._active_set_idx < len(self._payloads) and isinstance(
            self._payloads[self._active_set_idx], _LAZY_SOURCE_TYPES
        ):
            self.app.notify(
                "This set is generated/loaded from a file — click Clear first "
                "to switch it to a manually-edited list.",
                severity="warning", timeout=4,
            )
            return

        def _on_add(value: str) -> None:
            while self._active_set_idx >= len(self._payloads):
                self._payloads.append([])
            self._payloads[self._active_set_idx].append(value)
            self._refresh_payload_list()
            self._auto_save_state()

        self.app.push_screen(InputDialog("Add payload", "Enter payload value:", on_add=_on_add))

    def _remove_selected_payload(self) -> None:
        if self._active_set_idx < len(self._payloads) and isinstance(
            self._payloads[self._active_set_idx], _LAZY_SOURCE_TYPES
        ):
            self.app.notify(
                "This set is generated/loaded from a file — individual lines "
                "can't be removed. Click Clear to remove the whole set.",
                severity="warning", timeout=4,
            )
            return
        try:
            lv = self.query_one("#payload-list", ListView)
            idx = lv.index
            if idx is not None and self._active_set_idx < len(self._payloads):
                payloads = self._payloads[self._active_set_idx]
                if 0 <= idx < len(payloads):
                    payloads.pop(idx)
                    self._refresh_payload_list()
                    self._auto_save_state()
        except Exception as exc:
            logger.debug("op: %s", exc)

    def _clear_payloads(self) -> None:
        if self._active_set_idx < len(self._payloads):
            self._payloads[self._active_set_idx] = []
            self._refresh_payload_list()
            self._auto_save_state()

    _EAGER_LOAD_MAX_BYTES = 20 * 1024 * 1024

    def _load_payloads_from_file(self) -> None:
        if self._payload_load_in_progress:
            self.app.notify("A payload file is already loading — please wait", severity="warning", timeout=3)
            return
        from pentool.tui.dialogs.file_selector import FileSelectorDialog, FileSelectorMode
        captured_idx = self._active_set_idx

        def _on_file(path: str | None) -> None:
            if path:
                self.run_worker(
                    self._load_file_async(path, captured_idx),
                    exclusive=False, name="payload-load", exit_on_error=False,
                )

        self.app.push_screen(
            FileSelectorDialog(mode=FileSelectorMode.OPEN, filter_ext=["*.txt", "*.yaml", "*.yml"], title="Select payload file"),
            _on_file,
        )

    async def _load_file_async(self, path: str, target_idx: int) -> None:
        try:
            size = await asyncio.get_running_loop().run_in_executor(
                None, lambda: Path(path).stat().st_size
            )
        except Exception as exc:
            from pentool.core.error_guard import err
            err(exc, "Failed to load payload file", self, severity="error")
            return
        while target_idx >= len(self._payloads):
            self._payloads.append([])
        if size <= self._EAGER_LOAD_MAX_BYTES:
            await self._load_file_eager(path, target_idx)
        else:
            await self._load_file_streamed(path, target_idx, size)

    async def _load_file_eager(self, path: str, target_idx: int) -> None:
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
        existing = self._payloads[target_idx]
        if isinstance(existing, _LAZY_SOURCE_TYPES):
            self._payloads[target_idx] = payloads
        else:
            existing.extend(payloads)
        if target_idx == self._active_set_idx:
            self._refresh_payload_list()
        name = Path(path).name
        self.app.notify(f"Loaded {len(payloads)} payloads from {name}", timeout=3)
        self._auto_save_state()

    async def _load_file_streamed(self, path: str, target_idx: int, size_bytes: int) -> None:
        self._payload_load_in_progress = True
        source = FilePayloadSource(path)
        self._payloads[target_idx] = source
        if target_idx == self._active_set_idx:
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
            final_count = await loop.run_in_executor(
                None, count_lines_with_progress, path, "utf-8", _on_progress
            )
            source.set_count(final_count)
        except Exception as exc:
            from pentool.core.error_guard import err
            err(exc, "Payload line count failed (still usable)", self, severity="warning")
        finally:
            self._payload_load_in_progress = False
            if target_idx == self._active_set_idx:
                self._update_payload_count_label()
            self._auto_save_state()

    def _on_payload_count_progress(self, target_idx: int, count: int, bytes_read: int, total_bytes: int) -> None:
        active = (
            self._payloads[target_idx]
            if target_idx < len(self._payloads)
            else None
        )
        if not isinstance(active, FilePayloadSource):
            return
        tab_id = self._tab_id_for_widget()
        if tab_id is None:
            return
        try:
            label = self.query_one(f"#{self._wid(tab_id, 'payload-count-label')}", Static)
            pct = f" ({bytes_read / total_bytes * 100:.0f}%)" if total_bytes else ""
            if target_idx == self._active_set_idx:
                label.update(f"[dim]{count:,} line(s) counted so far{pct}…[/dim]")
        except Exception as exc:
            logger.debug("op: %s", exc)

    @staticmethod
    def _read_file_sync(path: str) -> str:
        return Path(path).read_text(encoding="utf-8", errors="replace")

    def _append_to_active_set(self, new_source) -> int:
        while self._active_set_idx >= len(self._payloads):
            self._payloads.append([])
        existing = self._payloads[self._active_set_idx]
        added = len(new_source)
        if isinstance(existing, list) and isinstance(new_source, list):
            existing.extend(new_source)
        elif isinstance(existing, list) and not existing:
            self._payloads[self._active_set_idx] = new_source
        else:
            self._payloads[self._active_set_idx] = ChainedPayloadSource(existing, new_source)
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
                severity="warning", timeout=4,
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
        logger.info("INTRUDER: action_start_attack called, running=%s", self._ssw.running)
        if self._ssw.running:
            return
        if self._payload_load_in_progress:
            self.app.notify(
                "A payload file is still being counted — wait for it to finish before starting",
                severity="warning", timeout=4,
            )
            return
        try:
            editor = self._template_editor()
            w = editor.content_widget
            template = w.text if isinstance(w, TextArea) else ""
            logger.info("INTRUDER: template len=%d", len(template))
        except Exception as e:
            logger.error("INTRUDER: cannot get template: %s", e)
            return
        if not template.strip():
            self.app.notify("Template is empty", severity="warning", timeout=3)
            return
        if count_markers(template) == 0:
            self.app.notify(
                "No §§ markers in template — use Auto §§ or Add §§ to mark positions first",
                severity="warning", timeout=5,
            )
            return
        logger.info("INTRUDER: action_start: attack_type=%s", self._attack_type)

        processing_ops = self._get_processing_ops()
        payload_sets = []
        for ps in self._payloads:
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
            threads = int(self.query_one("#input-threads", Input).value or "10")
            if not is_pro:
                threads = max(1, min(threads, 5))
            else:
                threads = max(1, min(threads, 200))
        except Exception:
            threads = 5 if not is_pro else 10

        try:
            delay_ms = int(self.query_one("#input-delay", Input).value or "0")
            if not is_pro:
                delay_ms = max(100, delay_ms)
            else:
                delay_ms = max(0, delay_ms)
        except Exception:
            delay_ms = 100 if not is_pro else 0

        config = IntruderConfig(
            template=template,
            attack_type=self._attack_type,
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

        turbo_mode = False
        try:
            if is_pro:
                turbo_mode = self.query_one("#chk-turbo", Checkbox).value
            else:
                self.query_one("#chk-turbo", Checkbox).value = False
        except Exception as exc:
            logger.debug("op: %s", exc)

        self._ssw.set_running(True)
        self._all_results = []
        self._clear_results()

        total_payloads = sum(len(ps) for ps in payload_sets)
        mode_label = " [⚡ Turbo]" if turbo_mode else ""
        limit_label = "" if is_pro else " [FREE: limited]"
        self.app.notify(
            f"Attack started: {total_payloads} payload(s){mode_label}{limit_label}",
            severity="success", title="Intruder",
        )
        self.run_worker(self._run_attack(config, turbo_mode=turbo_mode), exclusive=False, name="intruder-attack")

    async def _run_attack(self, config: IntruderConfig, turbo_mode: bool = False) -> None:
        logger.info("INTRUDER: _run_attack started, type=%s, turbo=%s", config.attack_type, turbo_mode)

        def on_result(result: IntruderResult) -> None:
            self.call_after_refresh(self._on_result, result)

        def on_progress(done: int, total: int) -> None:
            self.call_after_refresh(self._on_progress, done, total)

        try:
            await self._api.start_attack(config, on_result, on_progress, turbo_mode=turbo_mode)
        except Exception as exc:
            from pentool.core.error_guard import err
            err(exc, "Intruder attack error", self, severity="error")
        finally:
            logger.info("INTRUDER: _run_attack finished, results=%d", len(self._all_results))
            self._ssw.set_running(False)
            self.app.notify(
                f"Attack finished: {len(self._all_results)} requests",
                severity="information", timeout=4,
            )

    def _on_result(self, result: IntruderResult) -> None:
        self._all_results.append(result)
        row_dict = {
            "status": str(result.response_status),
            "length": result.response_length or 0,
            "payload": " ".join(result.payload_values),
        }
        passes = True
        if self._filter_spec and not self._filter_spec.is_empty:
            passes = self._filter_spec.apply([row_dict]) == [row_dict]
        if passes and self._grep_only_match and self._grep_match_patterns:
            text = f"{result.response_status} {result.response_length} {' '.join(result.payload_values)}"
            import re
            passes = any(re.search(pat, text, re.IGNORECASE) for pat in self._grep_match_patterns)
        if passes:
            self._filtered_results.append(result)
            self._add_result_row(result)
        self._auto_save_result(result)

    def _on_progress(self, done: int, total: int) -> None:
        try:
            pb = self.query_one("#attack-progress", ProgressBar)
            if done == 0:
                pb.update(total=max(1, total), progress=0)
            else:
                pb.advance(done - pb.progress)
        except Exception as exc:
            logger.debug("op: %s", exc)
        try:
            pct = f"{done / total * 100:.1f}%" if total > 0 else "0%"
            self.query_one("#progress-label", Static).update(f"{done}/{total} ({pct})")
        except Exception as exc:
            logger.debug("op: %s", exc)

    def action_toggle_pause(self) -> None:
        if not self._ssw.running or self._api is None:
            return
        should_pause = not self._ssw.paused
        if should_pause:
            self.run_worker(self._api.pause(), exit_on_error=False)
        else:
            self.run_worker(self._api.resume(), exit_on_error=False)
        self._ssw.set_paused(should_pause)
        self.app.notify("Paused" if should_pause else "Resumed", timeout=2)

    def action_resume(self) -> None:
        logger.info("INTRUDER: action_resume called, running=%s paused=%s", self._ssw.running, self._ssw.paused)
        self._ssw.set_paused(False)
        self.action_start_attack()

    def action_stop(self) -> None:
        if self._api is not None:
            self.run_worker(self._api.stop(), exit_on_error=False)
        self._ssw.set_running(False)
        self.app.notify("Attack stopped", severity="warning")

    def on_worker_state_changed(self, event) -> None:
        from textual.worker import WorkerState
        if getattr(event.worker, "name", None) != "intruder-attack":
            return
        if event.state in (WorkerState.SUCCESS, WorkerState.CANCELLED, WorkerState.ERROR):
            if self._ssw.running:
                if self._ssw.paused:
                    logger.info("INTRUDER: worker finished while paused — keeping paused state")
                else:
                    logger.info("INTRUDER: on_worker_state_changed — resetting running=False")
                    self._ssw.set_running(False)

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

    def _add_result_row(self, result: IntruderResult) -> None:
        try:
            row = self._row_from_result(result)
            if self._grep_extract_patterns:
                extract_val = ""
                resp_body = getattr(result, "request_raw", "") or ""
                for pat in self._grep_extract_patterns:
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
        try:
            table = self._results_table()
            if table is None:
                return
            table.clear_data()
        except Exception as exc:
            logger.debug("_clear_results: %s", exc)
        self._all_results = []
        self._filtered_results = []
        try:
            self.query_one("#progress-label", Static).update("0/0 (0%)")
            self.query_one("#attack-progress", ProgressBar).update(total=100)
        except Exception as exc:
            logger.debug("op: %s", exc)

    def _results_table(self) -> DataTable | None:
        try:
            return self.query_one("#results-table", DataTable)
        except Exception:
            return None

    def _rebuild_table_data(self) -> None:
        table = self._results_table()
        if table is None:
            return
        try:
            if not self._filtered_results:
                if self._all_results:
                    self._apply_and_display(self._all_results, table)
                else:
                    table.clear_data()
                return
            display_rows = []
            for r in self._filtered_results:
                row = self._row_from_result(r)
                if self._grep_extract_patterns:
                    extract_val = self._extract_grep_value(r, self._grep_extract_patterns)
                    row.append(extract_val)
                display_rows.append(row)
            import pyarrow as pa
            cols = _RESULTS_COL_NAMES
            if self._grep_extract_patterns:
                cols = cols + ["Extract"]
            data = {c: pa.array([row[i] for row in display_rows], type=pa.string()) for i, c in enumerate(cols)}
            arrow = pa.table(data)
            table.set_data(arrow)
        except Exception as exc:
            logger.error("_rebuild_table_data failed: %s", exc)

    def _apply_and_display(self, results: list[IntruderResult], table: DataTable) -> None:
        filtered = []
        for r in results:
            row_dict = {
                "status": str(r.response_status),
                "length": r.response_length or 0,
                "payload": " ".join(r.payload_values),
            }
            passes = True
            if self._filter_spec and not self._filter_spec.is_empty:
                passes = self._filter_spec.apply([row_dict]) == [row_dict]
            if passes and self._grep_only_match and self._grep_match_patterns:
                text = f"{r.response_status} {r.response_length} {' '.join(r.payload_values)}"
                import re
                passes = any(re.search(pat, text, re.IGNORECASE) for pat in self._grep_match_patterns)
            if passes:
                filtered.append(r)
        self._filtered_results = filtered
        if not filtered:
            table.clear_data()
            return
        display_rows = []
        for r in filtered:
            row = self._row_from_result(r)
            if self._grep_extract_patterns:
                extract_val = self._extract_grep_value(r, self._grep_extract_patterns)
                row.append(extract_val)
            display_rows.append(row)
        import pyarrow as pa
        cols = _RESULTS_COL_NAMES
        if self._grep_extract_patterns:
            cols = cols + ["Extract"]
        data = {c: pa.array([row[i] for row in display_rows], type=pa.string()) for i, c in enumerate(cols)}
        arrow = pa.table(data)
        table.set_data(arrow)

    @staticmethod
    def _extract_grep_value(result: IntruderResult, patterns: list[str] | None = None) -> str:
        import re
        for pat in (patterns or []):
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
        try:
            from textual.coordinate import Coordinate
            coord = Coordinate(row_index, 0)
            cell = table.get_cell_at(coord)
            row_number = int(str(cell))
        except (ValueError, TypeError, IndexError):
            row_number = -1
        if row_number >= 0:
            for r in self._filtered_results:
                if r.request_number == row_number:
                    return r
        if 0 <= row_index < len(self._filtered_results):
            return self._filtered_results[row_index]
        return None

    def on_data_table_header_selected(self, event: DataTable.HeaderSelected) -> None:
        if event.data_table.id != "results-table":
            return
        self._sort_table_sql(
            event, _RESULTS_COL_NAMES,
            order_by_map={
                "#": "request_number",
                "Payload(s)": "payload_values",
                "Status": "response_status",
                "Length": "response_length",
                "Time(ms)": "response_time_ms",
                "Error": "error",
            },
            reload_cb=lambda order_by, order_dir: self._do_load_results(
                self._get_api(), order_by=order_by, order_dir=order_dir
            ) if self._get_api() else None,
        )

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        if event.data_table.id != "results-table":
            return
        result = self._result_at_row(event.data_table, event.cursor_row)
        if result is None:
            return
        self._show_detail(result)

    def on_data_table_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        if not event.data_table.id or not event.data_table.id.startswith("results-table-"):
            return
        result = self._result_at_row(event.data_table, event.cursor_row)
        if result is None:
            return
        self._show_detail(result)

    def _show_detail(self, result: IntruderResult) -> None:
        self._current_result = result
        req_raw = result.request_raw or ""
        resp_raw = result.response_raw or ""
        try:
            panel = self.query_one("#intruder-detail-panel")
            panel.display = True
        except Exception as exc:
            logger.warning("INTRUDER: _show_detail panel query failed: %s", exc)
        self.call_after_refresh(self._load_detail_content, req_raw, resp_raw)

    def _load_detail_content(self, req_raw: str, resp_raw: str) -> None:
        try:
            req_view = self.query_one("#detail-request", HttpView)
            req_view.load_raw_http(req_raw)
        except Exception as exc:
            logger.debug("_load_detail_content: req_view error: %s", exc)
        try:
            resp_view = self.query_one("#detail-response", HttpView)
            if resp_raw:
                resp_view.load_raw_http(resp_raw)
            else:
                resp_view.clear()
        except Exception as exc:
            logger.debug("_load_detail_content: resp_view error: %s", exc)

    def action_hide_detail(self) -> None:
        try:
            panel = self.query_one("#intruder-detail-panel")
            panel.display = False
            self._current_result = None
        except Exception as exc:
            logger.debug("op: %s", exc)

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
            ("send_scanner",  "Send to Scanner"),
            ("copy_payload",  "Copy Payload"),
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
        except Exception as exc:
            logger.debug("op: %s", exc)

    def _copy_selected_payload(self) -> None:
        try:
            table = self._results_table()
            result = self._result_at_row(table, table.cursor_row)
            if result is not None:
                payload_str = " | ".join(result.payload_values)
                from pentool.utils.copy_as import copy_to_clipboard
                copy_to_clipboard(payload_str)
                self.app.notify("Payload copied", timeout=2)
        except Exception as exc:
            logger.debug("op: %s", exc)

    def _export_csv(self) -> None:
        if not self._all_results:
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
                    for r in self._all_results:
                        writer.writerow([
                            r.request_number,
                            " | ".join(r.payload_values),
                            r.response_status or "",
                            r.response_length or "",
                            r.response_time_ms or "",
                            r.error or "",
                            r.timestamp.isoformat(),
                        ])
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
            if self.query_one(f"#{self._wid(tab.tab_id, 'proc-url-encode')}", Checkbox).value:
                ops.append("url_encode")
            if self.query_one(f"#{self._wid(tab.tab_id, 'proc-base64')}", Checkbox).value:
                ops.append("base64_encode")
            if self.query_one(f"#{self._wid(tab.tab_id, 'proc-html-encode')}", Checkbox).value:
                ops.append("html_encode")
            if self.query_one(f"#{self._wid(tab.tab_id, 'proc-md5')}", Checkbox).value:
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
        except Exception as exc:
            logger.debug("op: %s", exc)
        try:
            editor = self._template_editor()
            w = editor.content_widget
            if isinstance(w, TextArea):
                _load_into_textarea(w, raw, ["§"])
                self._update_payload_select()
                self._highlight_nth_marker(self._active_set_idx)
        except Exception as exc:
            logger.debug("op: %s", exc)

    def get_intruder_export(self) -> dict:
        api = getattr(self, "_api", None)
        if api is None:
            return {"results": []}
        try:
            return api.export_project_data()
        except Exception:
            return {"results": []}
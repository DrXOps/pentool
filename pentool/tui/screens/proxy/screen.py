"""Полноценный экран прокси-сервера."""

from __future__ import annotations

from urllib.parse import urlparse
import asyncio
import datetime
import json as _json
import os
import time

import pyarrow as pa
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.message import Message
from textual.widget import Widget
from pathlib import Path

_CSS = (Path(__file__).parent / "screen.tcss").read_text(encoding="utf-8")
from textual.widgets import (
    Label,
    Static,
    TabPane,
    TabbedContent,
    TextArea,
)
from textual_fastdatatable import DataTable as _BaseDataTable, ArrowBackend

from pentool.api.proxy_api import InterceptedRequest, MatchReplaceRule
from pentool.core.logging import get_logger
from pentool.tui.messages import SendToRepeater, SendToIntruder, SendToTarget, SyncScopeToTarget
from pentool.services.proxy_service import ProxyService
from pentool.tui.widgets.context_menu import ContextMenu
from pentool.tui.widgets.filter_bar import FilterBar
from pentool.tui.widgets.inspector_panel import InspectorPanel
from pentool.tui.widgets.request_editor import HttpView
from pentool.tui.widgets.resize_handle import ResizeHandle
from pentool.tui.mixins.app_mixin import AppMixin
from pentool.tui.mixins.request_context_menu import RequestContextMenuMixin

logger = get_logger(__name__)

# Колонки таблицы HTTP History
_COL_NAMES = ["ID", "Host", "Method", "URL", "Status", "Size", "Time"]

def _make_empty_table() -> pa.Table:
    """Пустая Arrow-таблица с нужными колонками."""
    return pa.table({
        "ID":     pa.array([], type=pa.int64()),
        "Host":   pa.array([], type=pa.string()),
        "Method": pa.array([], type=pa.string()),
        "URL":    pa.array([], type=pa.string()),
        "Status": pa.array([], type=pa.string()),
        "Size":   pa.array([], type=pa.string()),
        "Time":   pa.array([], type=pa.string()),
    })

def _rows_to_arrow(rows: list[dict]) -> pa.Table:
    """Преобразовать список dict из HttpStorage в Arrow-таблицу."""
    ids, hosts, methods, urls, statuses, sizes, times = [], [], [], [], [], [], []
    for r in rows:
        ids.append(r.get("id", 0))
        host = str(r.get("host", "") or "")
        # Минимальная ширина Host — 30 символов, чтобы колонка не была узкой
        hosts.append(host)
        methods.append(str(r.get("method", "") or ""))
        url = str(r.get("url", "") or "")
        urls.append(url[:80] + "…" if len(url) > 80 else url)
        status = r.get("status_code")
        statuses.append(str(status) if status is not None else "-")
        length = r.get("length")
        sizes.append(str(length) if length is not None else "-")
        ts = r.get("timestamp")
        if ts:
            try:
                dt = datetime.datetime.fromtimestamp(ts)
                times.append(dt.strftime("%H:%M:%S"))
            except Exception:
                times.append("-")
        else:
            times.append("-")
    # Если таблица пустая — добавляем фиктивную строку-заглушку для ширины колонок,
    # но только если данных нет вообще
    if not rows:
        return pa.table({
            "ID":     pa.array([], type=pa.int64()),
            "Host":   pa.array([], type=pa.string()),
            "Method": pa.array([], type=pa.string()),
            "URL":    pa.array([], type=pa.string()),
            "Status": pa.array([], type=pa.string()),
            "Size":   pa.array([], type=pa.string()),
            "Time":   pa.array([], type=pa.string()),
        })
    return pa.table({
        "ID":     pa.array(ids,      type=pa.int64()),
        "Host":   pa.array(hosts,    type=pa.string()),
        "Method": pa.array(methods,  type=pa.string()),
        "URL":    pa.array(urls,     type=pa.string()),
        "Status": pa.array(statuses, type=pa.string()),
        "Size":   pa.array(sizes,    type=pa.string()),
        "Time":   pa.array(times,    type=pa.string()),
    })

from pentool.tui.widgets.toolbar_button import ToolbarButton

from textual import events as _events, on

class _ProxyDataTable(_BaseDataTable):
    """DataTable для Proxy HTTP History.

    Для Ctrl+левой кнопки публикуем собственное сообщение ContextMenuRequest,
    чтобы ProxyScreen мог открыть контекстное меню без зависимости от пузырения.
    (Правая кнопка button=3 не доходит до Textual в VTE-терминале.)
    """

    class ContextMenuRequest(Message):
        """Запрос открытия контекстного меню от DataTable."""
        def __init__(self, screen_x: int, screen_y: int) -> None:
            super().__init__()
            self.screen_x = screen_x
            self.screen_y = screen_y

    async def on_event(self, event: _events.Event) -> None:
        if isinstance(event, _events.MouseDown) and (
            event.button == 3 or (event.button == 1 and event.ctrl)
        ):
            # Сначала вызываем базовый обработчик (двигаем курсор к строке)
            await super().on_event(event)
            # Публикуем собственное сообщение — оно всегда поднимается к родителю
            self.post_message(self.ContextMenuRequest(event.screen_x, event.screen_y))
        else:
            await super().on_event(event)

DataTable = _ProxyDataTable

class ProxyScreen(RequestContextMenuMixin, AppMixin, Widget):
    """Полный экран модуля Proxy."""

    DEFAULT_CSS = _CSS

    BINDINGS = [
        Binding("i",       "toggle_inspector",  "Inspector",    show=False),
        Binding("h",       "focus_tab_history",  "HTTP History", show=False),
        Binding("n",       "focus_tab_intercept","Intercept",    show=False),
        Binding("w",       "focus_tab_ws",       "WS History",   show=False),
        Binding("ctrl+h",  "focus_tab_history",  "HTTP History", show=False),
        Binding("ctrl+n",  "focus_tab_intercept","Intercept",    show=False),
        Binding("ctrl+w",  "focus_tab_ws",       "WS History",   show=False),
    ]

    # Для совместимости с тестами (test_stage8_5)
    _COL_LABELS = ["ID", "Mth", "URL", "St", "Size"]

    # ── RequestContextMenuMixin config ────────────────────────────────────────
    _cm_show_nmap          = True
    _cm_show_send_scanner  = True
    _cm_show_send_decoder  = True
    _cm_show_send_comparer = True

    def __init__(self, proxy_service: ProxyService | None = None, **kwargs) -> None:
        super().__init__(**kwargs)
        self._proxy_service: ProxyService | None = proxy_service
        self._selected_req_id: int | None = None
        self._rows_cache: list[dict] = []
        self._ws_rows_cache: list[dict] = []
        self._sort_col: int | None = None
        self._sort_reverse: bool = False
        self._inspector_visible: bool = False
        self._current_filters: dict | None = None
        self._pending_req_ids: dict[str, int] = {}
        self._intercept_req: InterceptedRequest | None = None
        self._intercept_pending: list[InterceptedRequest] = []

    def compose(self) -> ComposeResult:
        # Toolbar (снаружи SubTabs — все btn-* ID всегда в DOM)
        with Horizontal(id="toolbar"):
            yield ToolbarButton("○ Proxy",     "btn-proxy",     classes="inactive")
            yield Static(" │ ", classes="toolbar-sep")
            yield ToolbarButton("○ Intercept", "btn-intercept", classes="inactive")
            yield Static(" │ ", classes="toolbar-sep")
            yield ToolbarButton("Scope",       "btn-scope")
            yield Static(" │ ", classes="toolbar-sep")
            yield ToolbarButton("M/R",         "btn-mr")
            yield Static(" │ ", classes="toolbar-sep")
            yield ToolbarButton("Load History","btn-load-history")
            yield Static(" │ ", classes="toolbar-sep")
            yield ToolbarButton("Clear",       "btn-clear")

        # Под-вкладки прокси
        with TabbedContent(id="proxy-subtabs"):
            with TabPane("Intercept", id="tab-intercept"):
                with Horizontal(id="intercept-toolbar"):
                    yield ToolbarButton("⏩ Forward", "btn-forward", classes="disabled")
                    yield ToolbarButton("✖ Drop",    "btn-drop",    classes="disabled")
                    yield Static(" │ ", classes="toolbar-sep")
                    yield Label("(enable Intercept to capture requests)", id="intercept-hint")
                with Vertical(id="intercept-req-area"):
                    yield Static("", id="intercept-headers-preview", markup=True)
                    yield TextArea(
                        "(No requests waiting for intercept)",
                        id="intercept-editor",
                        read_only=False,
                    )
                yield ResizeHandle(
                    "intercept-req-area", "intercept-bottom-area",
                    vertical=True,
                    id="resize-intercept",
                )
                with Horizontal(id="intercept-bottom-area"):
                    with Vertical(id="intercept-sent-panel"):
                        yield Static("Sent Request", classes="panel-title")
                        yield HttpView(id="intercept-sent-req")
                    yield ResizeHandle(
                        "intercept-sent-panel", "intercept-resp-panel",
                        id="resize-intercept-sent-resp",
                    )
                    with Vertical(id="intercept-resp-panel"):
                        yield Static("Response", classes="panel-title")
                        yield HttpView(id="intercept-resp-viewer")

            with TabPane("HTTP History", id="tab-http-history"):
                with Horizontal(id="body"):
                    with Vertical(id="main-panel"):
                        # Верхняя часть: FilterBar + DataTable
                        with Vertical(id="table-area"):
                            yield FilterBar(id="filter-bar")
                            yield DataTable(
                                backend=ArrowBackend(_make_empty_table()),
                                id="request-list",
                                cursor_type="row",
                                zebra_stripes=True,
                                max_column_content_width=120,
                                column_widths=[5, 20, 8, 60, 6, 8, 8],
                            )
                        # ResizeHandle между таблицей и детальной панелью
                        yield ResizeHandle(
                            "table-area", "detail-area",
                            vertical=True,
                            id="resize-table-detail",
                        )
                        # Нижняя часть: Request | ResizeHandle | Response
                        with Horizontal(id="detail-area"):
                            with Vertical(id="req-panel"):
                                yield Static("Request", classes="panel-title")
                                yield HttpView(id="req-editor")
                            yield ResizeHandle(
                                "req-panel", "resp-panel",
                                id="resize-req-resp",
                            )
                            with Vertical(id="resp-panel"):
                                yield Static("Response", classes="panel-title")
                                yield HttpView(id="resp-viewer")
                    # Inspector (скрыт по умолчанию)
                    yield InspectorPanel(id="inspector-panel")

            with TabPane("WS History", id="tab-ws-history"):
                with Horizontal(id="ws-body"):
                    with Vertical(id="ws-main-panel"):
                        with Vertical(id="ws-table-area"):
                            yield DataTable(
                                backend=ArrowBackend(_make_empty_table()),
                                id="ws-request-list",
                                cursor_type="row",
                                zebra_stripes=True,
                                column_widths=[5, 20, 8, 60, 6, 8, 8],
                            )
                        yield ResizeHandle(
                            "ws-table-area", "ws-detail-area",
                            vertical=True,
                            id="resize-ws-table-detail",
                        )
                        with Horizontal(id="ws-detail-area"):
                            with Vertical(id="ws-req-panel"):
                                yield Static("Request", classes="panel-title")
                                yield HttpView(id="ws-req-editor")
                            yield ResizeHandle(
                                "ws-req-panel", "ws-resp-panel",
                                id="resize-ws-req-resp",
                            )
                            with Vertical(id="ws-resp-panel"):
                                yield Static("Response", classes="panel-title")
                                yield HttpView(id="ws-resp-viewer")
                        yield ResizeHandle(
                            "ws-detail-area", "ws-messages-area",
                            vertical=True,
                            id="resize-ws-detail-msg",
                        )
                        with Vertical(id="ws-messages-area"):
                            yield Static(
                                "WebSocket Messages",
                                id="ws-msg-label",
                                classes="panel-title",
                            )
                            from textual.widgets import RichLog
                            yield RichLog(
                                id="ws-msg-log",
                                highlight=True,
                                markup=True,
                                wrap=True,
                                max_lines=1000,
                            )

        yield Static(
            "Ctrl+R: Repeater  │  Ctrl+T: Target  │  Ctrl+U: Copy URL  │  M: Context menu  │  I: Inspector  │  H: HTTP History  │  N: Intercept  │  W: WS History",
            id="status-bar",
        )

    def on_mount(self) -> None:
        self._sync_proxy_button()
        self._sync_intercept_button()
        self._setup_tooltips()
        # init_storage запускается из app.on_mount после инжекции _proxy_service
        # Установить начальное состояние ScopeToggle из конфига
        try:
            from pentool.core.config import get_config
            from pentool.tui.widgets.filter_bar import FilterBar, ScopeToggle
            scope = get_config().scope
            filter_bar = self.query_one("#filter-bar", FilterBar)
            filter_bar.query_one("#fb-scope", ScopeToggle).set_scope_empty(not bool(scope))
        except Exception:
            pass
        # Подписаться на WS-фреймы
        try:
            from pentool.core.event_bus import get_event_bus
            from pentool.core.events import WebSocketFrameEvent
            get_event_bus().subscribe(WebSocketFrameEvent, self._on_ws_frame_event)
        except Exception:
            pass

    def _on_ws_frame_event(self, event) -> None:
        """Получен WS-фрейм — добавить в лог (thread-safe)."""
        self.app.call_from_thread(self._append_ws_frame, event)

    def _append_ws_frame(self, event) -> None:
        try:
            from textual.widgets import RichLog
            log = self.query_one("#ws-msg-log", RichLog)
            opcode = getattr(event, "opcode", 0x1)
            direction = getattr(event, "direction", "")
            payload_text = getattr(event, "payload_text", "")
            payload = getattr(event, "payload", b"")

            _OPCODE_NAMES = {0x1: "TEXT", 0x2: "BIN", 0x8: "CLOSE", 0x9: "PING", 0xA: "PONG"}
            op_name = _OPCODE_NAMES.get(opcode, f"0x{opcode:X}")

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
                    f"{body}"
                )
            elif opcode == 0x2:
                log.write(
                    f"[{dir_color}]{dir_arrow} {op_name}[/{dir_color}] "
                    f"[dim]{getattr(event, 'request_id', '')}[/dim] "
                    f"[dim]{len(payload)} bytes[/dim]"
                )
            else:
                log.write(
                    f"[{dir_color}]{dir_arrow} {op_name}[/{dir_color}] "
                    f"[dim]{getattr(event, 'request_id', '')}[/dim]"
                )
        except Exception:
            pass

    def on_unmount(self) -> None:
        """Отписаться от EventBus при удалении виджета."""
        try:
            from pentool.core.event_bus import get_event_bus
            from pentool.core.events import WebSocketFrameEvent
            get_event_bus().unsubscribe(WebSocketFrameEvent, self._on_ws_frame_event)
        except Exception:
            pass

    async def _reload_table(self, filters: dict | None = None) -> None:
        """Загрузить/перезагрузить данные в DataTable из storage."""
        if self._proxy_service is None or not self._proxy_service.is_storage_ready():
            return
        try:
            logger.info("PROXY SCREEN: _reload_table called, filters=%s", filters)
            rows = await self._proxy_service.get_history(filters=filters)
            logger.info("PROXY SCREEN: _reload_table loaded %d rows", len(rows))
            self._rows_cache = rows
            self._current_filters = filters
            arrow = _rows_to_arrow(rows)
            table = self.query_one("#request-list", DataTable)
            table.backend = ArrowBackend(arrow)
            table._ordered_columns = None
            try:
                for col in table.ordered_columns:
                    if str(col.label).strip().startswith("Host"):
                        col.width = 30
                        col.auto_width = False
                        break
            except Exception:
                pass
            table._clear_caches()
            table._require_update_dimensions = True
            table.refresh()
            # Скролл к первой строке (новые запросы идут сверху)
            if rows:
                table.move_cursor(row=0)
        except Exception as exc:
            logger.error("_reload_table failed: %s", exc)

    async def _reload_ws_table(self) -> None:
        """Загрузить/перезагрузить WebSocket-запросы в WS History таблицу."""
        if self._proxy_service is None or not self._proxy_service.is_storage_ready():
            return
        try:
            logger.info("PROXY SCREEN: _reload_ws_table called")
            rows = await self._proxy_service.get_history(filters={"is_websocket": True})
            logger.info("PROXY SCREEN: _reload_ws_table loaded %d WS rows", len(rows))
            self._ws_rows_cache = rows
            arrow = _rows_to_arrow(rows)
            try:
                table = self.query_one("#ws-request-list", DataTable)
            except Exception:
                return
            table.backend = ArrowBackend(arrow)
            table._ordered_columns = None
            try:
                for col in table.ordered_columns:
                    if str(col.label).strip().startswith("Host"):
                        col.width = 30
                        col.auto_width = False
                        break
            except Exception:
                pass
            table._clear_caches()
            table._require_update_dimensions = True
            table.refresh()
            if rows:
                table.move_cursor(row=0)
        except Exception as exc:
            logger.error("_reload_ws_table failed: %s", exc)

    def _setup_tooltips(self) -> None:
        tooltips = {
            "btn-proxy":     "Toggle proxy server",
            "btn-forward":   "Forward intercepted request",
            "btn-drop":      "Drop intercepted request",
            "btn-intercept": "Toggle intercept mode",
            "btn-scope":     "Configure scope settings",
            "btn-mr":        "Match and Replace rules",
            "btn-ca-cert":   "Install CA certificate",
            "btn-clear":     "Clear request history",
        }
        for btn_id, tip in tooltips.items():
            try:
                self.query_one(f"#{btn_id}", ToolbarButton).tooltip = tip
            except Exception:
                pass

    def load_from_project(self) -> None:
        """Вызывается после смены проекта — перезагружает таблицу из storage (уже переключённого)."""
        try:
            from pentool.core.config import get_config
            from pentool.tui.widgets.filter_bar import FilterBar, ScopeToggle
            scope = get_config().scope
            filter_bar = self.query_one("#filter-bar", FilterBar)
            filter_bar.query_one("#fb-scope", ScopeToggle).set_scope_empty(not bool(scope))
        except Exception:
            pass
        self.run_worker(self._reload_from_storage())

    async def _reload_from_proxy(self) -> None:
        """Синхронизировать storage из in-memory прокси (для случая очистки/сброса истории)."""
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

    async def _reload_from_storage(self) -> None:
        """Перезагрузить таблицу из текущего storage без сброса данных."""
        if self._proxy_service is None:
            return
        for _ in range(60):
            if self._proxy_service.is_storage_ready():
                break
            await asyncio.sleep(0.1)
        if not self._proxy_service.is_storage_ready():
            logger.error("_reload_from_storage: storage not ready after 6s")
            return
        await self._reload_table()
        await self._reload_ws_table()

    def add_request_row(self, req: object) -> None:
        """Вызывается из app при поступлении нового запроса (без ответа ещё)."""
        if not isinstance(req, InterceptedRequest):
            return
        if req.id in self._pending_req_ids:
            logger.debug("PROXY SCREEN: add_request_row: duplicate req.id=%s, skipping", req.id)
            return
        logger.info("PROXY SCREEN: add_request_row: %s %s (id=%s, ws=%s)", req.method, req.url, req.id, req.is_websocket)
        self._pending_req_ids[req.id] = -1
        self.run_worker(self._store_request(req))

    def update_request_row(self, req: object) -> None:
        """Вызывается из app когда запрос полностью завершён (с ответом)."""
        if not isinstance(req, InterceptedRequest):
            return
        status = req.response.status if req.response else None
        logger.info("PROXY SCREEN: update_request_row: %s %s → %s (id=%s)", req.method, req.url, status, req.id)
        self.run_worker(self._update_and_reload(req))

    async def _store_request(self, req: InterceptedRequest) -> None:
        if self._proxy_service is None:
            return
        row_id = await self._proxy_service.store_request(req)
        if row_id is not None:
            logger.info("PROXY SCREEN: _store_request: saved req.id=%s as row_id=%d", req.id, row_id)
            self._pending_req_ids[req.id] = row_id

    async def _wait_for_row_id(self, req: InterceptedRequest) -> int | None:
        """Ждать пока _store_request заменит sentinel -1 на реальный row_id."""
        for _ in range(50):
            row_id = self._pending_req_ids.get(req.id)
            if row_id is not None and row_id != -1:
                return row_id
            if req.id not in self._pending_req_ids:
                return None
            await asyncio.sleep(0.1)
        return self._pending_req_ids.get(req.id)

    async def _update_and_reload(self, req: InterceptedRequest) -> None:
        if self._proxy_service is None or not self._proxy_service.is_storage_ready():
            return
        await self._wait_for_row_id(req)
        actual_row_id = self._pending_req_ids.pop(req.id, None)
        if actual_row_id and actual_row_id != -1 and req.response is not None:
            await self._proxy_service.update_response(actual_row_id, req.response)
        elif actual_row_id is None and req.response is not None:
            await self._proxy_service.store_request(req)
        if req.is_websocket:
            await self._reload_ws_table()
        elif self._current_filters:
            await self._reload_table(self._current_filters)
        elif actual_row_id and actual_row_id != -1:
            self._append_row_to_table(req, actual_row_id)
        else:
            await self._reload_table(None)

    def _append_row_to_table(self, req: InterceptedRequest, row_id: int) -> None:
        """Инкрементально добавить одну строку в таблицу без полного reload."""
        parsed = req.to_parsed_request()
        url = parsed.url or ""
        ts = time.time()
        row: dict = {
            "id": row_id,
            "host": parsed.headers.get("Host", "").split(":")[0] or url.split("/")[2] if "://" in url else url,
            "method": req.method or "",
            "url": url,
            "status_code": req.response.status if req.response else None,
            "length": len((req.response.body or "").encode("utf-8")) if req.response else None,
            "timestamp": ts,
            "is_websocket": req.is_websocket,
        }
        self._rows_cache.insert(0, row)
        try:
            arrow = _rows_to_arrow(self._rows_cache)
            table = self.query_one("#request-list", DataTable)
            table.backend = ArrowBackend(arrow)
            table._ordered_columns = None
            table._clear_caches()
            table._require_update_dimensions = True
            table.refresh()
        except Exception as exc:
            logger.debug("PROXY SCREEN: _append_row_to_table: %s", exc)

    def _select_row(self, row_idx: int) -> None:
        if 0 <= row_idx < len(self._rows_cache):
            row = self._rows_cache[row_idx]
            self._selected_req_id = row.get("id")
            self.run_worker(self._load_row_details(self._selected_req_id))

    def _select_ws_row(self, row_idx: int) -> None:
        """Выбор строки в WS History — загружает детали в ws-панели."""
        if 0 <= row_idx < len(self._ws_rows_cache):
            row = self._ws_rows_cache[row_idx]
            row_id = row.get("id")
            if row_id is not None:
                self.run_worker(self._load_ws_row_details(row_id))

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        if event.data_table.id == "ws-request-list":
            self._select_ws_row(event.cursor_row)
        else:
            self._select_row(event.cursor_row)

    def on_data_table_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        if event.data_table.id == "ws-request-list":
            self._select_ws_row(event.cursor_row)
        else:
            self._select_row(event.cursor_row)

    def on_data_table_cell_highlighted(self, event: DataTable.CellHighlighted) -> None:
        """Даём фокус DataTable при любом движении курсора — нужно для скролла мышью."""
        try:
            event.data_table.focus()
        except Exception:
            pass

    async def _load_row_details(self, row_id: int | None) -> None:
        if row_id is None or self._proxy_service is None or not self._proxy_service.is_storage_ready():
            return
        entry = await self._proxy_service.get_full_entry(row_id)
        if entry is None:
            return
        self.call_after_refresh(self._load_entry_details, entry)

    async def _load_ws_row_details(self, row_id: int) -> None:
        if self._proxy_service is None or not self._proxy_service.is_storage_ready():
            return
        entry = await self._proxy_service.get_full_entry(row_id)
        if entry is None:
            return
        self.call_after_refresh(self._load_ws_entry_details, entry)

    def _load_ws_entry_details(self, entry: dict) -> None:
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
            self.query_one("#ws-req-editor", HttpView).load_raw_http(raw_req)
        except Exception:
            pass

        resp_headers = entry.get("response_headers") or {}
        status = entry.get("status_code")
        resp_body = entry.get("response_body", "") or ""
        try:
            view = self.query_one("#ws-resp-viewer", HttpView)
            if status is not None:
                headers_text = "\r\n".join(f"{k}: {v}" for k, v in (resp_headers if isinstance(resp_headers, dict) else {}).items())
                raw = f"HTTP/1.1 {status}\r\n{headers_text}\r\n\r\n{resp_body}"
                view.load_raw_http(raw)
            else:
                view.load_raw_http("(no response)")
        except Exception:
            pass

    def on_data_table_header_selected(self, event: DataTable.HeaderSelected) -> None:
        idx = event.column_index
        self._sort_reverse = (self._sort_col == idx) and not self._sort_reverse
        self._sort_col = idx
        col_name = _COL_NAMES[idx] if idx < len(_COL_NAMES) else ""
        if col_name:
            direction = "descending" if self._sort_reverse else "ascending"
            event.data_table.sort(by=[(col_name, direction)])
            # Обновить метки колонок — показать стрелку у активной
            try:
                for i, name in enumerate(_COL_NAMES):
                    col = event.data_table.ordered_columns[i]
                    if i == idx:
                        arrow = "▼" if self._sort_reverse else "▲"
                        col.label = f"{name} {arrow}"
                    else:
                        col.label = name
                event.data_table.refresh()
            except Exception:
                pass

    def on_filter_bar_filter_changed(self, event: FilterBar.FilterChanged) -> None:
        filters = event.filters if event.filters else None
        self.run_worker(self._reload_table(filters))

    def action_toggle_inspector(self) -> None:
        self._inspector_visible = not self._inspector_visible
        try:
            panel = self.query_one("#inspector-panel", InspectorPanel)
            if self._inspector_visible:
                panel.add_class("-visible")
            else:
                panel.remove_class("-visible")
        except Exception:
            pass

    def _switch_proxy_tab(self, tab_id: str) -> None:
        """Переключиться на вкладку Proxy и поставить фокус на таблицу."""
        try:
            from textual.widgets import TabbedContent
            tabs = self.query_one(TabbedContent)
            tabs.active = tab_id
            # Ставим фокус на DataTable в нужной вкладке
            self.call_after_refresh(self._focus_tab_table, tab_id)
        except Exception:
            pass

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
                except Exception:
                    pass
        except Exception:
            pass

    def action_focus_tab_history(self) -> None:
        """Переключиться на HTTP History."""
        self._switch_proxy_tab("tab-http-history")

    def action_focus_tab_intercept(self) -> None:
        """Переключиться на Intercept."""
        self._switch_proxy_tab("tab-intercept")

    def action_focus_tab_ws(self) -> None:
        """Переключиться на WS History."""
        self._switch_proxy_tab("tab-ws-history")

    def on_key(self, event) -> None:
        if event.key == "ctrl+r":
            self.action_send_to_repeater()
            event.prevent_default()
        elif event.key == "ctrl+u":
            self._copy_selected_url()
            event.prevent_default()
        elif event.key == "ctrl+t":
            self._send_to_target()
            event.prevent_default()
        elif event.key == "m":
            self._show_context_menu_at_cursor()
            event.prevent_default()

    def _show_context_menu_at_cursor(self) -> None:
        try:
            table = self.query_one("#request-list", DataTable)
            r = table.region
            x = r.x + 2
            y = r.y + 1 + table.cursor_row
        except Exception:
            x, y = 10, 5
        self._open_context_menu(x, y)

    def action_send_to_repeater(self) -> None:
        if self._selected_req_id is None:
            return
        self.run_worker(self._do_send_to("repeater"))

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
        """Автоматически добавить хост из URL в Target sitemap."""
        try:
            from pentool.utils.parser import ParsedRequest
            parsed = ParsedRequest(method="GET", url=url, headers={}, body="")
            from pentool.tui.messages import SendToTarget
            self.app.post_message(SendToTarget(parsed))  # type: ignore[attr-defined]
        except Exception:
            pass

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
            copy_as_curl, copy_as_fetch, copy_as_ffuf, copy_as_sqlmap,
            copy_as_nmap, copy_as_jwt_tool, copy_to_clipboard,
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
            self.app.notify(
                f"Clipboard unavailable. {label}:\n{text[:80]}",
                severity="warning", timeout=5
            )

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
            pass

        resp_headers = entry.get("response_headers") or {}
        status = entry.get("status_code")
        resp_body = entry.get("response_body", "") or ""
        try:
            view = self.query_one("#resp-viewer", HttpView)
            if status is not None:
                headers_text = "\r\n".join(f"{k}: {v}" for k, v in (resp_headers if isinstance(resp_headers, dict) else {}).items())
                raw = f"HTTP/1.1 {status}\r\n{headers_text}\r\n\r\n{resp_body}"
                view.load_raw_http(raw)
            else:
                view.load_raw_http("(no response)")
        except Exception:
            pass

        try:
            panel = self.query_one("#inspector-panel", InspectorPanel)
            parsed_resp_for_inspector = None
            if status is not None:
                from pentool.utils.parser import ParsedResponse
                parsed_resp_for_inspector = ParsedResponse(
                    status=status,
                    headers=resp_headers if isinstance(resp_headers, dict) else {},
                    body=resp_body,
                )
            panel.load(parsed_req, parsed_resp_for_inspector)
        except Exception:
            pass

    @on(ToolbarButton.Pressed, "#btn-proxy")
    def on_btn_proxy(self, _: ToolbarButton.Pressed) -> None:
        self.action_toggle_proxy()

    @on(ToolbarButton.Pressed, "#btn-forward")
    def on_btn_forward(self, _: ToolbarButton.Pressed) -> None:
        self.action_forward()

    @on(ToolbarButton.Pressed, "#btn-drop")
    def on_btn_drop(self, _: ToolbarButton.Pressed) -> None:
        self.action_drop()

    @on(ToolbarButton.Pressed, "#btn-intercept")
    def on_btn_intercept(self, _: ToolbarButton.Pressed) -> None:
        self.action_toggle_intercept()

    @on(ToolbarButton.Pressed, "#btn-scope")
    def on_btn_scope(self, _: ToolbarButton.Pressed) -> None:
        self.action_open_scope()

    @on(ToolbarButton.Pressed, "#btn-mr")
    def on_btn_mr(self, _: ToolbarButton.Pressed) -> None:
        self.action_open_mr()

    @on(ToolbarButton.Pressed, "#btn-load-history")
    def on_btn_load_history(self, _: ToolbarButton.Pressed) -> None:
        self.action_load_history()

    @on(ToolbarButton.Pressed, "#btn-clear")
    def on_btn_clear(self, _: ToolbarButton.Pressed) -> None:
        self.action_clear_list()

    def action_load_history(self) -> None:
        self.run_worker(self._reload_table(self._current_filters))

    def action_forward(self) -> None:
        proxy = self._get_proxy()
        if proxy is None or self._intercept_req is None:
            return
        req = self._intercept_req
        try:
            editor = self.query_one("#intercept-editor", TextArea)
            modified = editor.text
        except Exception:
            modified = None
        # Показать отправленный запрос в левой нижней панели
        sent_text = modified if modified and modified.strip() else ""
        try:
            self.query_one("#intercept-sent-req", HttpView).load_raw_http(sent_text)
        except Exception:
            pass
        # Очистить правую панель ответа — ждём ответ от сервера
        try:
            self.query_one("#intercept-resp-viewer", HttpView).clear()
        except Exception:
            pass
        proxy.forward(req.id, modified if modified and modified.strip() else None)
        self._intercept_req = None
        # Если есть ожидающие — сразу показать следующий
        if self._intercept_pending:
            next_req = self._intercept_pending.pop(0)
            self._display_intercept_req(next_req)
        else:
            # Дизейблим кнопки — ответ появится асинхронно через show_intercept_response
            self._disable_intercept_buttons(hint="⏳ Forwarded — waiting for response…")

    def action_drop(self) -> None:
        proxy = self._get_proxy()
        if proxy is None or self._intercept_req is None:
            return
        proxy.drop(self._intercept_req.id)
        self._intercept_req = None
        # Если есть ожидающие — сразу показать следующий
        if self._intercept_pending:
            next_req = self._intercept_pending.pop(0)
            self._display_intercept_req(next_req)
            return
        self._disable_intercept_buttons(hint="✖ Dropped")
        # При Drop очищаем верхний редактор и обе нижние панели
        try:
            self.query_one("#intercept-editor", TextArea).load_text(
                "(No requests waiting for intercept)"
            )
        except Exception:
            pass
        try:
            preview = self.query_one("#intercept-headers-preview", Static)
            preview.update("")
            preview.display = False
        except Exception:
            pass
        try:
            self.query_one("#intercept-sent-req", HttpView).clear()
        except Exception:
            pass
        try:
            self.query_one("#intercept-resp-viewer", HttpView).clear()
        except Exception:
            pass

    def _disable_intercept_buttons(self, hint: str = "") -> None:
        """Дизейблить Forward/Drop и обновить подсказку."""
        try:
            self.query_one("#btn-forward", ToolbarButton).disabled = True
            self.query_one("#btn-drop",    ToolbarButton).disabled = True
        except Exception:
            pass
        if hint:
            try:
                self.query_one("#intercept-hint", Label).update(hint)
            except Exception:
                pass

    def show_intercepted_request(self, req: InterceptedRequest) -> None:
        """Вызывается из app при перехвате запроса — показывает в Intercept Tab.

        Если сейчас уже ожидает другой запрос (Forward/Drop ещё не нажато),
        новый запрос встаёт в очередь. Так пользователь видит запросы по одному,
        а не теряет их (и proxy корректно блокирует каждый до решения).
        """
        if self._intercept_req is not None:
            # Уже показываем запрос — встаём в очередь
            self._intercept_pending.append(req)
            try:
                self.query_one("#intercept-hint", Label).update(
                    f"⏸ {req.method} {req.url}  (+{len(self._intercept_pending)} queued)"
                )
            except Exception:
                pass
            return
        self._display_intercept_req(req)

    def _display_intercept_req(self, req: InterceptedRequest) -> None:
        """Отобразить запрос в Intercept Tab (используется при показе и при переходе к следующему)."""
        self._intercept_req = req
        try:
            from pentool.utils.parser import build_http_request
            raw = build_http_request(req.to_parsed_request())
        except Exception:
            raw = f"{req.method} {req.url}\n\n(could not render request)"
        try:
            editor = self.query_one("#intercept-editor", TextArea)
            editor.load_text(raw)
        except Exception:
            pass
        # Подсветка заголовков над редактором
        try:
            from pentool.tui.widgets.request_editor import _render_headers_rich
            parsed = req.to_parsed_request()
            request_line = f"{parsed.method} {parsed.path} HTTP/1.1"
            markup = _render_headers_rich(request_line, parsed.headers)
            preview = self.query_one("#intercept-headers-preview", Static)
            preview.update(markup)
            preview.display = True
        except Exception:
            pass
        # Очищаем только панель ответа — Sent Request не трогаем
        # (он обновляется только в action_forward/action_drop)
        try:
            self.query_one("#intercept-resp-viewer", HttpView).clear()
        except Exception:
            pass
        try:
            self.query_one("#btn-forward", ToolbarButton).disabled = False
            self.query_one("#btn-drop",    ToolbarButton).disabled = False
        except Exception:
            pass
        queued = len(self._intercept_pending)
        hint = f"⏸ Intercepted: {req.method} {req.url}"
        if queued:
            hint += f"  (+{queued} queued)"
        try:
            self.query_one("#intercept-hint", Label).update(hint)
        except Exception:
            pass
        # Переключиться на вкладку Intercept
        try:
            tabs = self.query_one("#proxy-subtabs", TabbedContent)
            tabs.active = "tab-intercept"
        except Exception:
            pass

    def show_intercept_response(self, req: InterceptedRequest) -> None:
        if req.response is None:
            return
        try:
            resp = req.response
            status_line = f"HTTP/1.1 {resp.status} {resp.reason}"
            headers = "\r\n".join(f"{k}: {v}" for k, v in resp.headers.items())
            body = resp.body or ""
            raw = f"{status_line}\r\n{headers}\r\n\r\n{body}"
            self.query_one("#intercept-resp-viewer", HttpView).load_raw_http(raw)
        except Exception:
            pass
        try:
            self.query_one("#intercept-hint", Label).update(
                f"✓ Response: {req.response.status} — {req.method} {req.url}"
            )
        except Exception:
            pass

    def action_toggle_intercept(self) -> None:
        self.app.action_toggle_intercept()  # type: ignore[attr-defined]
        self._sync_intercept_button()
        # При выключении перехвата — сбросить текущий и очередь,
        # иначе все накопленные запросы выскочат при следующем включении
        proxy = self._get_proxy()
        if proxy and not proxy.intercept_enabled:
            self._intercept_req = None
            self._intercept_pending.clear()
            self._disable_intercept_buttons(hint="(Intercept disabled)")

    def action_toggle_proxy(self) -> None:
        proxy = self._get_proxy()
        # Мгновенный визуальный отклик — ещё до того как поток запустится/остановится
        if proxy and not proxy.is_running:
            try:
                btn = self.query_one("#btn-proxy", ToolbarButton)
                btn.label = "⏳ Starting..."
                btn.remove_class("inactive")
                btn.add_class("active")
            except Exception:
                pass
            port = proxy.port if proxy else self.app._cfg.proxy_port  # type: ignore[attr-defined]
            self.app.notify(  # type: ignore[attr-defined]
                f"Starting proxy on :{port}...", timeout=3
            )
        elif proxy and proxy.is_running:
            try:
                btn = self.query_one("#btn-proxy", ToolbarButton)
                btn.label = "⏳ Stopping..."
                btn.remove_class("active")
                btn.add_class("inactive")
            except Exception:
                pass
            self.app.notify("Stopping proxy...", timeout=2)  # type: ignore[attr-defined]
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
        except Exception:
            pass
        self._selected_req_id = None

    async def _do_clear_table(self) -> None:
        if self._proxy_service is not None and self._proxy_service.is_storage_ready():
            await self._proxy_service.clear_history()
        self._rows_cache = []
        self._current_filters = None
        try:
            table = self.query_one("#request-list", DataTable)
            table.backend = ArrowBackend(_make_empty_table())
            table.refresh()
        except Exception:
            pass

    def action_open_scope(self) -> None:
        proxy = self._get_proxy()
        current = proxy.scope if proxy else []
        from pentool.tui.dialogs.scope_dialog import ScopeDialog

        def _apply(result: list[str] | None) -> None:
            if result is not None and proxy is not None:
                proxy.set_scope(result)
                # Синхронизируем scope в Config и сохраняем на диск
                try:
                    from pentool.core.config import get_config
                    cfg = get_config()
                    cfg.scope = list(result)
                    cfg.save()
                except Exception as e:
                    logger.warning("action_open_scope: failed to save scope to config: %s", e)
                # Обновить состояние ScopeToggle в FilterBar
                scope_toggle_was_active = False
                try:
                    from pentool.tui.widgets.filter_bar import FilterBar, ScopeToggle
                    filter_bar = self.query_one("#filter-bar", FilterBar)
                    st = filter_bar.query_one("#fb-scope", ScopeToggle)
                    scope_toggle_was_active = st.active
                    st.set_scope_empty(not bool(result))
                except Exception:
                    pass
                # Если ScopeToggle уже был активен — перезагрузить таблицу с новым scope
                if scope_toggle_was_active and result:
                    self.run_worker(self._reload_table({"scope_only": True}))
                elif not result:
                    # Scope очищен — снять фильтр и показать всё
                    self.run_worker(self._reload_table(None))
                if result is not None:
                    n = len(result)
                    self.app.notify(
                        f"Scope updated: {n} host{'s' if n != 1 else ''}",
                        timeout=3,
                    )

        self.app.push_screen(ScopeDialog(current), _apply)

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
        proxy = self._get_proxy()
        try:
            btn = self.query_one("#btn-proxy", ToolbarButton)
        except Exception:
            return
        if proxy and proxy.is_running:
            btn.label = f"● Proxy:{proxy.port}"
            btn.remove_class("inactive")
            btn.add_class("active")
        else:
            btn.label = "○ Proxy"
            btn.remove_class("active")
            btn.add_class("inactive")

    def _sync_intercept_button(self) -> None:
        proxy = self._get_proxy()
        try:
            btn = self.query_one("#btn-intercept", ToolbarButton)
        except Exception:
            return
        enabled = proxy and proxy.intercept_enabled
        if enabled:
            btn.label = "● Intercept"
            btn.remove_class("inactive")
            btn.add_class("active")
        else:
            btn.label = "○ Intercept"
            btn.remove_class("active")
            btn.add_class("inactive")

    def update_proxy_label(self, running: bool, port: int) -> None:
        self._sync_proxy_button()

    def update_intercept_label(self, enabled: bool) -> None:
        self._sync_intercept_button()

    # ID контейнеров, которые относятся к текстовым панелям (Request/Response)
    _TEXT_PANEL_IDS = frozenset({
        "req-panel", "resp-panel",
        "ws-req-panel", "ws-resp-panel",
        "req-editor", "resp-viewer",
        "ws-req-editor", "ws-resp-viewer",
        "intercept-editor", "intercept-sent-req", "intercept-resp-viewer",
        "intercept-req-area", "intercept-sent-panel", "intercept-resp-panel",
        # внутренние виджеты HttpView
        "http-headers", "http-body",
    })

    def _is_in_text_panel(self, widget) -> bool:
        """Проверить: виджет или один из его предков — текстовая панель."""
        try:
            from pentool.tui.widgets.request_editor import HttpView
            node = widget
            while node is not None and node is not self:
                nid = getattr(node, "id", None) or ""
                if nid in self._TEXT_PANEL_IDS:
                    return True
                # HttpView — всегда текстовая панель
                if isinstance(node, HttpView):
                    return True
                node = getattr(node, "parent", None)
        except Exception:
            pass
        return False

    def on__proxy_data_table_context_menu_request(self, event: _ProxyDataTable.ContextMenuRequest) -> None:
        """Обработка запроса контекстного меню от DataTable (Ctrl+click или правая кнопка)."""
        try:
            table = self.query_one("#request-list", DataTable)
            cursor_row = table.cursor_row
            if 0 <= cursor_row < len(self._rows_cache):
                self._selected_req_id = self._rows_cache[cursor_row].get("id")
        except Exception:
            pass
        self._open_context_menu(event.screen_x, event.screen_y)

    def on__base_http_widget_context_menu_request(self, event) -> None:
        """Ctrl+клик / правая кнопка на любом _BaseHttpWidget → контекстное меню."""
        self.cm_open_text_menu(event.screen_x, event.screen_y)

    def on_mouse_down(self, event) -> None:
        # Правая кнопка (button=3) или Ctrl+левая — контекстное меню
        if not ((event.button == 3) or (event.button == 1 and event.ctrl)):
            return

        widget = event.widget

        if self._is_in_text_panel(widget):
            # Клик в области Request / Response → текстовое меню
            self.cm_open_text_menu(event.screen_x, event.screen_y)
            event.stop()
            return

        # Клик в DataTable (#request-list) — обрабатывается через
        # on__proxy_data_table_context_menu_request, поэтому здесь
        # открываем меню только если событие пришло НЕ из таблицы
        try:
            table = self.query_one("#request-list", DataTable)
            node = widget
            while node is not None:
                if node is table:
                    # Это событие из DataTable — игнорируем (обработает ContextMenuRequest)
                    return
                node = getattr(node, "parent", None)
        except Exception:
            pass
        # Клик вне text panel и вне DataTable — открываем меню таблицы (общее)
        self._open_context_menu(event.screen_x, event.screen_y)
        event.stop()

    def on_click(self, event) -> None:
        # Двойной клик — загрузить детали в Request/Response панели
        if event.chain == 2:
            try:
                table = self.query_one("#request-list", DataTable)
                self._select_row(table.cursor_row)
            except Exception:
                pass

    def _open_context_menu(self, x: int, y: int) -> None:
        """Контекстное меню для строки в таблице HTTP History."""
        selected_host = self._get_selected_host_sync()
        proxy = self._get_proxy()
        in_scope = proxy.is_in_scope(selected_host) if (proxy and selected_host) else False
        scope_is_empty = not bool(proxy.scope) if proxy else True

        items = [
            ("send_repeater",  "Send to Repeater"),
            ("send_intruder",  "Send to Intruder"),
            ("send_scanner",   "Send to Scanner"),
            ("send_target",    "Send to Target"),
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
        """Raw HTTP из панели Request (HttpView#req-editor → TextArea#http-body)."""
        try:
            from textual.widgets import TextArea
            view = self.query_one("#req-editor", HttpView)
            area = view.query_one("#http-body", TextArea)
            return area.text or ""
        except Exception:
            return ""

    def _get_selected_host_sync(self) -> str:
        """Синхронно получить хост выбранного запроса из кэша."""
        # Сначала ищем по cursor_row (актуальнее чем _selected_req_id)
        try:
            table = self.query_one("#request-list", DataTable)
            row_idx = table.cursor_row
            if 0 <= row_idx < len(self._rows_cache):
                host = str(self._rows_cache[row_idx].get("host", ""))
                if host:
                    return host
        except Exception:
            pass
        # Запасной вариант — по _selected_req_id
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
        elif action == "send_target":
            self._send_to_target()
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
        """Добавить/убрать хост выбранного запроса из scope."""
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
                self.app.notify(f"★ {host} добавлен в scope", severity="information", timeout=2)
                self._sync_target_host_scope(host, True)
            else:
                self.app.notify(f"{host} уже в scope", timeout=2)
        else:
            if host in scope:
                scope.remove(host)
                proxy.set_scope(scope)
                self.app.notify(f"{host} убран из scope", severity="information", timeout=2)
                self._sync_target_host_scope(host, False)
            else:
                self.app.notify(f"{host} не в scope", timeout=2)
        # Обновить состояние кнопки ★ Scope в FilterBar
        try:
            from pentool.tui.widgets.filter_bar import FilterBar, ScopeToggle
            st = self.query_one("#filter-bar", FilterBar).query_one("#fb-scope", ScopeToggle)
            st.set_scope_empty(not bool(scope))
        except Exception:
            pass

    def _sync_target_host_scope(self, host: str, in_scope: bool) -> None:
        self.app.post_message(SyncScopeToTarget(host, in_scope))  # type: ignore[attr-defined]

    def _send_to_target(self) -> None:
        if self._selected_req_id is None:
            return
        self.run_worker(self._do_send_to_target())

    async def _do_send_to_target(self) -> None:
        if self._proxy_service is None or not self._proxy_service.is_storage_ready() or self._selected_req_id is None:
            return
        entry = await self._proxy_service.get_full_entry(self._selected_req_id)
        if entry is None:
            return
        from pentool.utils.parser import ParsedRequest
        parsed = ParsedRequest(
            method=entry.get("method", "GET"),
            url=entry.get("url", ""),
            headers=entry.get("request_headers") or {},
            body=entry.get("request_body", "") or "",
        )
        self.app.post_message(SendToTarget(parsed))
        self.app.notify("Added to Target", severity="information", timeout=2)

    def on_context_menu_item_selected(self, event: ContextMenu.ItemSelected) -> None:
        self._on_ctx_action(event.action)


"""Экран Intruder — автоматизированные атаки с payload'ами."""

from __future__ import annotations

import re
import asyncio
import time

from textual import on
from textual import events as _tevents
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widget import Widget
from pathlib import Path

_CSS = (Path(__file__).parent / "screen.tcss").read_text(encoding="utf-8")

from textual.widgets import (
    Button,
    Checkbox,
    DataTable,
    Input,
    Label,
    ListView,
    ListItem,
    ProgressBar,
    Select,
    Static,
    TextArea,
)

from pentool.api.intruder_api import AttackType, IntruderAttack, IntruderConfig, IntruderResult, count_markers, generate_numeric_payloads, process_payload
from pentool.tui.messages import SendToRepeater
from pentool.tui.mixins.app_mixin import AppMixin
from pentool.tui.widgets.resize_handle import ResizeHandle
from pentool.tui.widgets.toolbar_button import ToolbarButton
from pentool.tui.widgets.request_editor import _build_http_highlights, _load_into_textarea
from pentool.core.logging import get_logger

logger = get_logger(__name__)

# Модульные константы
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

class IntruderScreen(AppMixin, Widget):
    """Экран модуля Intruder."""

    DEFAULT_CSS = _CSS

    BINDINGS = [
        Binding("ctrl+j", "start_attack", "Start Attack", show=False),
        Binding("ctrl+p", "toggle_pause", "Pause/Resume", show=False),
    ]

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._payloads: list[list[str]] = [[]]
        self._active_set_idx: int = 0
        self._attack_type: AttackType = AttackType.SNIPER
        self._api = None
        self._all_results: list[IntruderResult] = []
        self._filter_status: str | None = None
        self._filter_len_gt: int | None = None
        self._filter_len_lt: int | None = None
        self._sort_col: str | None = None
        self._sort_reverse: bool = False
        self._running: bool = False
        self._paused: bool = False
        # Grep Match/Extract (Блок 4.4)
        self._grep_match_patterns: list[str] = []   # паттерны для маркировки строк
        self._grep_extract_patterns: list[str] = [] # паттерны для извлечения значений
        # Сохранённое выделение в template-editor (для ADD §§ после потери фокуса)
        self._last_editor_selection: tuple | None = None
        self._last_click_time: float = 0.0

    async def on_event(self, event: _tevents.Event) -> None:
        """Двойной клик в template-editor — выделить слово под курсором."""
        if isinstance(event, _tevents.MouseDown) and event.button == 1 and not event.ctrl:
            now = time.monotonic()
            if (now - self._last_click_time) < 0.4:
                self._last_click_time = 0.0
                await super().on_event(event)
                try:
                    from textual.widgets.text_area import Selection
                    area = self.query_one("#template-editor", TextArea)
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
                except Exception:
                    pass
                return
            self._last_click_time = now
        await super().on_event(event)

    def compose(self) -> ComposeResult:
        with Horizontal(id="toolbar"):
            yield ToolbarButton("▶ Start", "btn-start")
            yield Static(" │ ", classes="toolbar-sep")
            yield ToolbarButton("⏸ Pause", "btn-pause", classes="disabled")
            yield Static(" │ ", classes="toolbar-sep")
            yield ToolbarButton("■ Stop",  "btn-stop",  classes="disabled")
            yield Static(" │ ", classes="toolbar-sep")
            yield ToolbarButton("Clear results", "btn-clear-results")
            yield Static(" │ ", classes="toolbar-sep")
            yield ToolbarButton("Export CSV", "btn-export-csv")
            yield Static(" │ ", classes="toolbar-sep")
            yield Label("Threads:", classes="toolbar-label")
            yield Input("10", id="input-threads", placeholder="10", compact=True, type="integer")
            yield Label("Delay(ms):", classes="toolbar-label")
            yield Input("0",  id="input-delay",   placeholder="0",  compact=True, type="integer")

        with Horizontal(id="top-area"):
            yield from self._compose_positions()
            yield ResizeHandle("positions-panel", "payloads-panel", id="resize-pos-pay")
            yield from self._compose_payloads()

        yield ResizeHandle("top-area", "results-area", vertical=True, id="resize-top-results")

        yield from self._compose_results()

    def _compose_positions(self) -> ComposeResult:
        with Vertical(id="positions-panel"):
            yield Static("Positions", classes="section-title")
            with Horizontal(id="positions-toolbar"):
                yield Label("Attack:", classes="pos-label")
                yield ToolbarButton("Sniper ▼", "btn-attack-type")
                yield Static(" │ ", classes="toolbar-sep")
                yield ToolbarButton("Add §§",    "btn-add-marker")
                yield ToolbarButton("Clear §§",  "btn-clear-markers")
                yield Static(" │ ", classes="toolbar-sep")
                yield ToolbarButton("Auto §§",   "btn-mark-params")
                yield Static(" │ ", classes="toolbar-sep")
                yield Static(
                    _ATTACK_DESCRIPTIONS[AttackType.SNIPER],
                    id="attack-type-desc",
                )
            yield TextArea(
                "GET / HTTP/1.1\r\nHost: example.com\r\n\r\n",
                id="template-editor",
                language=None,
            )

    def _compose_payloads(self) -> ComposeResult:
        with Vertical(id="payloads-panel"):
            yield Static("Payloads", classes="section-title")
            with Horizontal(id="payloads-toolbar"):
                yield Label("Payload set:")
                yield ToolbarButton("Set 1 ▼", "btn-payload-set")
            with Horizontal(id="payload-buttons"):
                yield ToolbarButton("Add",           "btn-payload-add")
                yield ToolbarButton("Remove",        "btn-payload-remove")
                yield ToolbarButton("Clear",         "btn-payload-clear")
                yield ToolbarButton("Load from file…", "btn-payload-load")
                yield ToolbarButton("Generate…",     "btn-payload-generate")
                yield ToolbarButton("🧠 Smart…",     "btn-payload-smart", classes="pro-locked")
            yield ListView(id="payload-list")
            with Horizontal(id="processing-bar"):
                yield Label("Processing:")
                yield Checkbox("URL encode",  id="proc-url-encode",  value=False)
                yield Checkbox("Base64",      id="proc-base64",      value=False)
                yield Checkbox("HTML encode", id="proc-html-encode", value=False)
                yield Checkbox("MD5",         id="proc-md5",         value=False)

    def _compose_results(self) -> ComposeResult:
        with Vertical(id="results-area"):
            # Filters above the table (like HttpHistory)
            with Horizontal(id="results-filter-bar"):
                yield Label("Status:")
                yield Input(id="filter-status", placeholder="e.g. 200", compact=True)
                yield Label("Length >")
                yield Input(id="filter-len-gt", placeholder="0", compact=True)
                yield Label("<")
                yield Input(id="filter-len-lt", placeholder="∞", compact=True)
                yield Button("Apply", id="btn-filter-apply")
                yield Button("Reset filters", id="btn-filter-reset")
            with Horizontal(id="grep-bar"):
                yield Label("Grep:")
                yield Input(id="grep-match-input", placeholder="regex — highlight matching rows", compact=True)
                yield Label("Extract:")
                yield Input(id="grep-extract-input", placeholder="regex — add column with extracted value", compact=True)
                yield Button("Apply", id="btn-grep-apply")
                yield Button("Clear grep", id="btn-grep-clear")
            with Horizontal(id="results-toolbar"):
                pass
            with Horizontal(id="progress-row"):
                yield ProgressBar(total=100, id="attack-progress", show_eta=False)
                yield Static("0/0 (0%)", id="progress-label")
            yield DataTable(
                id="results-table",
                cursor_type="row",
                zebra_stripes=True,
            )

        yield Static(
            "Ctrl+J: Start Attack  │  Ctrl+P: Pause/Resume  │  M: Context menu",
            id="status-bar",
        )

    def on_mount(self) -> None:
        table = self.query_one("#results-table", DataTable)
        table.add_column("#",          width=5)
        table.add_column("Payload(s)", width=45)
        table.add_column("Status",     width=8)
        table.add_column("Length",     width=10)
        table.add_column("Time(ms)",   width=10)
        table.add_column("Error",      width=30)
        self._update_payload_select()
        self._setup_tooltips()

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
            except Exception:
                pass

    @on(ToolbarButton.Pressed, "#btn-start")
    def on_btn_start(self, _: ToolbarButton.Pressed) -> None:
        logger.info("INTRUDER: btn-start pressed")
        self.app.notify("▶ Starting attack…", timeout=2)
        self.action_start_attack()

    @on(ToolbarButton.Pressed, "#btn-pause")
    def on_btn_pause(self, _: ToolbarButton.Pressed) -> None:
        self.action_toggle_pause()

    @on(ToolbarButton.Pressed, "#btn-stop")
    def on_btn_stop(self, _: ToolbarButton.Pressed) -> None:
        self.action_stop_attack()

    @on(ToolbarButton.Pressed, "#btn-clear-results")
    def on_btn_clear_results(self, _: ToolbarButton.Pressed) -> None:
        self._clear_results()

    @on(ToolbarButton.Pressed, "#btn-export-csv")
    def on_btn_export_csv(self, _: ToolbarButton.Pressed) -> None:
        self._export_csv()

    @on(TextArea.SelectionChanged, "#template-editor")
    def on_template_selection_changed(self, event: TextArea.SelectionChanged) -> None:
        """Запомнить выделение в template-editor.

        При start==end (курсор без выделения) НЕ затираем сохранённое выделение
        сразу — первый такой event может быть сбросом при клике на кнопку ADD.
        Сбрасываем только если пришло два подряд start==end (пользователь кликнул
        в редакторе для снятия выделения).
        """
        sel = event.selection
        if sel.start != sel.end:
            # Реальное выделение — сохраняем, сбрасываем счётчик
            self._last_editor_selection = (sel.start, sel.end)
            self._cursor_only_count = 0
        else:
            self._cursor_only_count = getattr(self, "_cursor_only_count", 0) + 1
            if self._cursor_only_count >= 2:
                # Два cursor-only события подряд — пользователь снял выделение
                self._last_editor_selection = None

    @on(ToolbarButton.Pressed, "#btn-add-marker")
    def on_btn_add_marker(self, _: ToolbarButton.Pressed) -> None:
        self._add_marker_around_selection()

    @on(ToolbarButton.Pressed, "#btn-clear-markers")
    def on_btn_clear_markers(self, _: ToolbarButton.Pressed) -> None:
        self._clear_markers()

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

    @on(ToolbarButton.Pressed, "#btn-mark-params")
    def on_btn_mark_params(self, _: ToolbarButton.Pressed) -> None:
        self._mark_all_params()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        bid = event.button.id
        if bid == "btn-filter-apply":
            self._apply_filter()
        elif bid == "btn-filter-reset":
            self._reset_filter()
        elif bid in ("btn-export-csv-results", "btn-export-csv"):
            self._export_csv()
        elif bid == "btn-grep-apply":
            self._apply_grep()
        elif bid == "btn-grep-clear":
            self._clear_grep()

    def on_select_changed(self, event) -> None:
        # Оставлен для совместимости — теперь Select не используется
        pass

    def _open_attack_type_menu(self, btn: ToolbarButton) -> None:
        items = [
            (at.value, ("✓ " if at == self._attack_type else "  ") + label)
            for at, label in _ATTACK_LABELS.items()
        ]
        r = btn.region
        x = r.x
        y = r.y + 1

        screen = self  # явная ссылка на экран

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
                except Exception:
                    pass
                screen._update_payload_select()
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
                self.query_one("#btn-payload-set", ToolbarButton).label = (
                    f"Set {idx+1} ▼"
                )
                self._refresh_payload_list()
                self._highlight_nth_marker(idx)
            except Exception:
                pass

        self.app.show_context_menu(items, x, y, callback=_on_select)

    def _add_marker_around_selection(self) -> None:
        """Обернуть выделенный текст в §...§ маркеры."""
        try:
            editor = self.query_one("#template-editor", TextArea)
            text = editor.text

            # Используем сохранённое выделение (фокус мог уйти при клике на кнопку)
            if self._last_editor_selection is not None:
                raw_start, raw_end = self._last_editor_selection
            else:
                sel = editor.selection
                raw_start, raw_end = sel.start, sel.end


            # Нормализуем порядок — выделение может идти справа налево
            start, end = (raw_start, raw_end) if raw_start <= raw_end else (raw_end, raw_start)

            # Переводим (row, col) в offset
            lines = text.split("\n")

            def to_offset(row: int, col: int) -> int:
                return sum(len(lines[i]) + 1 for i in range(row)) + col

            s = to_offset(*start)
            e = to_offset(*end)

            if s == e:
                # Нет выделения — вставить §§ в позицию курсора
                new_text = text[:s] + "§§" + text[s:]
            else:
                new_text = text[:s] + "§" + text[s:e] + "§" + text[e:]

            editor.load_text(new_text)
            _load_into_textarea(editor, new_text, ["§"])
            editor.move_cursor(start)
            self._update_payload_select()
        except Exception as exc:
            self.app.notify(f"ADD error: {exc}", severity="error", timeout=5)

    def _clear_markers(self) -> None:
        try:
            editor = self.query_one("#template-editor", TextArea)
            text = editor.text
            cleaned = re.sub(r"§([^§]*)§", r"\1", text)
            cleaned = cleaned.replace("§", "")
            editor.load_text(cleaned)
            self._update_payload_select()
        except Exception:
            pass

    def _mark_all_params(self) -> None:
        """Автоматически пометить все параметры URL и тела запроса маркерами §§."""
        try:
            editor = self.query_one("#template-editor", TextArea)
            text = editor.text
        except Exception:
            return

        if not text:
            return

        lines = text.split("\n")
        if not lines:
            return

        def _mark_query_params(line: str) -> str:
            """Маркировать значения query параметров: key=value → key=§value§"""
            def mark_val(m: re.Match) -> str:
                key = m.group(1)
                val = m.group(2)
                # Не маркируем уже маркированные
                if "§" in val:
                    return m.group(0)
                return f"{key}=§{val}§"
            # Маркируем в query string (после ? или между &)
            # Разделяем строку на часть до ? и после
            if "?" in line:
                pre, qs = line.split("?", 1)
                # Парсим query string вручную через re
                qs_marked = re.sub(r"([^&=\s]+)=([^&\s§]+)", mark_val, qs)
                return f"{pre}?{qs_marked}"
            return line

        # Маркируем первую строку (request line: GET /path?params HTTP/1.1)
        if lines:
            lines[0] = _mark_query_params(lines[0])

        # Ищем тело запроса (после пустой строки)
        body_start_idx = None
        for i, line in enumerate(lines):
            if line.strip() == "" and i > 0:
                body_start_idx = i + 1
                break

        # Маркируем тело (application/x-www-form-urlencoded)
        # Проверим Content-Type заголовок
        content_type = ""
        for line in lines[1:]:
            if line.strip() == "":
                break
            if line.lower().startswith("content-type:"):
                content_type = line.split(":", 1)[1].strip().lower()

        if body_start_idx is not None and "urlencoded" in content_type:
            for i in range(body_start_idx, len(lines)):
                if lines[i].strip():
                    def mark_val_body(m: re.Match) -> str:
                        key = m.group(1)
                        val = m.group(2)
                        if "§" in val:
                            return m.group(0)
                        return f"{key}=§{val}§"
                    lines[i] = re.sub(r"([^&=\s]+)=([^&\s§]+)", mark_val_body, lines[i])

        # Cookie заголовок — маркируем значения
        for i, line in enumerate(lines):
            if line.lower().startswith("cookie:"):
                prefix = line[:7]  # "Cookie:"
                rest = line[7:]
                def mark_cookie_val(m: re.Match) -> str:
                    key = m.group(1)
                    val = m.group(2)
                    if "§" in val:
                        return m.group(0)
                    return f"{key}=§{val}§"
                lines[i] = prefix + re.sub(r"([^;=\s]+)=([^;§\s]+)", mark_cookie_val, rest)

        new_text = "\n".join(lines)
        try:
            editor.load_text(new_text)
            self._update_payload_select()
            n = new_text.count("§") // 2
            self.app.notify(f"Marked {n} parameter(s)", timeout=2)
            # Подсветить первую позицию (Set 1) сразу после автомаркировки
            self._highlight_nth_marker(self._active_set_idx)
        except Exception:
            pass

    def _update_payload_select(self) -> None:
        """Синхронизировать кнопку «Set N» и список payload'ов с текущим состоянием."""
        # 1) Сколько позиций в шаблоне — столько наборов нужно
        try:
            template = self.query_one("#template-editor", TextArea).text
        except Exception:
            template = ""
        n = max(1, count_markers(template))
        while len(self._payloads) < n:
            self._payloads.append([])

        # 2) Фиксируем индекс активного набора
        idx = min(self._active_set_idx, n - 1)
        self._active_set_idx = idx

        # 3) Обновляем кнопку выбора набора
        try:
            self.query_one("#btn-payload-set", ToolbarButton).label = f"Set {idx+1} ▼"
        except Exception:
            pass

        # 4) Обновляем список payload'ов
        self._refresh_payload_list()

    def _refresh_payload_list(self) -> None:
        try:
            lv = self.query_one("#payload-list", ListView)
            lv.clear()
            payloads = (
                self._payloads[self._active_set_idx]
                if self._active_set_idx < len(self._payloads)
                else []
            )
            for p in payloads:
                lv.append(ListItem(Label(p)))
        except Exception:
            pass

    def _highlight_nth_marker(self, n: int) -> None:
        """Выделить N-ю пару §...§ в TextArea редакторе позиций."""
        try:
            from textual.widgets.text_area import Selection
            editor = self.query_one("#template-editor", TextArea)
            text = editor.text
            lines = text.split("\n")

            def to_rowcol(offset: int):
                """Конвертировать offset в (row, col)."""
                row = 0
                for line in lines:
                    line_len = len(line) + 1  # +1 за \n
                    if offset < line_len:
                        return (row, offset)
                    offset -= line_len
                    row += 1
                return (row, 0)

            # Найти все пары §...§
            pairs = []
            i = 0
            while i < len(text):
                s = text.find("§", i)
                if s == -1:
                    break
                e = text.find("§", s + 1)
                if e == -1:
                    break
                pairs.append((s, e + 1))  # включаем закрывающий §
                i = e + 1

            if n < len(pairs):
                s_off, e_off = pairs[n]
                start_rc = to_rowcol(s_off)
                end_rc = to_rowcol(e_off)
                editor.selection = Selection(start_rc, end_rc)
        except Exception:
            pass

    def _add_payload_manual(self) -> None:
        def _on_add(value: str) -> None:
            while self._active_set_idx >= len(self._payloads):
                self._payloads.append([])
            self._payloads[self._active_set_idx].append(value)
            self._refresh_payload_list()

        self.app.push_screen(_InputDialog("Add payload", "Enter payload value:", on_add=_on_add))

    def _remove_selected_payload(self) -> None:
        try:
            lv = self.query_one("#payload-list", ListView)
            idx = lv.index
            if idx is not None and self._active_set_idx < len(self._payloads):
                payloads = self._payloads[self._active_set_idx]
                if 0 <= idx < len(payloads):
                    payloads.pop(idx)
                    self._refresh_payload_list()
        except Exception:
            pass

    def _clear_payloads(self) -> None:
        if self._active_set_idx < len(self._payloads):
            self._payloads[self._active_set_idx] = []
            self._refresh_payload_list()

    def _load_payloads_from_file(self) -> None:
        from pentool.tui.dialogs.file_selector import FileSelectorDialog, FileSelectorMode
        # Захватываем текущий индекс ДО открытия диалога
        captured_idx = self._active_set_idx

        def _on_file(path: str | None) -> None:
            if path:
                self.run_worker(
                    self._load_file_async(path, captured_idx),
                    exclusive=False,
                    name="payload-load",
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
        """Асинхронная загрузка payload-файла (не блокирует TUI)."""
        payloads: list[str] = []
        try:
            # Читаем файл в executor, чтобы не блокировать event loop
            loop = asyncio.get_running_loop()
            content = await loop.run_in_executor(None, self._read_file_sync, path)
            lines = content.splitlines()
            for line in lines:
                line = line.strip()
                if line and not line.startswith("#"):
                    payloads.append(line)
        except Exception as exc:
            self.app.notify(f"Failed to load: {exc}", severity="error", timeout=4)
            return

        while target_idx >= len(self._payloads):
            self._payloads.append([])
        self._payloads[target_idx].extend(payloads)
        # Обновляем UI только если загружали в активный сет
        if target_idx == self._active_set_idx:
            self._refresh_payload_list()
        name = path.split("/")[-1]
        self.app.notify(f"Loaded {len(payloads)} payloads from {name}", timeout=3)

    @staticmethod
    def _read_file_sync(path: str) -> str:
        """Синхронное чтение файла (запускается в executor)."""
        return Path(path).read_text(encoding="utf-8", errors="replace")

    def _open_generate_dialog(self) -> None:
        self.app.push_screen(_GenerateDialog(), self._on_payloads_generated)

    def _on_payloads_generated(self, payloads: list[str] | None) -> None:
        if payloads:
            while self._active_set_idx >= len(self._payloads):
                self._payloads.append([])
            self._payloads[self._active_set_idx].extend(payloads)
            self._refresh_payload_list()
            self.app.notify(f"Generated {len(payloads)} payloads", timeout=2)

    def _open_smart_payloads_dialog(self) -> None:
        from pentool.core.license import get_session_license
        info = get_session_license()
        if not info.has_feature("payloads_pro"):
            self.app.notify(  # type: ignore[attr-defined]
                "🔒 Smart Payloads requires PRO license — go to Settings → License",
                severity="warning",
                timeout=4,
            )
            return
        self.app.push_screen(_SmartPayloadsDialog(), self._on_smart_payloads_generated)  # type: ignore[attr-defined]

    def _on_smart_payloads_generated(self, payloads: list[str] | None) -> None:
        if payloads:
            while self._active_set_idx >= len(self._payloads):
                self._payloads.append([])
            self._payloads[self._active_set_idx].extend(payloads)
            self._refresh_payload_list()
            self.app.notify(f"🧠 Smart: added {len(payloads)} payloads", timeout=3)  # type: ignore[attr-defined]

    def action_start_attack(self) -> None:
        logger.info("INTRUDER: action_start_attack called, _running=%s", self._running)
        if self._running:
            logger.info("INTRUDER: already running, skip")
            return
        try:
            template = self.query_one("#template-editor", TextArea).text
            logger.info("INTRUDER: template len=%d", len(template))
        except Exception as e:
            logger.error("INTRUDER: cannot get template: %s", e)
            return
        if not template.strip():
            self.app.notify("Template is empty", severity="warning", timeout=3)
            return
        logger.info("INTRUDER: action_start_attack: attack_type=%s", self._attack_type)

        processing_ops = self._get_processing_ops()
        payload_sets = []
        for ps in self._payloads:
            processed = [
                self._apply_processing(p, processing_ops) for p in ps
            ] if ps else [""]
            payload_sets.append(processed)

        logger.info("INTRUDER: payload_sets=%s", [[len(p) for p in ps] for ps in payload_sets])
        if not any(ps for ps in payload_sets):
            self.app.notify("No payloads configured", severity="warning", timeout=3)
            return

        try:
            threads = int(self.query_one("#input-threads", Input).value or "10")
            threads = max(1, min(threads, 200))
        except Exception:
            threads = 10
        try:
            delay_ms = int(self.query_one("#input-delay", Input).value or "0")
            delay_ms = max(0, delay_ms)
        except Exception:
            delay_ms = 0

        config = IntruderConfig(
            template=template,
            attack_type=self._attack_type,
            payload_sets=payload_sets,
            threads=threads,
            delay_ms=delay_ms,
            follow_redirects=False,
            timeout=30,
        )

        from pentool.api.intruder_api import IntruderAPI
        db_path = self._get_db_path()
        self._api = IntruderAPI(db_path=db_path)

        self._running = True
        self._all_results = []
        self._clear_results()
        self._set_running_state(True)

        total_payloads = sum(len(ps) for ps in payload_sets)
        self.app.notify(f"Attack started: {total_payloads} payload(s)", timeout=3)
        self.run_worker(self._run_attack(config), exclusive=True, name="intruder-attack")

    async def _run_attack(self, config: IntruderConfig) -> None:
        attack = IntruderAttack(config, db_path=self._get_db_path())
        self._current_attack = attack

        logger.info("INTRUDER: _run_attack started, type=%s", config.attack_type)

        def on_result(result: IntruderResult) -> None:
            self._on_result(result)

        def on_progress(done: int, total: int) -> None:
            self._on_progress(done, total)

        try:
            await attack.run(on_result, on_progress)
        except Exception as exc:
            logger.error("INTRUDER: _run_attack error: %s", exc, exc_info=True)
            self.app.notify(f"Attack error: {exc}", severity="error", timeout=5)
        finally:
            self._running = False
            logger.info("INTRUDER: _run_attack finished, results=%d", len(self._all_results))
            self._set_running_state(False)
            self.app.notify(
                f"Attack finished: {len(self._all_results)} requests",
                severity="information", timeout=4,
            )

    def _on_result(self, result: IntruderResult) -> None:
        self._all_results.append(result)
        if self._passes_filter(result):
            self._add_result_row(result)

    def _on_progress(self, done: int, total: int) -> None:
        try:
            pb = self.query_one("#attack-progress", ProgressBar)
            if done == 0:
                # Первый вызов — инициализируем total
                pb.update(total=max(1, total), progress=0)
            else:
                pb.advance(done - pb.progress)
        except Exception:
            pass
        try:
            pct = f"{done / total * 100:.1f}%" if total > 0 else "0%"
            self.query_one("#progress-label", Static).update(f"{done}/{total} ({pct})")
        except Exception:
            pass

    def action_toggle_pause(self) -> None:
        if not self._running:
            return
        attack = getattr(self, "_current_attack", None)
        if attack is None:
            return
        if self._paused:
            self.run_worker(attack.resume())
            self._paused = False
            self.app.notify("Resumed", timeout=2)
        else:
            self.run_worker(attack.pause())
            self._paused = True
            self.app.notify("Paused", timeout=2)

    def action_stop_attack(self) -> None:
        attack = getattr(self, "_current_attack", None)
        if attack:
            self.run_worker(attack.stop())
        self._running = False
        self._paused = False
        self._set_running_state(False)
        self.app.notify("Attack stopped", severity="warning", timeout=3)

    def _set_running_state(self, running: bool) -> None:
        try:
            self.query_one("#btn-start", ToolbarButton).disabled = running
            self.query_one("#btn-pause", ToolbarButton).disabled = not running
            self.query_one("#btn-stop",  ToolbarButton).disabled = not running
        except Exception:
            pass

    def _add_result_row(self, result: IntruderResult) -> None:
        try:
            table = self.query_one("#results-table", DataTable)
            payloads_str = " | ".join(result.payload_values)
            if len(payloads_str) > 40:
                payloads_str = payloads_str[:37] + "…"

            # Grep Extract: извлекаем значение из request_raw по первому паттерну
            extract_val = ""
            if self._grep_extract_patterns:
                resp_body = getattr(result, "request_raw", "") or ""
                for pat in self._grep_extract_patterns:
                    try:
                        m = re.search(pat, resp_body)
                        if m:
                            extract_val = m.group(1) if m.lastindex else m.group(0)
                            extract_val = extract_val[:30]
                            break
                    except re.error:
                        pass

            # Grep Match: проверяем совпадение со строкой результата
            matched = False
            if self._grep_match_patterns:
                search_str = (
                    f"{result.response_status} {result.response_length} "
                    f"{' '.join(result.payload_values)}"
                )
                for pat in self._grep_match_patterns:
                    try:
                        if re.search(pat, search_str, re.IGNORECASE):
                            matched = True
                            break
                    except re.error:
                        pass

            status_str = str(result.response_status or "-")
            # Highlight matched rows
            if matched:
                status_str = f"[bold yellow]{status_str}✓[/bold yellow]"

            row = [
                str(result.request_number),
                payloads_str,
                status_str,
                str(result.response_length or "-"),
                str(result.response_time_ms or "-"),
                result.error or "",
            ]
            # Добавляем колонку Extract если паттерн задан
            if self._grep_extract_patterns:
                row.append(extract_val)

            table.add_row(*row, key=result.id)
        except Exception:
            pass

    def _clear_results(self) -> None:
        try:
            self.query_one("#results-table", DataTable).clear()
        except Exception:
            pass
        self._all_results = []
        try:
            self.query_one("#progress-label", Static).update("0/0 (0%)")
            self.query_one("#attack-progress", ProgressBar).update(total=100)
        except Exception:
            pass

    def on_data_table_header_selected(self, event: DataTable.HeaderSelected) -> None:
        if event.data_table.id != "results-table":
            return
        _col_names = ["#", "Payload(s)", "Status", "Length", "Time(ms)", "Error"]
        col_name = _col_names[event.column_index] if event.column_index < len(_col_names) else ""
        if not col_name:
            return
        self._sort_reverse = (self._sort_col == col_name) and not self._sort_reverse
        self._sort_col = col_name
        event.data_table.sort(col_name, reverse=self._sort_reverse)

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
            table = self.query_one("#results-table", DataTable)
            cursor_row = table.cursor_row
            if 0 <= cursor_row < len(self._all_results):
                result = self._all_results[cursor_row]
                self.app.post_message(SendToRepeater(result.request_raw))  # type: ignore[attr-defined]
        except Exception:
            pass

    def _send_selected_to_scanner(self) -> None:
        try:
            from pentool.tui.messages import SendHostToScanner
            table = self.query_one("#results-table", DataTable)
            cursor_row = table.cursor_row
            if 0 <= cursor_row < len(self._all_results):
                result = self._all_results[cursor_row]
                # Парсим URL из raw request
                raw = result.request_raw or ""
                host = ""
                for line in raw.splitlines():
                    if line.lower().startswith("host:"):
                        host = line.split(":", 1)[1].strip()
                        break
                if host:
                    self.app.post_message(SendHostToScanner(host))  # type: ignore[attr-defined]
                    self.app.notify(f"Sent {host} to Scanner", timeout=2)
                else:
                    self.app.notify("Could not extract host from request", severity="warning")
        except Exception as exc:
            logger.debug("_send_selected_to_scanner: %s", exc)

    def _copy_selected_payload(self) -> None:
        try:
            table = self.query_one("#results-table", DataTable)
            cursor_row = table.cursor_row
            if 0 <= cursor_row < len(self._all_results):
                result = self._all_results[cursor_row]
                payload_str = " | ".join(result.payload_values)
                from pentool.utils.copy_as import copy_to_clipboard
                copy_to_clipboard(payload_str)
                self.app.notify("Payload copied", timeout=2)
        except Exception:
            pass

    def _apply_filter(self) -> None:
        try:
            status_val = self.query_one("#filter-status", Input).value.strip()
            self._filter_status = status_val if status_val else None
        except Exception:
            self._filter_status = None
        try:
            gt_val = self.query_one("#filter-len-gt", Input).value.strip()
            self._filter_len_gt = int(gt_val) if gt_val else None
        except Exception:
            self._filter_len_gt = None
        try:
            lt_val = self.query_one("#filter-len-lt", Input).value.strip()
            self._filter_len_lt = int(lt_val) if lt_val else None
        except Exception:
            self._filter_len_lt = None
        self._redraw_results()

    def _reset_filter(self) -> None:
        self._filter_status = None
        self._filter_len_gt = None
        self._filter_len_lt = None
        try:
            self.query_one("#filter-status", Input).value = ""
            self.query_one("#filter-len-gt", Input).value = ""
            self.query_one("#filter-len-lt", Input).value = ""
        except Exception:
            pass
        self._redraw_results()

    def _apply_grep(self) -> None:
        """Применить Grep Match и Grep Extract паттерны."""
        try:
            match_val = self.query_one("#grep-match-input", Input).value.strip()
            self._grep_match_patterns = [match_val] if match_val else []
        except Exception:
            self._grep_match_patterns = []
        try:
            extract_val = self.query_one("#grep-extract-input", Input).value.strip()
            self._grep_extract_patterns = [extract_val] if extract_val else []
        except Exception:
            self._grep_extract_patterns = []
        self._redraw_results()
        n_match = len(self._grep_match_patterns)
        n_extract = len(self._grep_extract_patterns)
        self.app.notify(  # type: ignore[attr-defined]
            f"Grep Match: {n_match} pattern(s), Extract: {n_extract} pattern(s)",
            timeout=2,
        )

    def _clear_grep(self) -> None:
        """Сбросить Grep Match/Extract."""
        self._grep_match_patterns = []
        self._grep_extract_patterns = []
        try:
            self.query_one("#grep-match-input", Input).value = ""
            self.query_one("#grep-extract-input", Input).value = ""
        except Exception:
            pass
        self._redraw_results()

    def _passes_filter(self, result: IntruderResult) -> bool:
        if self._filter_status and str(result.response_status) != self._filter_status:
            return False
        length = result.response_length or 0
        if self._filter_len_gt is not None and length <= self._filter_len_gt:
            return False
        if self._filter_len_lt is not None and length >= self._filter_len_lt:
            return False
        return True

    def _redraw_results(self) -> None:
        try:
            self.query_one("#results-table", DataTable).clear()
        except Exception:
            pass
        for result in self._all_results:
            if self._passes_filter(result):
                self._add_result_row(result)

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
                attack = getattr(self, "_current_attack", None)
                if attack:
                    attack.export_csv(path)
                    self.app.notify(f"Exported to {path}", timeout=4)
            except Exception as exc:
                self.app.notify(f"Export failed: {exc}", severity="error", timeout=5)

        self.app.push_screen(
            FileSelectorDialog(mode=FileSelectorMode.SAVE, title="Save CSV"),
            _on_path,
        )

    def _get_processing_ops(self) -> list[str]:
        ops = []
        try:
            if self.query_one("#proc-url-encode", Checkbox).value:
                ops.append("url_encode")
            if self.query_one("#proc-base64", Checkbox).value:
                ops.append("base64_encode")
            if self.query_one("#proc-html-encode", Checkbox).value:
                ops.append("html_encode")
            if self.query_one("#proc-md5", Checkbox).value:
                ops.append("md5")
        except Exception:
            pass
        return ops

    def _apply_processing(self, payload: str, ops: list[str]) -> str:
        return process_payload(payload, ops)

    def load_request(self, raw: str) -> None:
        try:
            editor = self.query_one("#template-editor", TextArea)
            _load_into_textarea(editor, raw, ["§"])
            self._update_payload_select()
            self._highlight_nth_marker(self._active_set_idx)
        except Exception:
            pass


class _InputDialog(ModalScreen):
    """Диалог добавления payload'ов — не закрывается после ADD, накапливает список."""

    DEFAULT_CSS = _CSS

    def __init__(self, title: str, prompt: str, on_add=None, **kwargs) -> None:
        super().__init__(**kwargs)
        self._title = title
        self._prompt = prompt
        self._on_add = on_add  # callback(value: str) вызывается при каждом ADD

    def compose(self) -> ComposeResult:
        with Vertical(id="dialog"):
            yield Label(self._prompt, id="prompt-label")
            yield Input(id="input-value", placeholder="value...", compact=True)
            with Horizontal(id="buttons"):
                yield ToolbarButton("✔ Add",   "btn-ok")
                yield ToolbarButton("✕ Close", "btn-cancel")

    def on_mount(self) -> None:
        self.query_one("#input-value", Input).focus()

    @on(ToolbarButton.Pressed, "#btn-ok")
    def _ok(self, _: ToolbarButton.Pressed) -> None:
        self._do_add()

    @on(ToolbarButton.Pressed, "#btn-cancel")
    def _cancel(self, _: ToolbarButton.Pressed) -> None:
        self.dismiss(None)

    def _do_add(self) -> None:
        try:
            inp = self.query_one("#input-value", Input)
            value = inp.value.strip()
            if value and self._on_add:
                self._on_add(value)
                inp.value = ""
                inp.focus()
        except Exception:
            pass

    def on_key(self, event) -> None:
        if event.key == "escape":
            self.dismiss(None)
        elif event.key == "enter":
            self._do_add()

class _GenerateDialog(ModalScreen):
    DEFAULT_CSS = _CSS

    def compose(self) -> ComposeResult:
        with Vertical(id="dialog"):
            with Horizontal(classes="row"):
                yield Label("From:")
                yield Input("0", id="gen-start", compact=True)
            with Horizontal(classes="row"):
                yield Label("To:")
                yield Input("100", id="gen-end", compact=True)
            with Horizontal(classes="row"):
                yield Label("Step:")
                yield Input("1", id="gen-step", compact=True)
            with Horizontal(id="buttons"):
                yield ToolbarButton("✔ Generate", "btn-gen-ok")
                yield ToolbarButton("✕ Cancel",   "btn-gen-cancel")

    @on(ToolbarButton.Pressed, "#btn-gen-ok")
    def _gen_ok(self, _: ToolbarButton.Pressed) -> None:
        try:
            start = int(self.query_one("#gen-start", Input).value or "0")
            end   = int(self.query_one("#gen-end",   Input).value or "100")
            step  = int(self.query_one("#gen-step",  Input).value or "1")
            self.dismiss(generate_numeric_payloads(start, end, step))
        except Exception:
            self.dismiss(None)

    @on(ToolbarButton.Pressed, "#btn-gen-cancel")
    def _gen_cancel(self, _: ToolbarButton.Pressed) -> None:
        self.dismiss(None)

    def on_key(self, event) -> None:
        if event.key == "escape":
            self.dismiss(None)

class _SmartPayloadsDialog(ModalScreen[list[str] | None]):
    """PRO Smart Payload Generator — диалог генерации контекстных payload'ов."""

    DEFAULT_CSS = """
    _SmartPayloadsDialog {
        align: center middle;
    }
    _SmartPayloadsDialog #dialog {
        width: 60;
        height: 22;
        background: $surface;
        border: solid $primary;
        padding: 1 2;
    }
    _SmartPayloadsDialog #title-bar {
        height: 1;
        layout: horizontal;
        margin-bottom: 1;
    }
    _SmartPayloadsDialog #title-bar Static {
        width: 1fr;
        color: $primary;
    }
    _SmartPayloadsDialog #title-bar Button {
        width: 3;
        min-width: 3;
        background: transparent;
        border: none;
    }
    _SmartPayloadsDialog .row {
        height: auto;
        layout: horizontal;
        align: left middle;
        margin-bottom: 1;
    }
    _SmartPayloadsDialog .row Label {
        width: 14;
        color: $text-muted;
    }
    _SmartPayloadsDialog Select {
        width: 24;
    }
    _SmartPayloadsDialog Input {
        width: 10;
        background: $panel;
        border: none;
    }
    _SmartPayloadsDialog #buttons {
        height: auto;
        layout: horizontal;
        margin-top: 1;
        align: left middle;
    }
    _SmartPayloadsDialog #buttons Button {
        margin-right: 1;
    }
    """

    def compose(self) -> ComposeResult:
        with Vertical(id="dialog"):
            with Horizontal(id="title-bar"):
                yield Static("🧠 Smart Payload Generator (PRO)")
                yield Button("✕", id="btn-close-smart")
            with Horizontal(classes="row"):
                yield Label("Context:")
                yield Select(
                    [("String", "string"), ("Numeric", "numeric"), ("JSON", "json"),
                     ("XML", "xml"), ("URL", "url"), ("Cookie", "cookie"),
                     ("Header", "header"), ("Path", "path")],
                    id="smart-context", value="string",
                )
            with Horizontal(classes="row"):
                yield Label("Tech hint:")
                yield Select(
                    [("Unknown", "unknown"), ("PHP", "php"), ("Java", "java"),
                     ("Node.js", "node"), ("Python", "python"), (".NET", "dotnet")],
                    id="smart-tech", value="unknown",
                )
            with Horizontal(classes="row"):
                yield Label("WAF profile:")
                yield Select(
                    [("None", "none"), ("Generic", "generic"), ("Cloudflare", "cloudflare"),
                     ("ModSecurity", "modsec"), ("F5", "f5")],
                    id="smart-waf", value="none",
                )
            with Horizontal(classes="row"):
                yield Label("Count:")
                yield Input("50", id="smart-count", compact=True)
            with Horizontal(id="buttons"):
                yield Button("Generate", id="btn-smart-ok", variant="primary")
                yield Button("Cancel", id="btn-smart-cancel")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-smart-ok":
            try:
                from pentool.plugins.builtin.payloads_pro import generate_smart_payloads
                ctx = str(self.query_one("#smart-context", Select).value or "string")
                tech = str(self.query_one("#smart-tech", Select).value or "unknown")
                waf = str(self.query_one("#smart-waf", Select).value or "none")
                count = int(self.query_one("#smart-count", Input).value or "50")
                payloads = generate_smart_payloads(
                    context=ctx,  # type: ignore[arg-type]
                    tech_hint=tech,  # type: ignore[arg-type]
                    waf_profile=waf,  # type: ignore[arg-type]
                    count=max(1, min(count, 500)),
                )
                self.dismiss(payloads)
            except Exception:
                self.dismiss(None)
        elif event.button.id in ("btn-smart-cancel", "btn-close-smart"):
            self.dismiss(None)

    def on_key(self, event) -> None:
        if event.key == "escape":
            self.dismiss(None)

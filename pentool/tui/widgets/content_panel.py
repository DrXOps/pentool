"""ContentPanel — универсальный блок для RichLog/TextArea с панелью инструментов.

Заменяет ручные RichLog и TextArea с кнопками во всех экранах:
- RichLog: scan-log, recon-log, feed-log, ws-msg-log, detail-log,
  dec-steps-log, cmp-diff-log, seq-analysis-log, diff-panel-log, lightpanda-body
- TextArea: editor-area, viewer-area, http-body, dec-input/dec-output,
  cmp-left/cmp-right, scope-area, seq-token-area
"""

from __future__ import annotations

import time
from typing import ClassVar, Literal

from textual import on
from textual.containers import Horizontal, Vertical
from textual.message import Message
from textual.reactive import reactive
from textual.widget import Widget
from textual.widgets import RichLog, Static, TextArea

from pentool.tui.widgets.toolbar_button import ToolbarButton


class ContentPanel(Widget):
    """Блок-контейнер: RichLog или TextArea + панель кнопок в заголовке."""

    class CopyRequested(Message):
        """Запрос на копирование содержимого в буфер."""
        ALLOW_SELECTOR_MATCH = True
        def __init__(self, panel: "ContentPanel", text: str, selection: str | None = None) -> None:
            self.panel = panel
            self.text = text
            self.selection = selection  # выделенный текст, None = копировать всё
            super().__init__()

        @property
        def control(self) -> "ContentPanel":
            return self.panel

    class PasteRequested(Message):
        """Запрос на вставку из буфера."""
        ALLOW_SELECTOR_MATCH = True
        def __init__(self, panel: "ContentPanel") -> None:
            self.panel = panel
            super().__init__()

        @property
        def control(self) -> "ContentPanel":
            return self.panel

    class FormatToggleRequested(Message):
        """Запрос на переключение raw/formatted."""
        ALLOW_SELECTOR_MATCH = True
        def __init__(self, panel: "ContentPanel") -> None:
            self.panel = panel
            super().__init__()

        @property
        def control(self) -> "ContentPanel":
            return self.panel

    DEFAULT_CSS = """
    ContentPanel {
        height: auto;
        width: 1fr;
        border: solid $primary-darken-2;
        layout: vertical;
        margin: 0 0 1 0;
    }
    ContentPanel > .cp-title {
        height: 1;
        layout: horizontal;
        align: left middle;
        background: $primary-darken-3;
        padding: 0 1;
    }
    ContentPanel > .cp-title > Static {
        width: 1fr;
        height: 1;
        color: $text-muted;
        text-style: bold;
    }
    /* Кнопки в заголовке */
    ContentPanel > .cp-title > ToolbarButton {
        width: auto;
        min-width: 4;
        height: 1;
        padding: 0;
        background: transparent;
        border: none;
        pointer: pointer;
    }
    ContentPanel > .cp-title > ToolbarButton:focus {
        border: none;
    }
    ContentPanel > #cp-body {
        height: 1fr;
        min-height: 6;
    }
    ContentPanel RichLog {
        border: none;
        padding: 0 1;
        height: 1fr;
        min-height: 6;
    }
    ContentPanel RichLog:focus {
        border: none;
        outline: none;
    }
    ContentPanel TextArea {
        border: none;
        height: 1fr;
        min-height: 6;
    }
    ContentPanel TextArea:focus {
        border: none;
        outline: none;
    }
    """

    # ── Иконки (минималистичные unicode) ──────────────────────────────
    BUTTONS_COPY: ClassVar[str] = "⎙"
    BUTTONS_PASTE: ClassVar[str] = "⎘"
    BUTTONS_CLEAR: ClassVar[str] = "✕"
    BUTTONS_FORMAT: ClassVar[str] = "⇄"
    BUTTONS_WRAP: ClassVar[str] = "↩"
    BUTTONS_AUTOSCROLL: ClassVar[str] = "⬇"

    BUTTON_SCOPE: ClassVar[list[str]] = ["copy"]
    BUTTON_LABELS: ClassVar[dict[str, str]] = {
        "copy": BUTTONS_COPY,
        "paste": BUTTONS_PASTE,
        "clear": BUTTONS_CLEAR,
        "format": BUTTONS_FORMAT,
        "wrap": BUTTONS_WRAP,
        "autoscroll": BUTTONS_AUTOSCROLL,
    }

    _wrap_state: reactive[bool] = reactive(True)

    def __init__(
        self,
        title: str = "",
        *,
        widget_type: Literal["richlog", "textarea"] = "richlog",
        textarea_read_only: bool = False,
        textarea_language: str | None = None,
        textarea_soft_wrap: bool = True,
        wrap: bool = True,
        max_lines: int = 2000,
        initial_text: str = "",
        buttons: list[str] | None = None,
        **kwargs: object,
    ) -> None:
        super().__init__(**kwargs)
        self._panel_title = title
        self._widget_type = widget_type
        self._textarea_read_only = textarea_read_only
        self._textarea_language = textarea_language
        self._textarea_soft_wrap = textarea_soft_wrap
        self._wrap = wrap
        self._max_lines = max_lines
        self._initial_text = initial_text
        self._buttons = list(buttons) if buttons is not None else list(self.BUTTON_SCOPE)
        self._wrap_state = wrap

    def compose(self) -> ComposeResult:
        with Horizontal(classes="cp-title"):
            yield Static(self._panel_title)
            for bk in self._buttons:
                lbl = self.BUTTON_LABELS.get(bk, bk)
                if bk == "wrap":
                    yield ToolbarButton(
                        lbl if self._wrap_state else "╌",
                        f"cp-btn-{bk}",
                        classes="variant-success" if self._wrap_state else "variant-warning",
                    )
                else:
                    yield ToolbarButton(lbl, f"cp-btn-{bk}")
        with Vertical(id="cp-body"):
            if self._widget_type == "textarea":
                yield TextArea(
                    self._initial_text,
                    id="cp-body-widget",
                    read_only=self._textarea_read_only,
                    language=self._textarea_language,
                    soft_wrap=self._textarea_soft_wrap,
                )
            else:
                yield RichLog(
                    id="cp-body-widget",
                    highlight=True,
                    markup=True,
                    wrap=self._wrap,
                    max_lines=self._max_lines,
                )

    @property
    def content_widget(self) -> RichLog | TextArea:
        return self.query_one("#cp-body-widget")

    def get_text(self) -> str:
        w = self.content_widget
        if isinstance(w, TextArea):
            return w.text
        try:
            lines: list[str] = []
            for item in getattr(w, "lines", None) or []:
                t = getattr(item, "text", str(item))
                lines.append(str(t))
            return "\n".join(lines)
        except Exception:
            return ""

    def get_selected_text(self) -> str | None:
        """Вернуть выделенный текст из TextArea, или None если нет выделения."""
        w = self.content_widget
        if not isinstance(w, TextArea):
            return None
        sel = w.selection
        if sel is None:
            return None
        # selection.start/end — кортежи (row, col)
        if sel.start == sel.end:
            return None
        try:
            text = w.text
            lines = text.splitlines(keepends=True)
            def _flat(pos: tuple[int, int]) -> int:
                row, col = pos
                idx = sum(len(lines[r]) for r in range(row))
                return idx + col
            return text[_flat(sel.start):_flat(sel.end)]
        except Exception:
            return None

    def clear_content(self) -> None:
        w = self.content_widget
        if isinstance(w, TextArea):
            w.load_text("")
        else:
            w.clear()

    def set_title(self, title: str) -> None:
        """Обновить заголовок панели (Static в .cp-title)."""
        self._panel_title = title
        try:
            self.query_one(".cp-title > Static", Static).update(title)
        except Exception:
            pass

    def write_to_log(self, text: str) -> None:
        if self._widget_type == "richlog":
            self.content_widget.write(text)

    @on(ToolbarButton.Pressed)
    def on_cp_toolbar_button(self, event: ToolbarButton.Pressed) -> None:
        btn = event.button
        btn_id = btn.id or ""

        if btn_id == "cp-btn-copy":
            # Умное копирование: выделенное или всё
            sel_text = self.get_selected_text()
            if sel_text is not None:
                self.post_message(self.CopyRequested(self, sel_text, selection=sel_text))
            else:
                self.post_message(self.CopyRequested(self, self.get_text()))
        elif btn_id == "cp-btn-paste":
            self.post_message(self.PasteRequested(self))
        elif btn_id == "cp-btn-clear":
            self.clear_content()
        elif btn_id == "cp-btn-format":
            self.post_message(self.FormatToggleRequested(self))
        elif btn_id == "cp-btn-wrap":
            w = self.content_widget
            if isinstance(w, RichLog):
                self._wrap_state = not self._wrap_state
                w.wrap = self._wrap_state
                btn.label = self.BUTTONS_WRAP if self._wrap_state else "╌"
                btn.add_class(f"variant-{'success' if self._wrap_state else 'warning'}")
                btn.remove_class(f"variant-{'warning' if self._wrap_state else 'success'}")
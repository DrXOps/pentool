"""ContentPanel — универсальный блок для RichLog/TextArea с панелью инструментов.

Используется в проекте для:
- scan-log (Scanner PRO)
- recon-log (Recon PRO)
- feed-log (Dashboard)
- editor-area (Repeater/Intruder)
- viewer-area (Repeater)
- http-body (Proxy)
- viewer-area (Proxy)
- dec-steps-log (Decoder)
- diff-panel-log (DiffPanel)
- cmp-diff-log (Comparer)
- seq-analysis-log (Sequencer)
- lightpanda-body (LightpandaViewer)

Где:
- RichLog: многострочный скроллер/лог
- TextArea: редактор/просмотр содержимого
"""

from __future__ import annotations

import random
import string
import time
from pathlib import Path
from typing import ClassVar, Literal, Optional

from textual import on
from textual.containers import Horizontal, Vertical
from textual.message import Message
from textual.reactive import reactive
from textual.widget import Widget
from textual.widgets import RichLog, Static, TextArea


# =============================================================================
#  ToolbarButton — компактная кастомная кнопка
# =============================================================================

class ToolbarButton(Widget):
    """Кастомная кнопка: variant, disabled, compact."""

    class Pressed(Message):
        def __init__(self, button: "ToolbarButton") -> None:
            self.button = button
            super().__init__()

    def __init__(
        self,
        label: str = "",
        button_id: str = "",
        *,
        variant: str = "default",
        classes: str = "",
        disabled: bool = False,
    ):
        super().__init__()
        self._label = label
        self._variant = variant
        self._disabled = disabled
        if button_id:
            self.id = button_id
        if classes:
            self.classes = classes

    @property
    def label(self) -> str:
        return self._label

    @label.setter
    def label(self, val: str) -> None:
        self._label = val
        self.refresh()

    @property
    def variant(self) -> str:
        return self._variant

    @variant.setter
    def variant(self, val: str) -> None:
        self._variant = val
        self._update_css_classes()

    @property
    def disabled(self) -> bool:
        return self._disabled

    @disabled.setter
    def disabled(self, val: bool) -> None:
        self._disabled = val
        self._update_css_classes()

    def _update_css_classes(self) -> None:
        classes = set()
        if self._disabled:
            classes.add("disabled")
        if self._variant and self._variant != "default":
            classes.add(f"variant-{self._variant}")
        self.classes = " ".join(sorted(classes))
        self.refresh()

    def render(self) -> str:
        return self._label

    def on_click(self) -> None:
        if not self._disabled:
            self.post_message(self.Pressed(self))


# =============================================================================
#  ContentPanel — универсальный блок с RichLog/TextArea + панелью кнопок
# =============================================================================

class ContentPanel(Widget):
    """Блок-контейнер: RichLog или TextArea + панель кнопок."""

    class CopyRequested(Message):
        """Запрос на копирование содержимого в буфер."""
        def __init__(self, panel: "ContentPanel", text: str) -> None:
            self.panel = panel
            self.text = text
            super().__init__()

    class PasteRequested(Message):
        """Запрос на вставку из буфера."""
        def __init__(self, panel: "ContentPanel") -> None:
            self.panel = panel
            super().__init__()

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
    /* Кнопки в заголовке: рука-курсор, компактно, справа */
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
    /* RichLog внутри ContentPanel — без собственной рамки, рамка у панели */
    ContentPanel RichLog {
        border: none;
        padding: 0 1;
        height: 1fr;
        min-height: 6;
    }
    /* TextArea внутри ContentPanel */
    ContentPanel TextArea {
        border: none;
        height: 1fr;
        min-height: 6;
    }
    """

    BUTTONS_COPY: ClassVar[str] = "📋"
    BUTTONS_PASTE: ClassVar[str] = "📥"
    BUTTONS_CLEAR: ClassVar[str] = "✕"
    BUTTONS_WRAP: ClassVar[str] = "↩"
    BUTTONS_WRITE: ClassVar[str] = "✚"
    BUTTON_SCOPE: ClassVar[list[str]] = ["copy", "paste", "clear", "wrap", "write"]
    BUTTON_LABELS: ClassVar[dict[str, str]] = {
        "copy": BUTTONS_COPY,
        "paste": BUTTONS_PASTE,
        "clear": BUTTONS_CLEAR,
        "wrap": BUTTONS_WRAP,
        "write": BUTTONS_WRITE,
    }

    _wrap_state: reactive[bool] = reactive(True)

    def __init__(
        self,
        title: str = "",
        *,
        widget_type: Literal["richlog", "textarea"] = "richlog",
        textarea_read_only: bool = False,
        textarea_language: Optional[str] = None,
        textarea_soft_wrap: bool = True,
        wrap: bool = True,
        max_lines: int = 2000,
        initial_text: str = "",
        buttons: Optional[list[str]] = None,
    ) -> None:
        super().__init__()
        self._panel_title = title
        self._widget_type = widget_type
        self._textarea_read_only = textarea_read_only
        self._textarea_language = textarea_language
        self._textarea_soft_wrap = textarea_soft_wrap
        self._wrap = wrap
        self._max_lines = max_lines
        self._initial_text = initial_text
        self._buttons = buttons or list(self.BUTTON_SCOPE)
        self._wrap_state = wrap
        self._write_counter = 0

    def compose(self) -> ComposeResult:
        # Заголовок + кнопки в одной Horizontal
        with Horizontal(classes="cp-title"):
            yield Static(self._panel_title)
            # Кнопки справа
            for bk in self._buttons:
                lbl = self.BUTTON_LABELS.get(bk, bk)
                if bk == "wrap":
                    yield ToolbarButton(
                        lbl if self._wrap_state else "╌",
                        f"cp-btn-{bk}",
                        variant="default" if self._wrap_state else "warning",
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

    # -- доступ к виджету --
    @property
    def content_widget(self) -> RichLog | TextArea:
        return self.query_one("#cp-body-widget")

    # -- чтение текста --
    def get_text(self) -> str:
        w = self.content_widget
        if isinstance(w, TextArea):
            return w.text
        # RichLog — публичного get_text нет, пробуем lines/_lines
        try:
            lines: list[str] = []
            for item in getattr(w, "lines", None) or []:
                t = getattr(item, "text", str(item))
                lines.append(str(t))
            return "\n".join(lines)
        except Exception:
            return ""

    def clear_content(self) -> None:
        w = self.content_widget
        if isinstance(w, TextArea):
            w.load_text("")
        else:
            w.clear()

    def write_to_log(self, text: str) -> None:
        """Записать строку в RichLog (только для richlog)."""
        if self._widget_type == "richlog":
            self.content_widget.write(text)

    # -- хендлеры --

    @on(ToolbarButton.Pressed)
    def on_cp_toolbar_button(self, event: ToolbarButton.Pressed) -> None:
        btn = event.button
        btn_id = btn.id or ""

        if btn_id == "cp-btn-copy":
            self.post_message(self.CopyRequested(self, self.get_text()))

        elif btn_id == "cp-btn-paste":
            self.post_message(self.PasteRequested(self))

        elif btn_id == "cp-btn-clear":
            self.clear_content()

        elif btn_id == "cp-btn-wrap":
            w = self.content_widget
            if isinstance(w, RichLog):
                self._wrap_state = not self._wrap_state
                w.wrap = self._wrap_state
                if self._wrap_state:
                    btn.label = self.BUTTONS_WRAP
                    btn.variant = "default"
                else:
                    btn.label = "╌"
                    btn.variant = "warning"

        elif btn_id == "cp-btn-write":
            if self._widget_type == "richlog":
                self.write_to_log(
                    f"[dim]{time.strftime('%H:%M:%S')}[/dim]  "
                    f"[bold]line {self._write_counter + 1}[/bold]  "
                    f"Lorem ipsum"
                )
                self._write_counter += 1
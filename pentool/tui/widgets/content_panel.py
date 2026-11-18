"""ContentPanel — универсальный блок для RichLog/TextArea с панелью инструментов.

Заменяет ручные RichLog и TextArea с кнопками во всех экранах:
- RichLog: scan-log, recon-log, feed-log, ws-msg-log, detail-log,
  dec-steps-log, cmp-diff-log, seq-analysis-log, diff-panel-log, lightpanda-body
- TextArea: editor-area, viewer-area, http-body, dec-input/dec-output,
  cmp-left/cmp-right, scope-area, seq-token-area
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, ClassVar, Literal

from textual import on
from textual.containers import Horizontal, Vertical
from textual.css.query import NoMatches
from textual.message import Message
from textual.reactive import reactive
from textual.widget import Widget
from textual.widgets import RichLog, Static, TextArea

from pentool.core.logging import get_logger
from pentool.tui.markup import esc
from pentool.tui.widgets.toolbar_button import ToolbarButton

logger = get_logger(__name__)

if TYPE_CHECKING:
    from textual.app import ComposeResult


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

    DEFAULT_CSS = (Path(__file__).parent / "content_panel.tcss").read_text(encoding="utf-8")

    # ── Иконки (минималистичные unicode) ──────────────────────────────
    BUTTONS_COPY: ClassVar[str] = "cp"
    BUTTONS_PASTE: ClassVar[str] = "pst"
    BUTTONS_CLEAR: ClassVar[str] = "✕"
    BUTTONS_FORMAT: ClassVar[str] = "fmt"
    BUTTONS_SPECIAL: ClassVar[str] = "⏎"
    BUTTONS_WRAP: ClassVar[str] = "wrp"
    BUTTONS_AUTOSCROLL: ClassVar[str] = "end"

    BUTTON_SCOPE: ClassVar[list[str]] = ["copy"]
    BUTTON_LABELS: ClassVar[dict[str, str]] = {
        "copy": BUTTONS_COPY,
        "paste": BUTTONS_PASTE,
        "clear": BUTTONS_CLEAR,
        "format": BUTTONS_FORMAT,
        "special": BUTTONS_SPECIAL,
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
        with Horizontal(classes="cp-title panel-title"):
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

    @property
    def content_mounted(self) -> bool:
        """True once the body widget exists in the DOM.

        A panel is mounted before its children: ``req_panel.mount(editor)``
        returns while ``#cp-body-widget`` is still being composed. Code that
        loads text right after mounting must ask this first — ``load_raw``
        used to swallow the resulting ``NoMatches`` and leave the editor empty
        while its own ``_raw_full`` said the request was loaded.
        """
        return bool(len(self.query("#cp-body-widget")))

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

            return text[_flat(sel.start) : _flat(sel.end)]
        except Exception:
            return None

    def clear_content(self) -> None:
        w = self.content_widget
        if isinstance(w, TextArea):
            w.load_text("")
        else:
            w.clear()

    def set_title(self, title: str) -> None:
        """Обновить заголовок панели (Static в .cp-title).

        Заголовок всегда текст, не разметка: в него попадают имена файлов
        (могут содержать ``[``) и метки языка ответа в квадратных скобках
        (``[html]``, ``[json]``) — без экранирования Rich съедает их молча.
        """
        self._panel_title = title
        try:
            self.query_one(".cp-title > Static", Static).update(esc(title))
        except NoMatches as exc:
            # Заголовок на экране отстаёт от того, что реально загружено в
            # панель: две панели рядом выглядят одинаково.
            logger.debug("content panel: title %r not shown: %s", title, exc)

    def write_to_log(self, text: str) -> None:
        if self._widget_type == "richlog":
            self.content_widget.write(text)

    @on(ToolbarButton.Pressed)
    def on_cp_toolbar_button(self, event: ToolbarButton.Pressed) -> None:
        btn = event.button
        btn_id = btn.id or ""

        if btn_id == "cp-btn-copy":
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

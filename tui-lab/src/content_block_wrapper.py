"""ContentBlockWrapper — обертка контент-блока с обычными Button.

Сравнение на стенде:
- ContentPanel — существующая реализация с ToolbarButton
- ContentBlockWrapper — альтернатива с Panel + Button (textual.widgets)
"""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.message import Message
from textual.widget import Widget
from textual.widgets import Button, RichLog, Static, TextArea


class ContentBlockWrapper(Widget):
    """Обёртка: RichLog/TextArea + панель с обычными Button."""

    class Action(Message):
        """Клик по кнопке в панели."""
        ALLOW_SELECTOR_MATCH = True
        def __init__(self, wrapper: "ContentBlockWrapper", action: str) -> None:
            self.wrapper = wrapper
            self.action = action
            super().__init__()

        @property
        def control(self) -> "ContentBlockWrapper":
            return self.wrapper

    DEFAULT_CSS = """
    ContentBlockWrapper {
        width: 1fr;
        height: auto;
        layout: vertical;
        border: solid $secondary;
        margin: 0 0 1 0;
    }
    ContentBlockWrapper > .cbw-title {
        height: 1;
        layout: horizontal;
        align: left middle;
        background: $primary-darken-3;
        padding: 0 1;
    }
    ContentBlockWrapper > .cbw-title > Static {
        width: 1fr;
        height: 1;
        color: $text-muted;
        text-style: bold;
    }
    ContentBlockWrapper > .cbw-title > Button {
        width: auto;
        min-width: 6;
        height: 1;
        padding: 0 1;
        background: $panel;
        border: none;
    }
    ContentBlockWrapper > .cbw-title > Button:hover {
        background: $primary-darken-1;
    }
    ContentBlockWrapper > #cbw-body {
        height: 1fr;
        min-height: 6;
    }
    ContentBlockWrapper RichLog {
        border: none;
        padding: 0 1;
        height: 1fr;
        min-height: 6;
    }
    ContentBlockWrapper TextArea {
        border: none;
        height: 1fr;
        min-height: 6;
    }
    """

    def __init__(
        self,
        title: str = "",
        *,
        widget_type: str = "richlog",
        textarea_read_only: bool = False,
        textarea_language: str | None = None,
        textarea_soft_wrap: bool = True,
        wrap: bool = True,
        max_lines: int = 2000,
        initial_text: str = "",
        buttons: list[str] | None = None,
    ) -> None:
        super().__init__()
        self._title = title
        self._widget_type = widget_type
        self._textarea_read_only = textarea_read_only
        self._textarea_language = textarea_language
        self._textarea_soft_wrap = textarea_soft_wrap
        self._wrap = wrap
        self._max_lines = max_lines
        self._initial_text = initial_text
        self._buttons = buttons or ["📋", "✕"]

    def compose(self) -> ComposeResult:
        with Horizontal(classes="cbw-title"):
            yield Static(self._title)
            for btn_text in self._buttons:
                yield Button(btn_text)
        with Horizontal(id="cbw-body"):
            if self._widget_type == "textarea":
                yield TextArea(
                    self._initial_text,
                    id="cbw-body-widget",
                    read_only=self._textarea_read_only,
                    language=self._textarea_language,
                    soft_wrap=self._textarea_soft_wrap,
                )
            else:
                yield RichLog(
                    id="cbw-body-widget",
                    highlight=True,
                    markup=True,
                    wrap=self._wrap,
                    max_lines=self._max_lines,
                )

    @property
    def content_widget(self) -> RichLog | TextArea:
        return self.query_one("#cbw-body-widget")

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

    def write_to_log(self, text: str) -> None:
        if self._widget_type == "richlog":
            self.content_widget.write(text)

    def clear_content(self) -> None:
        w = self.content_widget
        if isinstance(w, TextArea):
            w.load_text("")
        else:
            w.clear()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        btn = event.button
        self.post_message(self.Action(self, btn.label or "?"))
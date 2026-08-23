"""SearchBar — search bar that appears on Ctrl+F."""

from __future__ import annotations

from pathlib import Path

from textual.app import ComposeResult
from textual.message import Message
from textual.widget import Widget
from textual.widgets import Button, Input, Label, Static

_CSS = (Path(__file__).parent / "search_bar.tcss").read_text(encoding="utf-8")


class SearchBar(Widget):
    """Search bar that appears on Ctrl+F over TextArea/RichLog.

    Usage:
        yield SearchBar(id="search-bar")

    Open:
        self.query_one(SearchBar).show()

    Close:
        self.query_one(SearchBar).hide()
    """

    DEFAULT_CSS = _CSS

    class Search(Message):
        """User entered a search query."""
        def __init__(self, query: str, regex: bool = False, direction: int = 1) -> None:
            super().__init__()
            self.query = query
            self.regex = regex
            self.direction = direction  # 1 = forward, -1 = backward

    class TargetToggle(Message):
        """User toggled search target (Req/Resp)."""
        def __init__(self) -> None:
            super().__init__()

    class Closed(Message):
        """Search bar closed."""

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._regex_enabled = False
        self._search_target: str = "request"  # "request" | "response"

    def compose(self) -> ComposeResult:
        yield Label("Find:")
        yield Input(placeholder="search...", id="search-input", compact=True)
        yield Static("Req", id="search-target-toggle", classes="search-target-req")
        yield Button("◀", id="btn-prev", variant="default")
        yield Button("▶", id="btn-next", variant="default")
        yield Static("Regex", id="search-regex-toggle")
        yield Static("", id="search-count")

    def show(self) -> None:
        self.display = True
        self.call_after_refresh(self._focus_input)

    def hide(self) -> None:
        self.display = False
        self.post_message(self.Closed())

    def _focus_input(self) -> None:
        try:
            self.query_one("#search-input", Input).focus()
        except Exception:
            pass

    def _fire_search(self, direction: int = 1) -> None:
        try:
            query = self.query_one("#search-input", Input).value
        except Exception:
            return
        if query:
            self.post_message(self.Search(query, self._regex_enabled, direction))

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id == "search-input":
            self._fire_search(1)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-next":
            self._fire_search(1)
        elif event.button.id == "btn-prev":
            self._fire_search(-1)

    def on_static_click(self, event) -> None:
        try:
            widget = event.widget
            wid = getattr(widget, "id", None)
            if wid == "search-regex-toggle":
                self._regex_enabled = not self._regex_enabled
                if self._regex_enabled:
                    widget.add_class("-active")
                else:
                    widget.remove_class("-active")
            elif wid == "search-target-toggle":
                self.toggle_target()
                self.post_message(self.TargetToggle())
        except Exception:
            pass

    def on_key(self, event) -> None:
        if event.key == "escape":
            self.hide()
            event.prevent_default()
        elif event.key == "enter":
            self._fire_search(1)
            event.prevent_default()
        elif event.key == "tab":
            self.toggle_target()
            self.post_message(self.TargetToggle())
            event.prevent_default()

    def set_count(self, current: int, total: int) -> None:
        try:
            count_label = self.query_one("#search-count", Static)
            if total == 0:
                count_label.update("No matches")
            else:
                count_label.update(f"{current}/{total}")
        except Exception:
            pass

    def toggle_target(self) -> None:
        self._search_target = "response" if self._search_target == "request" else "request"
        label = "Req" if self._search_target == "request" else "Resp"
        try:
            tgt = self.query_one("#search-target-toggle", Static)
            tgt.update(label)
            tgt.remove_class("search-target-req", "search-target-resp")
            tgt.add_class(f"search-target-{'req' if self._search_target == 'request' else 'resp'}")
        except Exception:
            pass

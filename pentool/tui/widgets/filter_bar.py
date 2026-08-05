"""FilterBar — filtering panel above DataTable."""

from __future__ import annotations

from pathlib import Path

from textual.app import ComposeResult
from textual.message import Message
from textual.widget import Widget
from textual.widgets import Button, Input, Static

_CSS = (Path(__file__).parent / "filter_bar.tcss").read_text(encoding="utf-8")

_METHODS = ["Any", "GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"]

# Same 6 mark colors as ProxyScreen._COLOR_OPTIONS — color IS the tag (variant A).
_COLOR_DOTS: list[tuple[str, str]] = [
    ("🔴", "red"),
    ("🟠", "orange"),
    ("🟡", "yellow"),
    ("🟢", "green"),
    ("🔵", "blue"),
    ("🟣", "purple"),
]


class MethodCycler(Static):
    """HTTP method toggle button — click cycles through values."""

    DEFAULT_CSS = _CSS

    def __init__(self, **kwargs) -> None:
        super().__init__("Any ▼", **kwargs)
        self._idx: int = 0

    @property
    def value(self) -> str:
        return _METHODS[self._idx]

    def reset(self) -> None:
        self._idx = 0
        self.update("Any ▼")

    def on_click(self) -> None:
        self._idx = (self._idx + 1) % len(_METHODS)
        label = _METHODS[self._idx]
        self.update(f"{label} ▼")
        # Post event upward so FilterBar can react
        self.post_message(MethodCycler.Changed(label))

    class Changed(Message):
        def __init__(self, method: str) -> None:
            super().__init__()
            self.method = method


class ScopeToggle(Static):
    """Toggle button for 'in-scope only' filter."""

    DEFAULT_CSS = _CSS

    class Toggled(Message):
        def __init__(self, active: bool) -> None:
            super().__init__()
            self.active = active

    def __init__(self, **kwargs) -> None:
        super().__init__("★ Scope", **kwargs)
        self._active: bool = False
        self._scope_empty: bool = True  # scope is initially empty → button inactive

    @property
    def active(self) -> bool:
        return self._active

    def set_scope_empty(self, empty: bool) -> None:
        self._scope_empty = empty
        if empty:
            self.add_class("disabled")
            if self._active:
                self._active = False
                self.remove_class("-active")
                self.update("★ Scope")
        else:
            self.remove_class("disabled")

    def on_click(self) -> None:
        if self._scope_empty:
            return  # ignore if scope is empty
        self._active = not self._active
        if self._active:
            self.add_class("-active")
            self.update("★ In Scope")
        else:
            self.remove_class("-active")
            self.update("★ Scope")
        self.post_message(self.Toggled(self._active))

    def reset(self) -> None:
        self._active = False
        self.remove_class("-active")
        self.update("★ Scope")


class ColorFilterCycler(Static):
    """Mark-color filter toggle — click cycles through Any/Red/Orange/.../Purple.

    Mirrors MethodCycler's UX: one click steps to the next value instead of
    a row of independently-clickable dots.
    """

    DEFAULT_CSS = _CSS

    class Changed(Message):
        def __init__(self, color: str) -> None:
            super().__init__()
            self.color = color  # "" means Any/cleared

    def __init__(self, **kwargs) -> None:
        super().__init__("", **kwargs)
        self._idx: int = 0  # 0 = "Any" (no filter)
        self._update_label()

    def _update_label(self) -> None:
        if self._idx == 0:
            self.update("Any ▼")
        else:
            dot, _ = _COLOR_DOTS[self._idx - 1]
            self.update(f"{dot} ▼")

    @property
    def value(self) -> str:
        if self._idx == 0:
            return ""
        return _COLOR_DOTS[self._idx - 1][1]

    def reset(self) -> None:
        self._idx = 0
        self._update_label()

    def on_click(self) -> None:
        self._idx = (self._idx + 1) % (len(_COLOR_DOTS) + 1)
        self._update_label()
        self.post_message(self.Changed(self.value))


class FilterBar(Widget):
    """Filter row: Host, Method, Status, Search + Apply/Reset.

    Posts FilterChanged on Apply or Enter.
    """

    DEFAULT_CSS = _CSS

    class FilterChanged(Message):
        """User applied a filter."""
        def __init__(self, filters: dict) -> None:
            super().__init__()
            self.filters = filters

    def compose(self) -> ComposeResult:
        yield Static("Host:", classes="fb-label")
        yield Input(placeholder="example.com", id="fb-host", compact=True)
        yield Static(" ", classes="fb-sep")
        yield Static("Method:", classes="fb-label")
        yield MethodCycler(id="fb-method")
        yield Static(" ", classes="fb-sep")
        yield Static("Status:", classes="fb-label")
        yield Input(placeholder="200-299", id="fb-status", compact=True)
        yield Static(" ", classes="fb-sep")
        yield Static("Mark:", classes="fb-label")
        yield ColorFilterCycler(id="fb-color")
        yield Static(" ", classes="fb-sep")
        yield Static("Search:", classes="fb-label")
        yield Input(placeholder="FTS5 query...", id="fb-search", compact=True)
        yield Static(" ", classes="fb-sep")
        yield ScopeToggle(id="fb-scope")
        yield Static(" ", classes="fb-sep")
        yield Button("Filter", id="fb-apply", variant="primary")
        yield Button("Clear", id="fb-reset")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "fb-apply":
            self._apply()
        elif event.button.id == "fb-reset":
            self._reset()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        """Enter in any Input applies the filter."""
        self._apply()

    def on_method_cycler_changed(self, event: MethodCycler.Changed) -> None:
        """Changing method immediately applies the filter."""
        self._apply()

    def on_color_filter_cycler_changed(self, event: ColorFilterCycler.Changed) -> None:
        """Changing color mark filter immediately applies the filter."""
        self._apply()

    def on_scope_toggle_toggled(self, event: ScopeToggle.Toggled) -> None:
        """Toggling the scope filter immediately applies the filter."""
        self._apply()

    def _apply(self) -> None:
        filters: dict = {}

        host = self.query_one("#fb-host", Input).value.strip()
        if host:
            filters["host"] = host

        try:
            method = self.query_one("#fb-method", MethodCycler).value
            if method and method != "Any":
                filters["method"] = [method]
        except Exception:
            pass

        status_raw = self.query_one("#fb-status", Input).value.strip()
        if status_raw:
            if "-" in status_raw:
                parts = status_raw.split("-", 1)
                try:
                    filters["status_code"] = (int(parts[0]), int(parts[1]))
                except ValueError:
                    pass
            else:
                try:
                    filters["status_code"] = int(status_raw)
                except ValueError:
                    pass

        tag = self.query_one("#fb-color", ColorFilterCycler).value
        if tag:
            filters["color"] = tag

        search = self.query_one("#fb-search", Input).value.strip()
        if search:
            filters["search"] = search

        # Scope filter — pass flag, ProxyScreen will supply the host list
        try:
            scope_toggle = self.query_one("#fb-scope", ScopeToggle)
            if scope_toggle.active:
                filters["scope_only"] = True
        except Exception:
            pass

        self.post_message(self.FilterChanged(filters))

    def _reset(self) -> None:
        self.query_one("#fb-host", Input).value = ""
        self.query_one("#fb-status", Input).value = ""
        self.query_one("#fb-search", Input).value = ""
        try:
            self.query_one("#fb-color", ColorFilterCycler).reset()
        except Exception:
            pass
        try:
            self.query_one("#fb-method", MethodCycler).reset()
        except Exception:
            pass
        try:
            self.query_one("#fb-scope", ScopeToggle).reset()
        except Exception:
            pass
        self.post_message(self.FilterChanged({}))

    def get_filters(self) -> dict:
        self._apply()
        # Returns the last built filters — via message
        return {}

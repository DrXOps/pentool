"""Color picker dialog — choose a color label for a Proxy history request."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import Button, Label

from pentool.tui.dialogs.base_dialog import BaseDialog

_COLOR_OPTIONS: list[tuple[str, str]] = [
    ("None", ""),
    ("🟥 Red", "red"),
    ("🟧 Orange", "orange"),
    ("🟨 Yellow", "yellow"),
    ("🟩 Green", "green"),
    ("🟦 Blue", "blue"),
    ("🟪 Purple", "purple"),
]


class ColorPickScreen(BaseDialog[str | None]):
    """Modal to pick a color mark for a proxy history request."""

    DEFAULT_CSS = """
    ColorPickScreen > Vertical {
        width: 30;
        height: auto;
        border: round $primary;
        padding: 1 2;
        background: $panel;
    }
    ColorPickScreen Button { margin: 0; width: 100%; }
    """

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Label("Mark color:")
            for label, val in _COLOR_OPTIONS:
                btn = Button(label, id=f"col-{val or 'clear'}")
                yield btn

    def on_button_pressed(self, event: Button.Pressed) -> None:
        bid = event.button.id or ""
        if bid.startswith("col-"):
            val = bid[4:]
            self.dismiss("" if val == "clear" else val)
        else:
            self.dismiss(None)

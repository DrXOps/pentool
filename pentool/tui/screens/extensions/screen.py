"""Extensions screen — plugin management."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.widget import Widget
from textual.widgets import Static
from pathlib import Path

_CSS = (Path(__file__).parent / "screen.tcss").read_text(encoding="utf-8")


class ExtensionsScreen(Widget):
    """Placeholder: Plugin manager screen."""

    DEFAULT_CSS = _CSS

    def compose(self) -> ComposeResult:
        with Static(id="box"):
            yield Static("Extensions", classes="title")
            yield Static(
                "Load Python plugins that add\nnew screens and CLI commands.",
                classes="desc",
            )

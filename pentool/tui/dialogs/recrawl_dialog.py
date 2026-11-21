"""RecrawlDialog — confirmation of a repeated crawl.

Shown when the host has already been crawled — offers the choice:
- Re-crawl — run the crawl again
- Skip — keep the existing results
"""

from __future__ import annotations

from pathlib import Path

from textual import on
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import Button, Label

from pentool.tui.dialogs.base_dialog import BaseDialog

_CSS = (Path(__file__).parent / "recrawl_dialog.tcss").read_text(encoding="utf-8")


class RecrawlDialog(BaseDialog):
    """Dialog: the host was already crawled. Re-crawl or Skip?"""

    DEFAULT_CSS = _CSS

    def __init__(self, host: str) -> None:
        super().__init__()
        self._host = host

    def compose(self) -> ComposeResult:
        with Vertical(id="dialog"):
            yield Label(
                f"[bold]Host:[/bold] {self._host}\n\nThis host was already crawled. What would you like to do?",
                id="question",
            )
            with Horizontal(id="buttons"):
                yield Button("Re-crawl", variant="primary", id="btn-recrawl")
                yield Button("Skip", variant="default", id="btn-skip")

    @on(Button.Pressed, "#btn-recrawl")
    def on_recrawl(self) -> None:
        self.dismiss("recrawl")

    @on(Button.Pressed, "#btn-skip")
    def on_skip(self) -> None:
        self.dismiss("skip")

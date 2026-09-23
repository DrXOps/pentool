"""RecrawlDialog — подтверждение повторного краула.

Показывается когда хост уже был краулен — предлагает выбрать:
- Re-crawl — запустить краул заново
- Skip — оставить существующие результаты
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
    """Диалог: хост уже краулен. Рекраул или Skip?"""

    DEFAULT_CSS = _CSS

    def __init__(self, host: str) -> None:
        super().__init__()
        self._host = host

    def compose(self) -> ComposeResult:
        with Vertical(id="dialog"):
            yield Label(
                f"[bold]Host:[/bold] {self._host}\n\n"
                f"This host was already crawled. What would you like to do?",
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
"""TextInputDialog — simple modal dialog with a single text input field."""

from __future__ import annotations

from pathlib import Path

from textual import on
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import Input, Label

from pentool.tui.dialogs.base_dialog import BaseDialog
from pentool.tui.widgets.toolbar_button import ToolbarButton


_CSS = (Path(__file__).parent / "text_input_dialog.tcss").read_text(encoding="utf-8")


class TextInputDialog(BaseDialog):
    """Simple modal dialog with a single Input field.

    Returns the text string via dismiss(), or None on cancel.
    """

    DEFAULT_CSS = _CSS

    def __init__(self, title: str = "Input", hint: str = "", initial: str = "") -> None:
        super().__init__()
        self._dialog_title = title
        self._hint = hint
        self._initial = initial

    def compose(self) -> ComposeResult:
        with Vertical(id="dialog"):
            yield Label(f"[bold]{self._dialog_title}[/bold]", id="title")
            if self._hint:
                yield Label(f"[dim]{self._hint}[/dim]", id="hint", classes="hint")
            yield Input(self._initial, id="text-input", placeholder="Type here...")
            with Horizontal(id="buttons"):
                yield ToolbarButton("✔ OK",     "btn-ok")
                yield ToolbarButton("✕ Cancel", "btn-cancel")

    @on(ToolbarButton.Pressed, "#btn-ok")
    def _btn_ok(self, _: ToolbarButton.Pressed) -> None:
        value = self.query_one("#text-input", Input).value
        self.dismiss(value)

    @on(ToolbarButton.Pressed, "#btn-cancel")
    def _btn_cancel(self, _: ToolbarButton.Pressed) -> None:
        self.dismiss(None)

    @on(Input.Submitted, "#text-input")
    def _input_submitted(self, _: Input.Submitted) -> None:
        value = self.query_one("#text-input", Input).value
        self.dismiss(value)
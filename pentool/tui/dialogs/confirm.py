"""ConfirmDialog — simple yes/no confirmation dialog.

Usage::

    dialog = ConfirmDialog(
        title="Confirm action",
        message="Are you sure?",
        confirm_text="Yes",
        cancel_text="No",
    )
    result = await app.push_screen_widget(dialog)
    if result:
        # user confirmed
"""

from __future__ import annotations

from pathlib import Path

from textual import on
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import Button, Label

from pentool.tui.dialogs.base_dialog import BaseDialog

_CSS = (Path(__file__).parent / "base_dialog.tcss").read_text(encoding="utf-8")


class ConfirmDialog(BaseDialog):
    """Simple confirmation dialog with two buttons."""

    DEFAULT_CSS = _CSS

    def __init__(
        self,
        title: str = "Confirm",
        message: str = "Are you sure?",
        confirm_text: str = "Yes",
        cancel_text: str = "No",
    ) -> None:
        super().__init__()
        self._title = title
        self._message = message
        self._confirm_text = confirm_text
        self._cancel_text = cancel_text

    def compose(self) -> ComposeResult:
        with Vertical(id="dialog"):
            yield Label(f"[bold]{self._title}[/bold]\n\n{self._message}", id="question")
            with Horizontal(id="buttons"):
                yield Button(self._confirm_text, variant="primary", id="btn-confirm")
                yield Button(self._cancel_text, variant="default", id="btn-cancel")

    @on(Button.Pressed, "#btn-confirm")
    def on_confirm(self) -> None:
        self.dismiss(True)

    @on(Button.Pressed, "#btn-cancel")
    def on_cancel(self) -> None:
        self.dismiss(False)
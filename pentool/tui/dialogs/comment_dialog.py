"""CommentDialog — view/edit the comment for a proxy history request.

Standardized on the same compact layout as the other dialogs (ToolbarButton
flat buttons, compact Input, CSS in a sibling .tcss file) instead of the
default textual.widgets.Button/Input, which render with full-size borders
and looked oversized compared to the rest of the app.
"""

from __future__ import annotations

from pathlib import Path

from textual import on
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Input, Label

from pentool.tui.widgets.toolbar_button import ToolbarButton

_CSS = (Path(__file__).parent / "comment_dialog.tcss").read_text(encoding="utf-8")


class CommentDialog(ModalScreen[str | None]):
    """Dialog: view/edit the comment for the currently-selected request."""

    DEFAULT_CSS = _CSS

    BINDINGS = [Binding("escape", "dismiss(None)", "Cancel")]

    def __init__(self, initial_comment: str = "") -> None:
        super().__init__()
        self._initial_comment = initial_comment

    def compose(self) -> ComposeResult:
        with Vertical(id="dialog"):
            yield Label("Comment:", id="comment-label")
            yield Input(
                value=self._initial_comment,
                placeholder="Add comment...",
                id="comment-dialog-input",
                compact=True,
            )
            with Horizontal(id="buttons"):
                yield ToolbarButton("Save", "btn-save")
                yield ToolbarButton("Cancel", "btn-cancel")

    def on_mount(self) -> None:
        self.query_one("#comment-dialog-input", Input).focus()

    @on(ToolbarButton.Pressed, "#btn-save")
    def on_btn_save(self, _: ToolbarButton.Pressed) -> None:
        self.dismiss(self.query_one("#comment-dialog-input", Input).value)

    @on(ToolbarButton.Pressed, "#btn-cancel")
    def on_btn_cancel(self, _: ToolbarButton.Pressed) -> None:
        self.dismiss(None)

    def on_input_submitted(self, event: Input.Submitted) -> None:
        self.dismiss(event.value)

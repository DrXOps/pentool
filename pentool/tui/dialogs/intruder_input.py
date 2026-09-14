"""Input dialog — add a single payload value to the intruder payload set."""

from __future__ import annotations

from pathlib import Path

from textual import on
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import Input, Label

from pentool.tui.dialogs.base_dialog import BaseDialog
from pentool.tui.widgets.toolbar_button import ToolbarButton


_CSS = (Path(__file__).parent / "intruder_input.tcss").read_text(encoding="utf-8")


class InputDialog(BaseDialog):
    """Payload add dialog — does not close after ADD, accumulates the list."""

    DEFAULT_CSS = _CSS

    def __init__(self, title: str, prompt: str, on_add=None, **kwargs) -> None:
        super().__init__(**kwargs)
        self._title = title
        self._prompt = prompt
        self._on_add = on_add  # callback(value: str) called on each ADD

    def compose(self) -> ComposeResult:
        with Vertical(id="dialog"):
            yield Label(self._prompt, id="prompt-label")
            yield Input(id="input-value", placeholder="value...", compact=True)
            with Horizontal(id="buttons"):
                yield ToolbarButton("✔ Add",   "btn-ok")
                yield ToolbarButton("✕ Close", "btn-cancel")

    def on_mount(self) -> None:
        self.query_one("#input-value", Input).focus()

    @on(ToolbarButton.Pressed, "#btn-ok")
    def _ok(self, _: ToolbarButton.Pressed) -> None:
        self._do_add()

    @on(ToolbarButton.Pressed, "#btn-cancel")
    def _cancel(self, _: ToolbarButton.Pressed) -> None:
        self.action_cancel()  # DialogCancelMixin -> dismiss(None)

    def _do_add(self) -> None:
        try:
            inp = self.query_one("#input-value", Input)
            value = inp.value.strip()
            if value and self._on_add:
                self._on_add(value)
                inp.value = ""
                inp.focus()
        except Exception:
            pass

    def on_key(self, event) -> None:
        if event.key == "escape":
            self.action_cancel()  # DialogCancelMixin -> dismiss(None)
        elif event.key == "enter":
            self._do_add()
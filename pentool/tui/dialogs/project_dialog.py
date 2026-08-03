"""Project save/load dialogs."""

from __future__ import annotations

from pathlib import Path

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Label, Static

_CSS = (Path(__file__).parent / "project_dialog.tcss").read_text(encoding="utf-8")


class SaveProjectDialog(ModalScreen[str | None]):
    """Dialog: enter path to save the project."""

    DEFAULT_CSS = _CSS

    BINDINGS = [Binding("escape", "dismiss(None)", "Cancel")]

    def __init__(self, default_path: str = "project.json") -> None:
        super().__init__()
        self._default = default_path

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Label("Save project as:")
            yield Input(value=self._default, id="path-input", placeholder="path/to/project.json", compact=True)
            with Horizontal():
                yield Button("Save", variant="primary", id="btn-save")
                yield Button("Cancel", id="btn-cancel")

    def on_mount(self) -> None:
        self.query_one("#path-input", Input).focus()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-save":
            path = self.query_one("#path-input", Input).value.strip()
            self.dismiss(path if path else None)
        else:
            self.dismiss(None)

    def on_input_submitted(self, event: Input.Submitted) -> None:
        path = event.value.strip()
        self.dismiss(path if path else None)


class LoadProjectDialog(ModalScreen[str | None]):
    """Dialog: enter path to load the project."""

    DEFAULT_CSS = _CSS

    BINDINGS = [Binding("escape", "dismiss(None)", "Cancel")]

    def __init__(self, default_path: str = "project.json") -> None:
        super().__init__()
        self._default = default_path

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Label("Load project from:")
            yield Input(value=self._default, id="path-input", placeholder="path/to/project.json", compact=True)
            yield Static("HTTP History will be replaced with saved data.", classes="hint")
            with Horizontal():
                yield Button("Load", variant="primary", id="btn-load")
                yield Button("Cancel", id="btn-cancel")

    def on_mount(self) -> None:
        self.query_one("#path-input", Input).focus()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-load":
            path = self.query_one("#path-input", Input).value.strip()
            self.dismiss(path if path else None)
        else:
            self.dismiss(None)

    def on_input_submitted(self, event: Input.Submitted) -> None:
        path = event.value.strip()
        self.dismiss(path if path else None)

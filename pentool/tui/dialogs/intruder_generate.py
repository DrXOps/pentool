"""Generate dialog — create numeric or char brute-force payload sources."""

from __future__ import annotations

from pathlib import Path

from textual import on
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Input, Label, Static

from pentool.api.intruder_api import CharPayloadSource, NumericPayloadSource
from pentool.tui.mixins.dialog_cancel import DialogCancelMixin
from pentool.tui.widgets.option_cycler import OptionCycler
from pentool.tui.widgets.toolbar_button import ToolbarButton


_CSS = r"""
GenerateDialog {
    align: center middle;
    height: 15;
    width: 50;
}
GenerateDialog #dialog {
    height: auto;
    width: 100%;
    padding: 1 2;
    border: round $primary;
    background: $surface;
    layout: vertical;
}
GenerateDialog .row {
    height: 1;
    layout: horizontal;
    align: left middle;
    margin-bottom: 1;
}
GenerateDialog .row Label {
    width: 8;
    color: $text-muted;
}
GenerateDialog Input {
    width: 12;
    background: $surface-darken-1;
}
GenerateDialog #mode-select {
    width: 26;
}
GenerateDialog #numeric-fields,
GenerateDialog #char-fields {
    height: auto;
    layout: vertical;
}
GenerateDialog #preview-label {
    height: 1;
    color: $text-muted;
    margin-bottom: 1;
}
GenerateDialog #buttons {
    height: 1;
    layout: horizontal;
    align: right middle;
    margin-top: 1;
}
GenerateDialog #buttons ToolbarButton {
    margin: 0 0 0 1;
}
"""


class GenerateDialog(DialogCancelMixin, ModalScreen):
    """Generate dialog — Numeric range or Char (alphabet brute-force) mode.

    Returns a lazy NumericPayloadSource/CharPayloadSource (never a
    materialized list) via dismiss().
    """

    DEFAULT_CSS = _CSS
    # Force the outer ModalScreen itself to a small size. Textual's CSS
    # selector uses the Python class name, but mixin MRO can confuse it —
    # as a belt-and-suspenders, also pass styles in compose elements.
    BINDINGS = [
        Binding("escape", "cancel", "Cancel"),
    ]

    def compose(self) -> ComposeResult:
        # Belt-and-suspenders: set fixed size on the screen's own DOM node
        # so the ModalScreen never stretches full-terminal when CSS fails.
        self.styles.width = 50
        self.styles.height = 18
        self.styles.align = ("center", "middle")
        with Vertical(id="dialog") as dlg:
            dlg.styles.width = 48
            dlg.styles.height = 16
            dlg.styles.align = ("center", "middle")
            with Horizontal(classes="row"):
                yield Label("Mode:")
                yield OptionCycler(
                    [("Numeric range", "numeric"), ("Char brute-force", "char")],
                    initial="numeric", id="mode-select",
                )
            with Vertical(id="numeric-fields"):
                with Horizontal(classes="row"):
                    yield Label("From:")
                    yield Input("0", id="gen-start", compact=True)
                with Horizontal(classes="row"):
                    yield Label("To:")
                    yield Input("100", id="gen-end", compact=True)
                with Horizontal(classes="row"):
                    yield Label("Step:")
                    yield Input("1", id="gen-step", compact=True)
            with Vertical(id="char-fields"):
                with Horizontal(classes="row"):
                    yield Label("Charset:")
                    yield Input("abcdefghijklmnopqrstuvwxyz0123456789", id="gen-charset", compact=True)
                with Horizontal(classes="row"):
                    yield Label("Min len:")
                    yield Input("1", id="gen-minlen", compact=True)
                with Horizontal(classes="row"):
                    yield Label("Max len:")
                    yield Input("3", id="gen-maxlen", compact=True)
            yield Static("", id="preview-label")
            with Horizontal(id="buttons"):
                yield ToolbarButton("✔ Generate", "btn-gen-ok")
                yield ToolbarButton("✕ Cancel", "btn-gen-cancel")

    def on_mount(self) -> None:
        self._sync_mode_visibility()
        self._update_preview()

    def _sync_mode_visibility(self) -> None:
        mode = self.query_one("#mode-select", OptionCycler).value
        try:
            self.query_one("#numeric-fields").display = (mode == "numeric")
            self.query_one("#char-fields").display = (mode == "char")
        except Exception:
            pass

    def _build_source(self):
        mode = self.query_one("#mode-select", OptionCycler).value
        try:
            if mode == "numeric":
                start = int(self.query_one("#gen-start", Input).value or "0")
                end   = int(self.query_one("#gen-end",   Input).value or "100")
                step  = int(self.query_one("#gen-step",  Input).value or "1")
                return NumericPayloadSource(start, end, step)
            else:
                charset = self.query_one("#gen-charset", Input).value or ""
                min_len = int(self.query_one("#gen-minlen", Input).value or "1")
                max_len = int(self.query_one("#gen-maxlen", Input).value or "1")
                return CharPayloadSource(charset, min_len, max_len)
        except Exception:
            return None

    def _update_preview(self) -> None:
        try:
            label = self.query_one("#preview-label", Static)
        except Exception:
            return
        source = self._build_source()
        if source is None:
            label.update("[dim]invalid input[/dim]")
            return
        n = len(source)
        label.update(f"[dim]→ {n:,} payload(s)[/dim]")

    @on(OptionCycler.Changed, "#mode-select")
    def _mode_changed(self, _: OptionCycler.Changed) -> None:
        self._sync_mode_visibility()
        self._update_preview()

    @on(Input.Changed)
    def _field_changed(self, _: Input.Changed) -> None:
        self._update_preview()

    @on(ToolbarButton.Pressed, "#btn-gen-ok")
    def _gen_ok(self, _: ToolbarButton.Pressed) -> None:
        self.dismiss(self._build_source())

    @on(ToolbarButton.Pressed, "#btn-gen-cancel")
    def _gen_cancel(self, _: ToolbarButton.Pressed) -> None:
        self.action_cancel()

    def on_key(self, event) -> None:
        if event.key == "escape":
            self.action_cancel()
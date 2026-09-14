"""Generate dialog — create numeric or char brute-force payload sources."""

from __future__ import annotations

from pathlib import Path

from textual import on
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import Input, Label, Static

from pentool.api.intruder_api import CharPayloadSource, NumericPayloadSource
from pentool.tui.dialogs.base_dialog import BaseDialog
from pentool.tui.widgets.option_cycler import OptionCycler
from pentool.tui.widgets.toolbar_button import ToolbarButton


_CSS = (Path(__file__).parent / "intruder_generate.tcss").read_text(encoding="utf-8")


class GenerateDialog(BaseDialog):
    """Generate dialog — Numeric range or Char (alphabet brute-force) mode.

    Returns a lazy NumericPayloadSource/CharPayloadSource (never a
    materialized list) via dismiss().
    """

    DEFAULT_CSS = _CSS

    def compose(self) -> ComposeResult:
        with Vertical(id="dialog"):
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
        self.query_one("#numeric-fields").display = (mode == "numeric")
        self.query_one("#char-fields").display = (mode == "char")

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
        label = self.query_one("#preview-label", Static)
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
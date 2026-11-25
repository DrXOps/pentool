"""Decoder/Encoder screen — encoding, decoding, hashing."""

from __future__ import annotations

from pathlib import Path

from textual import on
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.css.query import NoMatches
from textual.widgets import Label, Static

from pentool.core.logging import get_logger
from pentool.tui.header import HeaderAction, HeaderSpec
from pentool.tui.hotkeys.defaults import DECODER_BINDINGS
from pentool.tui.markup import esc
from pentool.tui.mixins.content_clipboard_mixin import ContentClipboardMixin
from pentool.tui.screens.module_screen import ModuleScreen
from pentool.tui.widgets.action_row import action_buttons, action_of
from pentool.tui.widgets.content_panel import ContentPanel
from pentool.tui.widgets.resize_handle import ResizeHandle
from pentool.tui.widgets.toolbar_button import ToolbarButton

logger = get_logger(__name__)

_CSS = (Path(__file__).parent / "screen.tcss").read_text(encoding="utf-8")


class DecoderScreen(ContentClipboardMixin, ModuleScreen):
    """Encoder / Decoder with operation chains."""

    DEFAULT_CSS = _CSS

    BINDINGS = DECODER_BINDINGS

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        from pentool.api.decoder_api import OP_LABELS

        self._op_labels: list[str] = OP_LABELS
        self._selected_op: str = OP_LABELS[0]  # currently selected operation
        self._chain: list[str] = []  # list of operations in the chain

    #: Header buttons (see `header_spec`) → methods that run them.
    ACTIONS = {
        "run": "action_run_chain",
        "add_step": "_add_step",
        "clear_chain": "_clear_chain",
        "swap": "_swap_io",
        "smart": "_smart_decode",
    }

    @on(ToolbarButton.Pressed, ".tool-act")
    def _on_tool_action(self, event: ToolbarButton.Pressed) -> None:
        """A button in the tool's own row — same path as the header buttons."""
        self.header_action(action_of(event.button))

    def header_spec(self) -> HeaderSpec:
        """The five one-shot actions; the operation picker stays in the config row."""
        return HeaderSpec(
            actions=(
                HeaderAction("run", "▶ Run"),
                HeaderAction("add_step", "+ Add Step"),
                HeaderAction("clear_chain", "✗ Clear Chain"),
                HeaderAction("swap", "⇅ Swap I/O"),
                HeaderAction("smart", "🔍 Smart"),
            ),
        )

    def compose(self) -> ComposeResult:

        # ── Operation selector (adding steps) ──────────────────────────────────
        with Horizontal(id="dec-op-row"):
            yield from action_buttons(self.header_spec().actions)
            yield Label("Operation:", id="dec-op-label")
            yield ToolbarButton(f"{self._selected_op} ▼", "btn-dec-op-select")
            yield Label("  Chain:", id="dec-chain-label")
            yield Static("(empty)", id="dec-chain-display")

        # ── Work area ──────────────────────────────────────────────────────────
        with Horizontal(id="dec-work-area"):
            # Input
            with Vertical(id="dec-input-col"):
                yield ContentPanel(
                    "Input",
                    widget_type="textarea",
                    role="request-editable-plain",
                    id="dec-input",
                    classes="card",
                )

            yield ResizeHandle("dec-input-col", "dec-output-col", id="dec-resize-h")

            # Output
            with Vertical(id="dec-output-col"):
                yield ContentPanel(
                    "Output",
                    widget_type="textarea",
                    textarea_read_only=True,
                    role="text-readonly",
                    id="dec-output",
                    classes="card",
                )

        yield ResizeHandle("dec-work-area", "dec-steps-area", vertical=True, id="dec-resize-v")

        # ── Chain steps log ────────────────────────────────────────────────────
        with Vertical(id="dec-steps-area"):
            yield ContentPanel(
                "Chain steps",
                widget_type="richlog",
                wrap=True,
                max_lines=200,
                role="log",
                id="dec-steps-log",
                classes="card",
            )

    # ── Toolbar actions ────────────────────────────────────────────────────────

    @on(ToolbarButton.Pressed, "#btn-dec-op-select")
    def on_btn_dec_op_select(self, event: ToolbarButton.Pressed) -> None:
        self._open_op_menu(event.button)

    # ── ContentPanel handlers ──────────────────────────────────────────────────

    @on(ContentPanel.FormatToggleRequested)
    def on_dec_toggle_format(self, event: ContentPanel.FormatToggleRequested) -> None:
        """Toggle raw/formatted — not applicable to the Decoder."""
        pass

    def _open_op_menu(self, btn: ToolbarButton) -> None:
        items = [(op, ("✓ " if op == self._selected_op else "  ") + op) for op in self._op_labels]
        r = btn.region
        self.app.show_context_menu(items, r.x, r.y + 1, callback=self._on_op_selected)

    def _on_op_selected(self, op: str) -> None:
        self._selected_op = op
        try:
            btn = self.query_one("#btn-dec-op-select", ToolbarButton)
            btn.label = f"{op} ▼"
        except NoMatches as exc:
            # The button still shows the previous operation while the chain is
            # built from the new one — what actually runs is unreadable on screen.
            logger.debug("decoder: op button label not updated: %s", exc)

    def _add_step(self) -> None:
        try:
            op = self._selected_op
            if op:
                self._chain.append(op)
                self._update_chain_display()
        except Exception as exc:
            logger.debug("_add_step: %s", exc)

    def _clear_chain(self) -> None:
        self._chain.clear()
        self._update_chain_display()
        try:
            self.query_one("#dec-steps-log", ContentPanel).clear_content()
        except NoMatches as exc:
            # Old steps stay in the log panel after "Clear" — the journal
            # describes a chain that no longer exists.
            logger.debug("decoder: steps log not cleared: %s", exc)

    def _swap_io(self) -> None:
        try:
            inp = self.query_one("#dec-input", ContentPanel).content_widget
            out = self.query_one("#dec-output", ContentPanel).content_widget
            inp_text = inp.text
            inp.load_text(out.text)
            out.load_text(inp_text)
        except Exception as exc:
            logger.debug("_swap_io: %s", exc)

    def _smart_decode(self) -> None:
        """Auto-detect and chain-decode the input."""
        try:
            from pentool.api.decoder_api import detect_encoding, encode_op

            inp = self.query_one("#dec-input", ContentPanel).content_widget
            text = inp.text.strip()
            if not text:
                self.app.notify("Input is empty", severity="warning")
                return

            # Run chain and collect steps for visualization
            current = text
            chain: list[str] = []
            steps: list[str] = [current]
            for _ in range(8):
                op = detect_encoding(current)
                if op is None:
                    break
                try:
                    nxt = encode_op(op, current)
                    if nxt == current:
                        break
                    chain.append(op)
                    current = nxt
                    steps.append(current)
                except Exception:
                    break

            result = current
            self.query_one("#dec-output", ContentPanel).content_widget.load_text(result)
            log = self.query_one("#dec-steps-log", ContentPanel).content_widget
            log.clear()
            if chain:
                log.write(f"[bold cyan]Smart decode chain: {' → '.join(chain)}[/bold cyan]")
                log.write("")
                for i, (op, val) in enumerate(zip(["INPUT"] + chain, steps)):
                    color = "dim" if i == 0 else "green"
                    preview = val[:100].replace("\n", "↵")
                    label = f"Step {i}" if i > 0 else "Input"
                    log.write(f"[bold]{label}[/bold] [{color}]{op}[/{color}]")
                    log.write(f"  [dim]{esc(preview)}[/dim]  [dim]({len(val)} chars)[/dim]")
            else:
                log.write("[yellow]Smart decode: no known encoding detected[/yellow]")
                log.write(f"[dim]Input ({len(text)} chars): {esc(text[:80])}[/dim]")
        except Exception as exc:
            self.err(exc, "Smart decode error")

    def _update_chain_display(self) -> None:
        try:
            lbl = self.query_one("#dec-chain-display", Static)
            if self._chain:
                lbl.update(" → ".join(self._chain))
            else:
                lbl.update("[dim](empty)[/dim]")
        except Exception as exc:
            # Chain display not updated — it shows steps that are no longer in
            # the chain (or vice versa), so Run will execute the wrong thing.
            logger.debug("decoder: chain display not updated: %s", exc)

    # ── Run ───────────────────────────────────────────────────────────────────

    def action_run_chain(self) -> None:
        try:
            from pentool.api.decoder_api import encode_op, run_chain

            inp_text = self.query_one("#dec-input", ContentPanel).content_widget.text
            if not inp_text:
                self.app.notify("Input is empty", severity="warning")
                return

            if not self._chain:
                # Single operation — use the one selected by button
                op = self._selected_op
                try:
                    result = encode_op(op, inp_text)
                    steps = [inp_text, result]
                    chain_used = [op]
                except Exception as exc:
                    self.err(exc, "Encode error")
                    return
            else:
                result, steps = run_chain(self._chain, inp_text)
                chain_used = self._chain

            self.query_one("#dec-output", ContentPanel).content_widget.load_text(result)
            self._render_steps(chain_used, steps)

        except Exception as exc:
            self.err(exc, "Run error")

    def _render_steps(self, chain: list[str], steps: list[str]) -> None:
        try:
            log = self.query_one("#dec-steps-log", ContentPanel).content_widget
            log.clear()
            log.write(f"[bold cyan]Chain: {' → '.join(chain)}[/bold cyan]")
            log.write("")
            for i, (op, value) in enumerate(zip(["INPUT"] + chain, steps)):
                step_label = f"Step {i}" if i > 0 else "Input"
                color = "dim" if i == 0 else ("green" if not value.startswith("[error") else "red")
                preview = value[:100].replace("\n", "↵") + ("…" if len(value) > 100 else "")
                log.write(f"[bold]{step_label}[/bold] [{color}]{op}[/{color}]")
                log.write(f"  [dim]{esc(preview)}[/dim]  [dim]({len(value)} chars)[/dim]")
        except Exception as exc:
            logger.debug("_render_steps: %s", exc)

    # ── Copy / Clear ──────────────────────────────────────────────────────────

    def action_copy_result(self) -> None:
        """Copy output to clipboard (called from hotkey)."""
        try:
            from pentool.utils.copy_as import copy_to_clipboard

            text = self.query_one("#dec-output", ContentPanel).content_widget.text
            if text and copy_to_clipboard(text):
                self.app.notify("Result copied", timeout=2)
            else:
                self.app.notify("Nothing to copy", severity="warning")
        except Exception as exc:
            self.err(exc, "Copy failed")

    def action_clear_all(self) -> None:
        try:
            self.query_one("#dec-input", ContentPanel).clear_content()
            self.query_one("#dec-output", ContentPanel).clear_content()
            self.query_one("#dec-steps-log", ContentPanel).clear_content()
            self._chain.clear()
            self._update_chain_display()
        except NoMatches as exc:
            # One of the three panels is not in the tree — "Clear all" left part
            # of the previous output on screen. `NoMatches` names the cause;
            # let anything else bubble up.
            logger.debug("decoder: clear all — panel not mounted: %s", exc)

    # ── Public API (loading from other modules) ───────────────────────────────

    def load_text(self, text: str) -> None:
        try:
            self.query_one("#dec-input", ContentPanel).content_widget.load_text(text)
            self.query_one("#dec-output", ContentPanel).clear_content()
            self.query_one("#dec-steps-log", ContentPanel).clear_content()
        except NoMatches as exc:
            # The text was loaded but the step log from the previous operation
            # remains — it describes what the new input will no longer produce.
            logger.debug("decoder: load_text panels not reset: %s", exc)

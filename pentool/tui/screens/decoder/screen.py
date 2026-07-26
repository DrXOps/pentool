"""Decoder/Encoder screen — encoding, decoding, hashing."""

from __future__ import annotations

from pathlib import Path
from textual import on
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.widget import Widget
from textual.widgets import Label, RichLog, Static, TextArea

from pentool.tui.widgets.toolbar_button import ToolbarButton
from pentool.tui.widgets.resize_handle import ResizeHandle
from pentool.core.logging import get_logger

logger = get_logger(__name__)

_CSS = (Path(__file__).parent / "screen.tcss").read_text(encoding="utf-8")


class DecoderScreen(Widget):
    """Encoder / Decoder with operation chains."""

    DEFAULT_CSS = _CSS

    BINDINGS = [
        Binding("ctrl+enter", "run_chain", "Run",      show=True),
        Binding("ctrl+l",     "clear_all", "Clear",    show=False),
        Binding("ctrl+c",     "copy_result","Copy",    show=False),
    ]

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        from pentool.api.decoder_api import OP_LABELS
        self._op_labels: list[str] = OP_LABELS
        self._selected_op: str = OP_LABELS[0]  # currently selected operation
        self._chain: list[str] = []           # list of operations in the chain

    def compose(self) -> ComposeResult:
        from pentool.api.decoder_api import OP_LABELS

        # ── Toolbar ────────────────────────────────────────────────────────────
        with Horizontal(id="dec-toolbar"):
            yield ToolbarButton("▶ Run",        "btn-dec-run")
            yield Static(" │ ", classes="toolbar-sep")
            yield ToolbarButton("+ Add Step",   "btn-dec-add")
            yield Static(" │ ", classes="toolbar-sep")
            yield ToolbarButton("✗ Clear Chain","btn-dec-clrchain")
            yield Static(" │ ", classes="toolbar-sep")
            yield ToolbarButton("⇅ Swap I/O",   "btn-dec-swap")
            yield Static(" │ ", classes="toolbar-sep")
            yield ToolbarButton("📋 Copy",       "btn-dec-copy")
            yield Static(" │ ", classes="toolbar-sep")
            yield ToolbarButton("🔍 Smart",      "btn-dec-smart")

        # ── Operation selector (adding steps) ──────────────────────────────────
        with Horizontal(id="dec-op-row"):
            yield Label("Operation:", id="dec-op-label")
            yield ToolbarButton(f"{self._selected_op} ▼", "btn-dec-op-select")
            yield Label("  Chain:", id="dec-chain-label")
            yield Static("(empty)", id="dec-chain-display")

        # ── Work area ──────────────────────────────────────────────────────────
        with Horizontal(id="dec-work-area"):
            # Input
            with Vertical(id="dec-input-col"):
                yield Static("Input", id="dec-input-label", classes="dec-col-label")
                yield TextArea(id="dec-input", language=None)

            yield ResizeHandle("dec-input-col", "dec-output-col", id="dec-resize-h")

            # Output
            with Vertical(id="dec-output-col"):
                yield Static("Output", id="dec-output-label", classes="dec-col-label")
                yield TextArea(id="dec-output", language=None)

        yield ResizeHandle("dec-work-area", "dec-steps-area", vertical=True,
                           id="dec-resize-v")

        # ── Chain steps log ────────────────────────────────────────────────────
        with Vertical(id="dec-steps-area"):
            yield Static("Chain steps", id="dec-steps-label", classes="dec-col-label")
            yield RichLog(id="dec-steps-log", highlight=True, markup=True,
                          wrap=True, max_lines=200)

        yield Static(
            "Ctrl+Enter: Run  │  + Add Step: add operation to chain  │  ⇅ Swap: swap Input/Output"
            "  │  📋 Copy: copy result  │  🔍 Smart: auto-detect encoding",
            id="status-bar",
        )

    # ── Toolbar actions ────────────────────────────────────────────────────────

    @on(ToolbarButton.Pressed, "#btn-dec-run")
    def on_btn_dec_run(self, _: ToolbarButton.Pressed) -> None:
        self.action_run_chain()

    @on(ToolbarButton.Pressed, "#btn-dec-add")
    def on_btn_dec_add(self, _: ToolbarButton.Pressed) -> None:
        self._add_step()

    @on(ToolbarButton.Pressed, "#btn-dec-op-select")
    def on_btn_dec_op_select(self, event: ToolbarButton.Pressed) -> None:
        self._open_op_menu(event.button)

    @on(ToolbarButton.Pressed, "#btn-dec-clrchain")
    def on_btn_dec_clrchain(self, _: ToolbarButton.Pressed) -> None:
        self._clear_chain()

    @on(ToolbarButton.Pressed, "#btn-dec-swap")
    def on_btn_dec_swap(self, _: ToolbarButton.Pressed) -> None:
        self._swap_io()

    @on(ToolbarButton.Pressed, "#btn-dec-copy")
    def on_btn_dec_copy(self, _: ToolbarButton.Pressed) -> None:
        self.action_copy_result()

    @on(ToolbarButton.Pressed, "#btn-dec-smart")
    def on_btn_dec_smart(self, _: ToolbarButton.Pressed) -> None:
        self._smart_decode()

    def _open_op_menu(self, btn: ToolbarButton) -> None:
        items = [
            (op, ("✓ " if op == self._selected_op else "  ") + op)
            for op in self._op_labels
        ]
        r = btn.region
        self.app.show_context_menu(items, r.x, r.y + 1, callback=self._on_op_selected)

    def _on_op_selected(self, op: str) -> None:
        self._selected_op = op
        try:
            btn = self.query_one("#btn-dec-op-select", ToolbarButton)
            btn.label = f"{op} ▼"
        except Exception:
            pass

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
            self.query_one("#dec-steps-log", RichLog).clear()
        except Exception:
            pass

    def _swap_io(self) -> None:
        try:
            inp = self.query_one("#dec-input", TextArea)
            out = self.query_one("#dec-output", TextArea)
            inp_text = inp.text
            inp.load_text(out.text)
            out.load_text(inp_text)
        except Exception as exc:
            logger.debug("_swap_io: %s", exc)

    def _smart_decode(self) -> None:
        """Auto-detect and chain-decode the input."""
        try:
            from pentool.api.decoder_api import decode_smart
            from pentool.modules.decoder import _detect_encoding, encode_op
            inp = self.query_one("#dec-input", TextArea)
            text = inp.text.strip()
            if not text:
                self.app.notify("Input is empty", severity="warning")
                return

            # Run chain and collect steps for visualization
            current = text
            chain: list[str] = []
            steps: list[str] = [current]
            for _ in range(8):
                op = _detect_encoding(current)
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
            self.query_one("#dec-output", TextArea).load_text(result)
            log = self.query_one("#dec-steps-log", RichLog)
            log.clear()
            if chain:
                log.write(f"[bold cyan]Smart decode chain: {' → '.join(chain)}[/bold cyan]")
                log.write("")
                for i, (op, val) in enumerate(zip(["INPUT"] + chain, steps)):
                    color = "dim" if i == 0 else "green"
                    preview = val[:100].replace("\n", "↵")
                    label = f"Step {i}" if i > 0 else "Input"
                    log.write(f"[bold]{label}[/bold] [{color}]{op}[/{color}]")
                    log.write(f"  [dim]{preview}[/dim]  [dim]({len(val)} chars)[/dim]")
            else:
                log.write("[yellow]Smart decode: no known encoding detected[/yellow]")
                log.write(f"[dim]Input ({len(text)} chars): {text[:80]}[/dim]")
        except Exception as exc:
            self.app.notify(f"Smart decode error: {exc}", severity="error")

    def _update_chain_display(self) -> None:
        try:
            lbl = self.query_one("#dec-chain-display", Static)
            if self._chain:
                lbl.update(" → ".join(self._chain))
            else:
                lbl.update("[dim](empty)[/dim]")
        except Exception:
            pass

    # ── Run ───────────────────────────────────────────────────────────────────

    def action_run_chain(self) -> None:
        try:
            from pentool.api.decoder_api import run_chain, encode_op
            inp_text = self.query_one("#dec-input", TextArea).text
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
                    self.app.notify(f"Error: {exc}", severity="error")
                    return
            else:
                result, steps = run_chain(self._chain, inp_text)
                chain_used = self._chain

            self.query_one("#dec-output", TextArea).load_text(result)
            self._render_steps(chain_used, steps)

        except Exception as exc:
            self.app.notify(f"Run error: {exc}", severity="error")
            logger.debug("action_run_chain: %s", exc)

    def _render_steps(self, chain: list[str], steps: list[str]) -> None:
        try:
            log = self.query_one("#dec-steps-log", RichLog)
            log.clear()
            log.write(f"[bold cyan]Chain: {' → '.join(chain)}[/bold cyan]")
            log.write("")
            for i, (op, value) in enumerate(zip(["INPUT"] + chain, steps)):
                step_label = f"Step {i}" if i > 0 else "Input"
                color = "dim" if i == 0 else ("green" if not value.startswith("[error") else "red")
                preview = value[:100].replace("\n", "↵") + ("…" if len(value) > 100 else "")
                log.write(f"[bold]{step_label}[/bold] [{color}]{op}[/{color}]")
                log.write(f"  [dim]{preview}[/dim]  [dim]({len(value)} chars)[/dim]")
        except Exception as exc:
            logger.debug("_render_steps: %s", exc)

    # ── Copy / Clear ──────────────────────────────────────────────────────────

    def action_copy_result(self) -> None:
        try:
            from pentool.utils.copy_as import copy_to_clipboard
            text = self.query_one("#dec-output", TextArea).text
            if text and copy_to_clipboard(text):
                self.app.notify("Result copied", timeout=2)
            else:
                self.app.notify("Nothing to copy", severity="warning")
        except Exception as exc:
            self.app.notify(f"Copy failed: {exc}", severity="error")

    def action_clear_all(self) -> None:
        try:
            self.query_one("#dec-input", TextArea).load_text("")
            self.query_one("#dec-output", TextArea).load_text("")
            self.query_one("#dec-steps-log", RichLog).clear()
            self._chain.clear()
            self._update_chain_display()
        except Exception as exc:
            logger.debug("action_clear_all: %s", exc)

    # ── Public API (loading from other modules) ───────────────────────────────

    def load_text(self, text: str) -> None:
        try:
            self.query_one("#dec-input", TextArea).load_text(text)
            self.query_one("#dec-output", TextArea).load_text("")
            self.query_one("#dec-steps-log", RichLog).clear()
        except Exception as exc:
            logger.debug("load_text: %s", exc)

    # ── Keyboard shortcut ─────────────────────────────────────────────────────

    def action_run_chain_binding(self) -> None:
        self.action_run_chain()

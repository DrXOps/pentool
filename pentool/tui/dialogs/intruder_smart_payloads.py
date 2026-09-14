"""PRO Smart Payload Generator dialog — context-aware payloads."""

from __future__ import annotations

from pathlib import Path

from textual import on
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import Button, Input, Label, Select, Static

from pentool.core.logging import get_logger
from pentool.tui.dialogs.base_dialog import BaseDialog
from pentool.tui.widgets.toolbar_button import ToolbarButton


_CSS = (Path(__file__).parent / "intruder_smart_payloads.tcss").read_text(encoding="utf-8")

logger = get_logger(__name__)


class SmartPayloadsDialog(BaseDialog):
    """PRO Smart Payload Generator — dialog for generating context-aware payloads."""

    DEFAULT_CSS = _CSS

    def compose(self) -> ComposeResult:
        with Vertical(id="dialog"):
            with Horizontal(id="title-bar"):
                yield Static("🧠 Smart Payload Generator (PRO)")
                yield Button("✕", id="btn-close-smart")
            with Horizontal(classes="row"):
                yield Label("Context:")
                yield Select(
                    [("String", "string"), ("Numeric", "numeric"), ("JSON", "json"),
                     ("XML", "xml"), ("URL", "url"), ("Cookie", "cookie"),
                     ("Header", "header"), ("Path", "path")],
                    id="smart-context", value="string",
                )
            with Horizontal(classes="row"):
                yield Label("Tech hint:")
                yield Select(
                    [("Unknown", "unknown"), ("PHP", "php"), ("Java", "java"),
                     ("Node.js", "node"), ("Python", "python"), (".NET", "dotnet")],
                    id="smart-tech", value="unknown",
                )
            with Horizontal(classes="row"):
                yield Label("WAF profile:")
                yield Select(
                    [("None", "none"), ("Generic", "generic"), ("Cloudflare", "cloudflare"),
                     ("ModSecurity", "modsec"), ("F5", "f5")],
                    id="smart-waf", value="none",
                )
            with Horizontal(classes="row"):
                yield Label("Count:")
                yield Input("50", id="smart-count", compact=True)
            with Horizontal(id="buttons"):
                yield ToolbarButton("✔ Generate", "btn-smart-ok")
                yield ToolbarButton("✕ Cancel",   "btn-smart-cancel")

    @on(ToolbarButton.Pressed, "#btn-smart-ok")
    def _smart_ok(self, _: ToolbarButton.Pressed) -> None:
        self._generate()

    @on(ToolbarButton.Pressed, "#btn-smart-cancel")
    def _smart_cancel(self, _: ToolbarButton.Pressed) -> None:
        self.action_cancel()

    def _generate(self) -> None:
        try:
            from pentool.core.plugin_manager import load_pro_module
            payloads_pro = load_pro_module("payloads_pro")
            ctx = str(self.query_one("#smart-context", Select).value or "string")
            tech = str(self.query_one("#smart-tech", Select).value or "unknown")
            waf = str(self.query_one("#smart-waf", Select).value or "none")
            count = int(self.query_one("#smart-count", Input).value or "50")
            payloads = payloads_pro.generate_smart_payloads(
                context=ctx,
                tech_hint=tech,
                waf_profile=waf,
                count=max(1, min(count, 500)),
            )
            self.dismiss(payloads)
        except Exception as exc:
            logger.error("Smart Payload Generator failed: %s", exc, exc_info=True)
            try:
                self.app.notify(
                    f"Smart Payload Generator failed: {exc}",
                    severity="error", timeout=6,
                )
            except Exception:
                pass
            self.dismiss(None)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-close-smart":
            self.dismiss(None)

    def on_key(self, event) -> None:
        if event.key == "escape":
            self.dismiss(None)
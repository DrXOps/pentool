"""AppMixin — common helpers for TUI screens that access the app level."""

from __future__ import annotations


class AppMixin:
    """Mixin with helpers for app-level access and cross-module sends."""

    def _get_proxy(self):
        try:
            return self.app.get_proxy_api().proxy  # type: ignore[attr-defined]
        except Exception:
            return None

    def _get_proxy_api(self):
        try:
            return self.app.get_proxy_api()  # type: ignore[attr-defined]
        except Exception:
            return None

    def _get_db_path(self) -> str:
        try:
            return self.app.db_path  # type: ignore[attr-defined]
        except Exception:
            return ""

    def _send_to_decoder(self, text: str) -> None:
        try:
            from pentool.tui.constants import SCREEN_DECODER
            from pentool.tui.screens.decoder.screen import DecoderScreen
            if not text:
                self.app.notify("No text to send", severity="warning")  # type: ignore[attr-defined]
                return
            decoder = self.app.query_one(SCREEN_DECODER, DecoderScreen)  # type: ignore[attr-defined]
            decoder.load_text(text)
            self.app.action_switch_module("decoder")  # type: ignore[attr-defined]
            self.app.notify("Sent to Decoder", timeout=2)  # type: ignore[attr-defined]
        except Exception as exc:
            self.app.notify(f"Could not send to Decoder: {exc}", severity="error")  # type: ignore[attr-defined]

    def _send_to_comparer(self, text: str, label: str = "") -> None:
        try:
            from pentool.tui.constants import SCREEN_COMPARER
            from pentool.tui.screens.comparer.screen import ComparerScreen
            if not text:
                self.app.notify("No text to send", severity="warning")  # type: ignore[attr-defined]
                return
            comparer = self.app.query_one(SCREEN_COMPARER, ComparerScreen)  # type: ignore[attr-defined]
            left_text = comparer.query_one("#cmp-left").text  # type: ignore[attr-defined]
            if left_text.strip():
                comparer.load_right(text, label=label or "Request")
                side = "right"
            else:
                comparer.load_left(text, label=label or "Request")
                side = "left"
            self.app.action_switch_module("comparer")  # type: ignore[attr-defined]
            self.app.notify(f"Sent to Comparer ({side})", timeout=2)  # type: ignore[attr-defined]
        except Exception as exc:
            self.app.notify(f"Could not send to Comparer: {exc}", severity="error")  # type: ignore[attr-defined]

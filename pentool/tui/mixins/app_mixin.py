"""AppMixin — common helpers for TUI screens that access the app level."""

from __future__ import annotations

from pentool.core.error_guard import err as _err


class AppMixin:
    """Mixin with helpers for app-level access and cross-module sends."""

    def err(self, exception: Exception, context: str = "", severity: str = "error") -> None:
        """Log exception + TUI notify — shorthand for error_guard.err."""
        _err(exception, context, self, severity=severity)

    def refresh_header(self) -> None:
        """Ask the app to redraw the module header.

        Screens call this after state changes that alter header buttons (start/stop,
        capture, tab add/remove). A screen can exist without an app in unit tests, so
        the lookup is guarded — the same three lines were copy-pasted in six screens.
        """
        refresh = getattr(getattr(self, "app", None), "refresh_header", None)
        if callable(refresh):
            refresh()

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

    async def _send_to_decoder(self, text: str) -> None:
        """Get-or-mount the Decoder screen and drop *text* into it.

        Async because the target screen may not be mounted at all (lazy screens):
        `ensure_module_screen` mounts it on demand, which is exactly the case "send to
        Decoder from the Proxy context menu without ever opening Decoder".
        """
        try:
            from pentool.tui.screens.decoder.screen import DecoderScreen

            if not text:
                self.notify_user("No text to send", severity="warning")  # type: ignore[attr-defined]
                return
            decoder = await self.app.ensure_module_screen("decoder", DecoderScreen)  # type: ignore[attr-defined]
            if decoder is None:
                self.notify_user("Decoder is unavailable", severity="error")  # type: ignore[attr-defined]
                return
            decoder.load_text(text)
            self.app.action_switch_module("decoder")  # type: ignore[attr-defined]
            self.notify_user("Sent to Decoder", timeout=2)  # type: ignore[attr-defined]
        except Exception as exc:
            self.err(exc, "Could not send to Decoder")

    async def _send_to_comparer(self, text: str, label: str = "") -> None:
        """Get-or-mount the Comparer screen and load *text* on the free side."""
        try:
            from pentool.tui.screens.comparer.screen import ComparerScreen

            if not text:
                self.notify_user("No text to send", severity="warning")  # type: ignore[attr-defined]
                return
            comparer = await self.app.ensure_module_screen("comparer", ComparerScreen)  # type: ignore[attr-defined]
            if comparer is None:
                self.notify_user("Comparer is unavailable", severity="error")  # type: ignore[attr-defined]
                return
            left_text = comparer.query_one("#cmp-left").text  # type: ignore[attr-defined]
            if left_text.strip():
                comparer.load_right(text, label=label or "Request")
                side = "right"
            else:
                comparer.load_left(text, label=label or "Request")
                side = "left"
            self.app.action_switch_module("comparer")  # type: ignore[attr-defined]
            self.notify_user(f"Sent to Comparer ({side})", timeout=2)  # type: ignore[attr-defined]
        except Exception as exc:
            self.err(exc, "Could not send to Comparer")

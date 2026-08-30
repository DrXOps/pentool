"""InterceptMixin — ProxyScreen's Intercept-tab logic (Этап 6, intercept).

Extracted from the proxy mega-screen so the Intercept tab's behaviour —
queueing, Forward/Drop, special-char visualisation, syntax highlighting,
response display, button state — lives in one cohesive slice instead of
being spread through ProxyScreen.

The mixin binds to the screen through the existing AppMixin surface:
- self._get_proxy()            (AppMixin) — the running ProxyService
- self.query_one(sid, cls)     (Widget)    — the screen's descendant widgets
- self.app.action_toggle_intercept() (App)  — global intercept toggle

State lives on the screen (self._intercept_req / _pending /
_show_special_chars / _raw_full), initialized in ProxyScreen.__init__, so no
mixin __init__ is needed and the screen keeps ownership of its attributes.
"""

from __future__ import annotations

from pentool.tui.widgets.toolbar_button import ToolbarButton


class InterceptMixin:
    """Intercept-tab controller mixed into ProxyScreen."""

    def action_forward(self) -> None:
        from textual.widgets import TextArea

        from pentool.tui.widgets.request_editor import HttpView

        proxy = self._get_proxy()
        if proxy is None or self._intercept_req is None:
            return
        req = self._intercept_req
        try:
            editor = self.query_one("#intercept-editor", TextArea)
            modified = editor.text
        except Exception:
            modified = None
        if modified is not None and self._intercept_show_special_chars:
            try:
                from pentool.tui.widgets.request_editor import decode_special_chars

                modified = decode_special_chars(modified)
            except Exception:
                pass
        # Display the sent request in the bottom-left panel
        sent_text = modified if modified and modified.strip() else ""
        try:
            self.query_one("#intercept-sent-req", HttpView).load_raw_http(sent_text)
        except Exception:
            pass
        # Clear the response panel — waiting for the server response
        try:
            self.query_one("#intercept-resp-viewer", HttpView).clear()
        except Exception:
            pass
        proxy.forward(req.id, modified if modified and modified.strip() else None)
        self._intercept_req = None
        # If there are queued requests — show the next one immediately
        if self._intercept_pending:
            next_req = self._intercept_pending.pop(0)
            self._display_intercept_req(next_req)
        else:
            # Disable buttons — response will arrive asynchronously via show_intercept_response
            self._disable_intercept_buttons(hint="⏳ Forwarded — waiting for response…")

    def action_drop(self) -> None:
        from textual.widgets import TextArea

        from pentool.tui.widgets.request_editor import HttpView

        proxy = self._get_proxy()
        if proxy is None or self._intercept_req is None:
            return
        proxy.drop(self._intercept_req.id)
        self._intercept_req = None
        # If there are queued requests — show the next one immediately
        if self._intercept_pending:
            next_req = self._intercept_pending.pop(0)
            self._display_intercept_req(next_req)
            return
        self._disable_intercept_buttons(hint="✖ Dropped")
        # On Drop: clear the top editor and both bottom panels
        try:
            self.query_one("#intercept-editor", TextArea).load_text(
                "(No requests waiting for intercept)"
            )
        except Exception:
            pass
        try:
            self.query_one("#intercept-sent-req", HttpView).clear()
        except Exception:
            pass
        try:
            self.query_one("#intercept-resp-viewer", HttpView).clear()
        except Exception:
            pass

    def _toggle_intercept_special_chars(self, btn: ToolbarButton) -> None:
        """Toggle display of literal \\r\\n / \\n special chars in the Intercept editor."""
        try:
            from pentool.tui.widgets.request_editor import (
                decode_special_chars,
                visualize_special_chars,
            )
            from textual.widgets import TextArea

            editor = self.query_one("#intercept-editor", TextArea)
        except Exception:
            return
        # Commit the current text before switching mode representation
        current = editor.text
        if self._intercept_show_special_chars:
            # Currently showing literal escapes — decode back to raw control chars
            decoded = decode_special_chars(current)
            self._intercept_raw_full = decoded
        else:
            self._intercept_raw_full = current

        self._intercept_show_special_chars = not self._intercept_show_special_chars
        if self._intercept_show_special_chars:
            btn.update("⏎ Special: ON")
            btn.add_class("active")
            editor.load_text(visualize_special_chars(self._intercept_raw_full))
        else:
            btn.update("⏎ Special: OFF")
            btn.remove_class("active")
            editor.load_text(self._intercept_raw_full)
            self._apply_intercept_highlight(self._intercept_raw_full)

    def _apply_intercept_highlight(self, raw: str) -> None:
        """Apply HTTP header syntax highlighting directly on the (full-text) intercept editor."""
        try:
            from collections import defaultdict

            from pentool.tui.widgets.request_editor import _build_http_highlights
            from textual.widgets import TextArea

            editor = self.query_one("#intercept-editor", TextArea)
            normalized = raw.replace("\r\n", "\n")
            editor._highlights = defaultdict(list, _build_http_highlights(normalized))
            editor._line_cache.clear()
            editor.refresh()
        except Exception:
            pass

    def _disable_intercept_buttons(self, hint: str = "") -> None:
        """Disable Forward/Drop and update the hint."""
        from textual.widgets import Label

        try:
            self.query_one("#btn-forward", ToolbarButton).disabled = True
            self.query_one("#btn-drop", ToolbarButton).disabled = True
        except Exception:
            pass
        if hint:
            try:
                self.query_one("#intercept-hint", Label).update(hint)
            except Exception:
                pass

    def show_intercepted_request(self, req: object) -> None:
        """Called from app when a request is intercepted — displays it in the Intercept Tab.

        If another request is already waiting (Forward/Drop not yet pressed),
        the new request is queued. This way the user sees requests one at a time
        and none are lost (the proxy correctly blocks each until resolved).
        """
        from textual.widgets import Label

        if self._intercept_req is not None:
            # Already showing a request — queue the new one
            self._intercept_pending.append(req)
            try:
                self.query_one("#intercept-hint", Label).update(
                    f"⏸ {req.method} {req.url}  (+{len(self._intercept_pending)} queued)"
                )
            except Exception:
                pass
            return
        self._display_intercept_req(req)

    def _display_intercept_req(self, req: object) -> None:
        """Display a request in the Intercept Tab (both initial display and next-in-queue)."""
        from textual.widgets import Label, TabbedContent

        from pentool.tui.widgets.request_editor import HttpView, visualize_special_chars

        self._intercept_req = req
        try:
            from pentool.utils.parser import build_http_request

            raw = build_http_request(req.to_parsed_request())
        except Exception:
            raw = f"{req.method} {req.url}\n\n(could not render request)"
        self._intercept_raw_full = raw
        try:
            from textual.widgets import TextArea

            editor = self.query_one("#intercept-editor", TextArea)
            if self._intercept_show_special_chars:
                editor.load_text(visualize_special_chars(raw))
            else:
                editor.load_text(raw)
                self._apply_intercept_highlight(raw)
        except Exception:
            pass
        # Clear only the response panel — leave Sent Request as-is
        # (it is updated only in action_forward/action_drop)
        try:
            self.query_one("#intercept-resp-viewer", HttpView).clear()
        except Exception:
            pass
        try:
            self.query_one("#btn-forward", ToolbarButton).disabled = False
            self.query_one("#btn-drop", ToolbarButton).disabled = False
        except Exception:
            pass
        queued = len(self._intercept_pending)
        hint = f"⏸ Intercepted: {req.method} {req.url}"
        if queued:
            hint += f"  (+{queued} queued)"
        try:
            self.query_one("#intercept-hint", Label).update(hint)
        except Exception:
            pass
        # Switch to the Intercept tab
        try:
            tabs = self.query_one("#proxy-subtabs", TabbedContent)
            tabs.active = "tab-intercept"
        except Exception:
            pass

    def show_intercept_response(self, req: object) -> None:
        from textual.widgets import Label

        from pentool.tui.widgets.request_editor import HttpView

        if req.response is None:
            return
        try:
            resp = req.response
            status_line = f"HTTP/1.1 {resp.status} {resp.reason}"
            headers = "\r\n".join(f"{k}: {v}" for k, v in resp.headers.items())
            body = resp.body or ""
            raw = f"{status_line}\r\n{headers}\r\n\r\n{body}"
            self.query_one("#intercept-resp-viewer", HttpView).load_raw_http(raw)
        except Exception:
            pass
        try:
            self.query_one("#intercept-hint", Label).update(
                f"✓ Response: {req.response.status} — {req.method} {req.url}"
            )
        except Exception:
            pass

    def action_toggle_intercept(self) -> None:
        self.app.action_toggle_intercept()  # type: ignore[attr-defined]
        self._sync_intercept_button()
        # When intercept is disabled — reset current request and queue,
        # otherwise all queued requests will pop up on the next enable
        proxy = self._get_proxy()
        if proxy and not proxy.intercept_enabled:
            self._intercept_req = None
            self._intercept_pending.clear()
            self._disable_intercept_buttons(hint="(Intercept disabled)")

    def _sync_intercept_button(self) -> None:
        proxy = self._get_proxy()
        try:
            btn = self.query_one("#btn-intercept", ToolbarButton)
        except Exception:
            return
        enabled = proxy and proxy.intercept_enabled
        if enabled:
            btn.label = "● Intercept"
            btn.remove_class("inactive")
            btn.add_class("active")
        else:
            btn.label = "○ Intercept"
            btn.remove_class("active")
            btn.add_class("inactive")

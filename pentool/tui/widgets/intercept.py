"""InterceptMixin — ProxyScreen's Intercept-tab logic (Stage 6, intercept).

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

from typing import Any, Protocol

from textual.css.query import NoMatches

from pentool.api.proxy_api import InterceptedRequest
from pentool.core.logging import get_logger
from pentool.tui.markup import esc
from pentool.tui.widgets.content_panel import ContentPanel
from pentool.tui.widgets.toolbar_button import ToolbarButton

logger = get_logger(__name__)


class _InterceptHost(Protocol):
    """What a class mixing in InterceptMixin must provide.

    Declares the Widget/AppMixin surface the mixin relies on so mypy can
    type-check the methods here without a circular import of ProxyScreen.
    """

    def _get_proxy(self): ...

    def query_one(
        self,
        selector: str | type,
        expect_type: type | tuple[type, ...] | None = None,
        /,
        **kwargs: Any,
    ) -> Any: ...

    @property
    def app(self) -> Any: ...

    # Mixin's own methods are present on the host (ProxyScreen inherits the
    # mixin), so cross-calls between them satisfy this protocol too.
    def _display_intercept_req(self, req: InterceptedRequest) -> None: ...

    def _disable_intercept_buttons(self, hint: str = "") -> None: ...

    def _apply_intercept_highlight(self, raw: str) -> None: ...

    def _sync_intercept_button(self) -> None: ...

    _intercept_req: InterceptedRequest | None
    _intercept_pending: list[InterceptedRequest]
    _intercept_show_special_chars: bool
    _intercept_raw_full: str


class InterceptMixin:
    """Intercept-tab controller mixed into ProxyScreen."""

    def action_forward(self: _InterceptHost) -> None:
        from pentool.tui.widgets.request_editor import HttpView

        proxy = self._get_proxy()
        if proxy is None or self._intercept_req is None:
            return
        req = self._intercept_req
        try:
            editor = self.query_one("#intercept-panel", ContentPanel).content_widget
            modified = editor.text
        except NoMatches as exc:
            # The intercept panel is not in the tree (the tab is not mounted) —
            # send the original request, there is nothing to edit.
            logger.debug("intercept: no editor to read, sending original: %s", exc)
            modified = None
        except Exception:
            # `modified = None` below means "forward the request with no edits".
            # If an editor existed but could not be read, the user's edits are
            # silently lost and the original request goes out — a traceback, not a string.
            logger.exception("intercept: edited request not read, sending original")
            modified = None
        if modified is not None and self._intercept_show_special_chars:
            try:
                from pentool.tui.widgets.request_editor import decode_special_chars

                modified = decode_special_chars(modified)
            except Exception:
                # Literal "\r\n" would go out instead of CRLF — the server replies
                # 400, and the link to the special-chars display stays invisible.
                logger.exception("intercept: special chars not decoded before forward")
        # Display the sent request in the bottom-left panel
        sent_text = modified if modified and modified.strip() else ""
        try:
            self.query_one("#intercept-sent-req", HttpView).load_raw_http(sent_text)
        except NoMatches as exc:
            # The bottom panel would show the previous request under the one just
            # sent — a direct mismatch with what went to the server.
            logger.debug("intercept: sent request not shown: %s", exc)
        # Clear the response panel — waiting for the server response
        try:
            self.query_one("#intercept-resp-viewer", HttpView).clear()
        except NoMatches as exc:
            # The response from the previous intercept stays on screen and will be
            # read as the response to this request.
            logger.debug("intercept: response panel not cleared before forward: %s", exc)
        proxy.forward(req.id, modified if modified and modified.strip() else None)
        self._intercept_req = None
        # If there are queued requests — show the next one immediately
        if self._intercept_pending:
            next_req = self._intercept_pending.pop(0)
            self._display_intercept_req(next_req)
        else:
            # Disable buttons — response will arrive asynchronously via show_intercept_response
            self._disable_intercept_buttons(hint="⏳ Forwarded — waiting for response…")

    def action_drop(self: _InterceptHost) -> None:
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
            self.query_one("#intercept-panel", ContentPanel).content_widget.load_text(
                "(No requests waiting for intercept)"
            )
        except NoMatches as exc:
            # The buttons already say "Dropped", but the editor still holds the
            # discarded request: the user may press Forward on it.
            logger.debug("intercept: editor not reset after drop: %s", exc)
        try:
            self.query_one("#intercept-sent-req", HttpView).clear()
        except NoMatches as exc:
            logger.debug("intercept: sent panel not cleared after drop: %s", exc)
        try:
            self.query_one("#intercept-resp-viewer", HttpView).clear()
        except NoMatches as exc:
            logger.debug("intercept: response panel not cleared after drop: %s", exc)

    def _toggle_intercept_special_chars(self: _InterceptHost, btn: ToolbarButton | None) -> None:
        """Toggle display of literal \\r\\n / \\n special chars in the Intercept editor.

        ``btn`` is the toolbar button that asked for the toggle; when the toggle
        comes from the module header there is no such button (the label lives in
        the header spec), so the button update is skipped and the header redraws.
        """
        try:
            from pentool.tui.widgets.request_editor import decode_special_chars, visualize_special_chars

            editor = self.query_one("#intercept-panel", ContentPanel).content_widget
        except NoMatches as exc:
            # The "Special" button toggles the flag, but if the editor is not
            # found there is nothing to toggle, and the button looks broken.
            logger.debug("intercept: panel not found for special-chars toggle: %s", exc)
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
        label = "⏎ Special: ON" if self._intercept_show_special_chars else "⏎ Special: OFF"
        if btn is not None:
            btn.update(label)
            btn.set_class(self._intercept_show_special_chars, "active")
        if self._intercept_show_special_chars:
            editor.load_text(visualize_special_chars(self._intercept_raw_full))
        else:
            editor.load_text(self._intercept_raw_full)
            self._apply_intercept_highlight(self._intercept_raw_full)
        # The label lives in the header now — redraw it either way.
        refresh = getattr(self.app, "refresh_header", None)
        if refresh is not None:
            refresh()

    def _apply_intercept_highlight(self: _InterceptHost, raw: str) -> None:
        """Apply HTTP header syntax highlighting directly on the (full-text) intercept editor."""
        try:
            from collections import defaultdict

            from pentool.tui.widgets.request_editor import _build_http_highlights

            editor = self.query_one("#intercept-panel", ContentPanel).content_widget
            normalized = raw.replace("\r\n", "\n")
            editor._highlights = defaultdict(list, _build_http_highlights(normalized))
            editor._line_cache.clear()
            editor.refresh()
        except Exception as exc:
            # Highlighting is decoration, but its absence next to an otherwise
            # working editor looks like "it stopped working".
            logger.debug("intercept: header highlighting not applied: %s", exc)

    def _disable_intercept_buttons(self: _InterceptHost, hint: str = "") -> None:
        """Reflect "nothing waiting" in the header and update the hint."""
        from textual.widgets import Label

        # Forward/Drop live in the module header; their enabled state comes from
        # the header spec (queue length), so a redraw is the whole sync.
        self.refresh_header()  # type: ignore[attr-defined]
        if hint:
            try:
                self.query_one("#intercept-hint", Label).update(hint)
            except NoMatches as exc:
                # The hint is the only explanation of why the buttons are grey.
                logger.debug("intercept: hint not updated: %s", exc)

    def show_intercepted_request(self: _InterceptHost, req: InterceptedRequest) -> None:
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
                    f"⏸ {esc(req.method)} {esc(req.url)}  (+{len(self._intercept_pending)} queued)"
                )
            except NoMatches as exc:
                # The request was queued, but the queue counter on screen did not
                # grow — the user does not know another one is waiting.
                logger.debug("intercept: queue hint not updated: %s", exc)
            return
        self._display_intercept_req(req)

    def _display_intercept_req(self: _InterceptHost, req: InterceptedRequest) -> None:
        """Display a request in the Intercept Tab (both initial display and next-in-queue)."""
        from textual.widgets import Label, TabbedContent

        from pentool.tui.widgets.request_editor import HttpView, visualize_special_chars

        self._intercept_req = req
        try:
            from pentool.utils.parser import build_http_request

            raw = build_http_request(req.to_parsed_request())
        except Exception as exc:
            # Show a stub instead of the request — but without the log entry
            # there is no telling what actually came from the proxy.
            logger.debug("intercept: request could not be rendered: %s", exc)
            raw = f"{req.method} {req.url}\n\n(could not render request)"
        self._intercept_raw_full = raw
        try:
            editor = self.query_one("#intercept-panel", ContentPanel).content_widget
            if self._intercept_show_special_chars:
                editor.load_text(visualize_special_chars(raw))
            else:
                editor.load_text(raw)
                self._apply_intercept_highlight(raw)
        except Exception as exc:
            # The request is intercepted and waiting for Forward, but it is not in
            # the editor — the user would send empty or stale content.
            logger.debug("intercept: request not shown in editor: %s", exc)
        # Clear only the response panel — leave Sent Request as-is
        # (it is updated only in action_forward/action_drop)
        try:
            self.query_one("#intercept-resp-viewer", HttpView).clear()
        except NoMatches as exc:
            # A new intercepted request, yet the response panel holds the previous response.
            logger.debug("intercept: response panel not cleared for new request: %s", exc)
        # Forward/Drop are header buttons now: redraw so they become enabled.
        self.refresh_header()  # type: ignore[attr-defined]
        queued = len(self._intercept_pending)
        hint = f"⏸ Intercepted: {req.method} {req.url}"
        if queued:
            hint += f"  (+{queued} queued)"
        try:
            self.query_one("#intercept-hint", Label).update(hint)
        except NoMatches as exc:
            logger.debug("intercept: hint not set for new request: %s", exc)
        # Switch to the Intercept tab
        try:
            tabs = self.query_one("#proxy-subtabs", TabbedContent)
            tabs.active = "tab-intercept"
        except NoMatches as exc:
            # Interception is running, but the user cannot see its tab — the
            # request just hangs, and the UI gives no way to notice that.
            logger.debug("intercept: intercept tab not activated: %s", exc)

    def show_intercept_response(self: _InterceptHost, req: InterceptedRequest) -> None:
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
        except NoMatches as exc:
            # The response arrived, but the panel did not show it — from the Send
            # side it looks like a failure.
            logger.debug("intercept: response not shown: %s", exc)
        try:
            self.query_one("#intercept-hint", Label).update(
                f"✓ Response: {req.response.status} — {esc(req.method)} {esc(req.url)}"
            )
        except NoMatches as exc:
            # The hint line will stay on "Forwarded — waiting…" forever.
            logger.debug("intercept: response hint not updated: %s", exc)

    def action_toggle_intercept(self: _InterceptHost) -> None:
        self.app.action_toggle_intercept()  # type: ignore[attr-defined]
        self._sync_intercept_button()
        # When intercept is disabled — reset current request and queue,
        # otherwise all queued requests will pop up on the next enable
        proxy = self._get_proxy()
        if proxy and not proxy.intercept_enabled:
            self._intercept_req = None
            self._intercept_pending.clear()
            self._disable_intercept_buttons(hint="(Intercept disabled)")

    def _sync_intercept_button(self: _InterceptHost) -> None:
        """Repaint the intercept state in the module header (spec reads the proxy)."""
        self.refresh_header()  # type: ignore[attr-defined]

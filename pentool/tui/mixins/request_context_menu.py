"""RequestContextMenuMixin — standardised context menu for HTTP requests."""

from __future__ import annotations


class RequestContextMenuMixin:
    """Unified HTTP request context menu for all modules."""

    # ── Item flags (override in subclass) ────────────────────────────────────
    _cm_show_copy_url:      bool = False
    _cm_show_ffuf:          bool = True
    _cm_show_sqlmap:        bool = True
    _cm_show_nmap:          bool = False
    _cm_show_jwt:           bool = True
    _cm_show_save_txt:      bool = True
    _cm_show_send_repeater: bool = True
    _cm_show_send_intruder: bool = False
    _cm_show_send_scanner:  bool = False
    _cm_show_send_decoder:  bool = False
    _cm_show_send_comparer: bool = False

    # ── Required interface ────────────────────────────────────────────────────

    def _cm_get_raw_request(self) -> str:
        return ""

    # ── Optional hook ─────────────────────────────────────────────────────────

    def _cm_on_custom_action(self, action: str) -> bool:
        """Handle custom action. Return True if handled."""
        return False

    # ── Public entry point ────────────────────────────────────────────────────

    def cm_open_text_menu(self, x: int, y: int) -> None:
        items = self._cm_build_items()
        self.app.show_context_menu(  # type: ignore[attr-defined]
            items, x, y, callback=self._cm_handle
        )

    # ── Building items ────────────────────────────────────────────────────────

    def _cm_build_items(self) -> list[tuple[str, str]]:
        items: list[tuple[str, str]] = [
            ("text_copy",       "Copy"),
            ("text_select_all", "Select All"),
            ("-", ""),
        ]
        if self._cm_show_copy_url:
            items.append(("copy_url", "Copy URL"))
        items += [
            ("copy_curl",  "Copy as curl"),
            ("copy_fetch", "Copy as fetch()"),
        ]
        if self._cm_show_ffuf:
            items.append(("copy_ffuf",   "Copy as ffuf"))
        if self._cm_show_sqlmap:
            items.append(("copy_sqlmap", "Copy as sqlmap"))
        if self._cm_show_nmap:
            items.append(("copy_nmap",   "Copy as nmap"))
        if self._cm_show_jwt:
            items.append(("copy_jwt",    "Copy as jwt_tool"))
        items += [
            ("-", ""),
            ("open_browser", "Open in Browser"),
        ]
        if self._cm_show_save_txt:
            items += [
                ("-", ""),
                ("save_req_txt", "Save request.txt"),
            ]
        # Send-to group
        send_items: list[tuple[str, str]] = []
        if self._cm_show_send_repeater:
            send_items.append(("send_repeater", "Send to Repeater"))
        if self._cm_show_send_intruder:
            send_items.append(("send_intruder", "Send to Intruder"))
        if self._cm_show_send_scanner:
            send_items.append(("send_scanner",  "Send to Scanner"))
        if send_items:
            items.append(("-", ""))
            items += send_items
        # Decoder/Comparer group
        tool_items: list[tuple[str, str]] = []
        if self._cm_show_send_decoder:
            tool_items.append(("send_decoder",  "Send to Decoder"))
        if self._cm_show_send_comparer:
            tool_items.append(("send_comparer", "Send to Comparer"))
        if tool_items:
            items.append(("-", ""))
            items += tool_items
        return items

    # ── Dispatcher ────────────────────────────────────────────────────────────

    def _cm_handle(self, action: str) -> None:
        if self._cm_on_custom_action(action):
            return
        if action == "text_copy":
            self._cm_do_copy_selection()
            return
        if action == "text_select_all":
            self._cm_do_select_all()
            return
        raw = self._cm_get_raw_request()
        if action == "copy_url":
            self._cm_do_copy_url(raw)
        elif action in ("copy_curl", "copy_fetch", "copy_ffuf",
                        "copy_sqlmap", "copy_nmap", "copy_jwt"):
            self._cm_do_copy_as(action, raw)
        elif action == "open_browser":
            self._cm_do_open_browser(raw)
        elif action == "save_req_txt":
            self._cm_do_save_txt(raw)
        elif action == "send_repeater":
            self._cm_do_send_repeater(raw)
        elif action == "send_intruder":
            self._cm_do_send_intruder(raw)
        elif action == "send_scanner":
            self._cm_do_send_scanner(raw)
        elif action == "send_decoder":
            self._cm_do_send_decoder(raw)
        elif action == "send_comparer":
            self._cm_do_send_comparer(raw)

    # ── Action implementations ────────────────────────────────────────────────

    def _cm_do_copy_selection(self) -> None:
        try:
            from pentool.utils.copy_as import copy_to_clipboard
            focused = self.app.focused  # type: ignore[attr-defined]
            text = ""
            if hasattr(focused, "selected_text"):
                text = focused.selected_text or ""
            elif hasattr(focused, "text"):
                text = focused.text or ""
            if text:
                copy_to_clipboard(text)
        except Exception:
            pass

    def _cm_do_select_all(self) -> None:
        try:
            focused = self.app.focused  # type: ignore[attr-defined]
            if hasattr(focused, "select_all"):
                focused.select_all()
        except Exception:
            pass

    def _cm_do_copy_url(self, raw: str) -> None:
        from pentool.utils.copy_as import extract_url_from_raw, copy_to_clipboard
        url = extract_url_from_raw(raw)
        if url and copy_to_clipboard(url):
            self.app.notify("URL copied", timeout=2)  # type: ignore[attr-defined]
        elif not url:
            self.app.notify("No URL found", severity="warning", timeout=2)  # type: ignore[attr-defined]

    def _cm_do_copy_as(self, action: str, raw: str) -> None:
        if not raw.strip():
            self.app.notify("No request", severity="warning", timeout=2)  # type: ignore[attr-defined]
            return
        from pentool.utils.copy_as import (
            copy_as_curl, copy_as_fetch, copy_as_ffuf,
            copy_as_sqlmap, copy_as_nmap, copy_as_jwt_tool,
            copy_to_clipboard,
        )
        from pentool.utils.parser import parse_http_request
        try:
            req = parse_http_request(raw)
        except Exception as exc:
            self.app.notify(f"Parse error: {exc}", severity="error")  # type: ignore[attr-defined]
            return
        _MAP = {
            "copy_curl":   (copy_as_curl,     "curl"),
            "copy_fetch":  (copy_as_fetch,    "fetch()"),
            "copy_ffuf":   (copy_as_ffuf,     "ffuf"),
            "copy_sqlmap": (copy_as_sqlmap,   "sqlmap"),
            "copy_nmap":   (copy_as_nmap,     "nmap"),
            "copy_jwt":    (copy_as_jwt_tool, "jwt_tool"),
        }
        fn, label = _MAP[action]
        text = fn(req)
        if copy_to_clipboard(text):
            self.app.notify(f"{label} copied", timeout=2)  # type: ignore[attr-defined]
        else:
            self.app.notify(  # type: ignore[attr-defined]
                f"Clipboard unavailable.\n{text[:80]}",
                severity="warning", timeout=5,
            )

    def _cm_do_open_browser(self, raw: str) -> None:
        from pentool.utils.copy_as import extract_url_from_raw, open_in_browser
        url = extract_url_from_raw(raw)
        if url:
            open_in_browser(url)
            self.app.notify(f"Opening: {url[:60]}", timeout=2)  # type: ignore[attr-defined]
        else:
            self.app.notify("No URL found", severity="warning", timeout=2)  # type: ignore[attr-defined]

    def _cm_do_save_txt(self, raw: str) -> None:
        if not raw.strip():
            self.app.notify("No request", severity="warning", timeout=2)  # type: ignore[attr-defined]
            return
        import os
        from pentool.utils.copy_as import save_request_txt
        from pentool.utils.parser import parse_http_request
        try:
            req = parse_http_request(raw)
            path = os.path.expanduser("~/request.txt")
            save_request_txt(req, path)
            self.app.notify(f"Saved → {path}", timeout=3)  # type: ignore[attr-defined]
        except Exception as exc:
            self.app.notify(f"Save failed: {exc}", severity="error")  # type: ignore[attr-defined]

    def _cm_do_send_repeater(self, raw: str) -> None:
        if not raw.strip():
            self.app.notify("No request", severity="warning", timeout=2)  # type: ignore[attr-defined]
            return
        from pentool.tui.messages import SendToRepeater
        self.app.post_message(SendToRepeater(raw))  # type: ignore[attr-defined]

    def _cm_do_send_intruder(self, raw: str) -> None:
        if not raw.strip():
            self.app.notify("No request", severity="warning", timeout=2)  # type: ignore[attr-defined]
            return
        from pentool.tui.messages import SendToIntruder
        self.app.post_message(SendToIntruder(raw))  # type: ignore[attr-defined]

    def _cm_do_send_scanner(self, raw: str) -> None:
        if not raw.strip():
            self.app.notify("No request", severity="warning", timeout=2)  # type: ignore[attr-defined]
            return
        try:
            from pentool.utils.parser import parse_http_request
            from pentool.tui.messages import SendRequestToScanner
            req = parse_http_request(raw)
            self.app.post_message(SendRequestToScanner(req))  # type: ignore[attr-defined]
        except Exception as exc:
            self.app.notify(f"Send to Scanner failed: {exc}", severity="error")  # type: ignore[attr-defined]

    def _cm_do_send_decoder(self, raw: str) -> None:
        """Requires AppMixin in the inheritance chain."""
        self._send_to_decoder(raw)  # type: ignore[attr-defined]

    def _cm_do_send_comparer(self, raw: str) -> None:
        """Requires AppMixin in the inheritance chain."""
        self._send_to_comparer(raw, label="Request")  # type: ignore[attr-defined]

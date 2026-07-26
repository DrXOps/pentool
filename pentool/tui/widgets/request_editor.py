"""HTTP request/response editor widget with syntax highlighting."""

from __future__ import annotations

import time
from collections import defaultdict

from textual.app import ComposeResult
from textual import events as _tevents
from textual.message import Message
from textual.widget import Widget
from textual.widgets import Static, TextArea
from textual.widgets.text_area import Selection

from pentool.utils.parser import ParsedRequest, ParsedResponse, build_http_request
from pathlib import Path

_CSS = (Path(__file__).parent / "request_editor.tcss").read_text(encoding="utf-8")


_METHOD_COLORS = {
    "GET": "keyword", "POST": "string", "PUT": "string",
    "DELETE": "tag", "PATCH": "string", "HEAD": "keyword",
    "OPTIONS": "comment", "TRACE": "comment",
}

_HEADER_TOKEN = {
    "host": "function", "content-type": "function", "authorization": "tag",
    "cookie": "tag", "set-cookie": "tag", "location": "function",
    "user-agent": "comment", "accept": "comment", "accept-encoding": "comment",
    "accept-language": "comment", "connection": "comment", "referer": "comment",
    "origin": "comment", "content-length": "comment", "transfer-encoding": "comment",
    "x-frame-options": "tag", "x-content-type-options": "tag",
    "strict-transport-security": "tag",
}


def _build_http_highlights(text: str) -> dict:
    """Build a highlight map for raw HTTP request/response.

    Returns dict[int, list[(col_start, col_end|None, token_name)]]
    compatible with TextArea._highlights.
    """
    highlights: dict = defaultdict(list)
    lines = text.split("\n")
    in_headers = True
    header_end_row = 0

    for row, line in enumerate(lines):
        if in_headers and line.strip() == "":
            in_headers = False
            header_end_row = row
            continue

        if in_headers:
            if row == 0:
                # Status line: method/protocol
                parts = line.split(" ", 2)
                if parts:
                    token = _METHOD_COLORS.get(parts[0].upper(), "keyword")
                    highlights[row].append((0, len(parts[0]), token))
                    if len(parts) >= 2:
                        # path — highlight query parameters as string
                        path_start = len(parts[0]) + 1
                        path = parts[1]
                        if "?" in path:
                            q = path.index("?")
                            highlights[row].append((path_start, path_start + q + 1, "comment"))
                            # key=value in query string
                            offset = path_start + q + 1
                            for pair in path[q + 1:].split("&"):
                                if "=" in pair:
                                    k, _, v = pair.partition("=")
                                    highlights[row].append((offset, offset + len(k), "function"))
                                    highlights[row].append((offset + len(k) + 1, offset + len(pair), "string"))
                                offset += len(pair) + 1
                        else:
                            highlights[row].append((path_start, path_start + len(path), "comment"))
            else:
                # Header: Name: value
                if ":" in line:
                    name, _, value = line.partition(":")
                    token = _HEADER_TOKEN.get(name.strip().lower(), "variable")
                    highlights[row].append((0, len(name), token))
                    highlights[row].append((len(name), len(name) + 1, "operator"))
                    # Cookie/Set-Cookie: highlight key=value
                    if name.strip().lower() in ("cookie", "set-cookie"):
                        offset = len(name) + 2  # ": "
                        for pair in value.lstrip().split("; "):
                            if "=" in pair:
                                k, _, v = pair.partition("=")
                                highlights[row].append((offset, offset + len(k), "function"))
                                highlights[row].append((offset + len(k) + 1, offset + len(pair), "string"))
                            offset += len(pair) + 2
        # body — no highlights (TextArea language handles it)

    return highlights


def _select_word_at_cursor(area: TextArea) -> None:
    """Select word under cursor in TextArea (for double-click)."""
    try:
        cursor = area.cursor_location
        row, col = cursor
        lines = area.text.split("\n")
        if row >= len(lines):
            return
        line = lines[row]
        start = col
        while start > 0 and (line[start - 1].isalnum() or line[start - 1] in "_-./"):
            start -= 1
        end = col
        while end < len(line) and (line[end].isalnum() or line[end] in "_-./"):
            end += 1
        if start < end:
            area.selection = Selection((row, start), (row, end))
    except Exception:
        pass

# Languages supported by the built-in TextArea highlighter
_SUPPORTED_LANGS = {
    "json", "html", "xml", "javascript", "css",
    "python", "sql", "bash", "yaml", "toml", "markdown",
}

_HEADER_COLORS: dict[str, str] = {
    "host": "cyan", "content-type": "green", "content-length": "dim green",
    "authorization": "bold yellow", "cookie": "yellow", "set-cookie": "bold yellow",
    "location": "bold cyan", "server": "dim magenta", "date": "dim",
    "x-frame-options": "dim red", "x-content-type-options": "dim red",
    "strict-transport-security": "dim red", "access-control-allow-origin": "magenta",
    "www-authenticate": "bold red",
}
_METHOD_RICH = {
    "GET": "bold green", "POST": "bold yellow", "PUT": "bold cyan",
    "DELETE": "bold red", "PATCH": "bold magenta", "HEAD": "green",
    "OPTIONS": "dim cyan", "TRACE": "dim",
}


def _hl_qs(path: str) -> str:
    if "?" not in path:
        return f"[cyan]{path}[/cyan]"
    base, qs = path.split("?", 1)
    parts = []
    for pair in qs.split("&"):
        if "=" in pair:
            k, v = pair.split("=", 1)
            parts.append(f"[cyan]{k}[/cyan][dim]=[/dim][yellow]{v}[/yellow]")
        else:
            parts.append(f"[cyan]{pair}[/cyan]")
    return f"[cyan]{base}[/cyan][dim]?[/dim]" + "[dim]&[/dim]".join(parts)


def _hl_cookie(value: str) -> str:
    parts = []
    for pair in value.split("; "):
        if "=" in pair:
            k, v = pair.split("=", 1)
            parts.append(f"[cyan]{k}[/cyan][dim]=[/dim][yellow]{v}[/yellow]")
        else:
            parts.append(f"[dim]{pair}[/dim]")
    return "[dim]; [/dim]".join(parts)


def _render_headers_rich(status_line: str, headers: dict) -> str:
    lines: list[str] = []
    if status_line.startswith("HTTP/"):
        proto, *rest = status_line.split(" ", 2)
        code = rest[0] if rest else ""
        reason = rest[1] if len(rest) > 1 else ""
        c = int(code) if code.isdigit() else 0
        cc = "bold green" if c < 300 else ("bold yellow" if c < 400 else "bold red")
        lines.append(f"[dim]{proto}[/dim] [{cc}]{code} {reason}[/{cc}]")
    else:
        parts = status_line.split(" ", 2)
        method = parts[0] if parts else ""
        path = parts[1] if len(parts) > 1 else ""
        proto = parts[2] if len(parts) > 2 else ""
        mc = _METHOD_RICH.get(method.upper(), "bold white")
        lines.append(f"[{mc}]{method}[/{mc}] {_hl_qs(path)} [dim]{proto}[/dim]")
    for name, value in headers.items():
        color = _HEADER_COLORS.get(name.lower(), "white")
        if name.lower() in ("cookie", "set-cookie"):
            lines.append(f"[{color}]{name}[/{color}][dim]:[/dim] {_hl_cookie(value)}")
        else:
            lines.append(f"[{color}]{name}[/{color}][dim]:[/dim] {value}")
    return "\n".join(lines)


def _get_content_type(headers: dict) -> str:
    """Extract Content-Type from headers (case-insensitive)."""
    for k, v in headers.items():
        if k.lower() == "content-type":
            return v
    return ""


def _detect_language(content_type: str, body: str) -> str | None:
    """Detect highlight language from Content-Type and response body."""
    ct = (content_type or "").lower()
    if "json" in ct:
        return "json"
    if "html" in ct:
        return "html"
    if "xml" in ct:
        return "xml"
    if "javascript" in ct or "ecmascript" in ct:
        return "javascript"
    if "css" in ct:
        return "css"
    if "sql" in ct:
        return "sql"
    if "yaml" in ct:
        return "yaml"
    # Detect from body (heuristic)
    body_strip = (body or "").lstrip()
    if body_strip.startswith("{") or body_strip.startswith("["):
        return "json"
    if body_strip.startswith("<html") or body_strip.startswith("<!DOCTYPE"):
        return "html"
    if body_strip.startswith("<?xml") or body_strip.startswith("<"):
        return "xml"
    return None


class _BaseHttpWidget(Widget):
    """Base class for HTTP widgets: shared on_event (double-click / Ctrl+click)
    and helper _set_text* methods.

    Subclasses must declare:
        _textarea_id: str  — id of TextArea inside compose()
    """

    DEFAULT_CSS = _CSS

    _textarea_id: str = ""       # override in subclass
    _last_click_time: float = 0.0

    class ContextMenuRequest(Message):
        """Ctrl+click — context menu request."""
        def __init__(self, screen_x: int, screen_y: int) -> None:
            super().__init__()
            self.screen_x = screen_x
            self.screen_y = screen_y

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._last_click_time = 0.0

    async def on_event(self, event: _tevents.Event) -> None:
        """Intercept Ctrl+click and double-click."""
        if isinstance(event, _tevents.MouseDown) and event.button == 1:
            now = time.monotonic()
            if not event.ctrl and (now - self._last_click_time) < 0.4:
                self._last_click_time = 0.0
                await super().on_event(event)
                try:
                    area = self.query_one(f"#{self._textarea_id}", TextArea)
                    self.call_after_refresh(_select_word_at_cursor, area)
                except Exception:
                    pass
                return
            self._last_click_time = now
            if event.ctrl:
                await super().on_event(event)
                self.post_message(self.ContextMenuRequest(event.screen_x, event.screen_y))
                return
        elif isinstance(event, _tevents.MouseDown) and event.button == 3:
            await super().on_event(event)
            self.post_message(self.ContextMenuRequest(event.screen_x, event.screen_y))
            return
        await super().on_event(event)

    def _set_text_with_lang(self, text: str, lang: str | None) -> None:
        try:
            area = self.query_one(f"#{self._textarea_id}", TextArea)
            area.language = lang if lang in _SUPPORTED_LANGS else None
            area.load_text(text)
        except Exception:
            pass

    def _set_text(self, text: str) -> None:
        try:
            area = self.query_one(f"#{self._textarea_id}", TextArea)
            area.language = None
            area.load_text(text)
        except Exception:
            pass


def _load_into_textarea(area: TextArea, text: str,
                        highlight_terms: list[str] | None = None) -> None:
    normalized = text.replace("\r\n", "\n")
    area.language = None
    area.load_text(normalized)
    hl = defaultdict(list, _build_http_highlights(normalized))

    if highlight_terms:
        lines = normalized.split("\n")
        for row, line in enumerate(lines):
            for term in highlight_terms:
                if not term:
                    continue
                start = 0
                while True:
                    idx = line.find(term, start)
                    if idx < 0:
                        break
                    hl[row].append((idx, idx + len(term), "tag"))
                    start = idx + len(term)

    area._highlights = hl
    area._line_cache.clear()
    area.refresh()


class HttpView(_BaseHttpWidget):
    """Read-only viewer of HTTP request or response.

    The full raw (headers + body) is loaded into a single TextArea.
    Header highlighting — via _highlights; body — without syntax highlighter.
    """

    _textarea_id = "http-body"

    def compose(self) -> ComposeResult:
        yield TextArea("", read_only=True, id="http-body", soft_wrap=False)

    def load_raw_http(self, text: str,
                      highlight_terms: list[str] | None = None) -> None:
        if not text or not text.strip():
            self.clear()
            return
        try:
            area = self.query_one("#http-body", TextArea)
            _load_into_textarea(area, text, highlight_terms)
        except Exception:
            pass

    def clear(self) -> None:
        self._set_text("")


class RequestEditor(_BaseHttpWidget):
    """Editable HTTP request field with header and body highlighting."""

    _textarea_id = "editor-area"

    def __init__(self, label: str = "Request", read_only: bool = False, **kwargs) -> None:
        super().__init__(**kwargs)
        self._label = label
        self._read_only = read_only
        self._raw_full: str = ""
        self._headers_part: str = ""
        self._special_chars_mode: bool = False

    def compose(self) -> ComposeResult:
        yield Static(f" {self._label}", classes="editor-label")
        yield TextArea(
            "",
            language=None,
            read_only=self._read_only,
            id="editor-area",
            show_line_numbers=True,
            soft_wrap=False,
        )

    def load_request(self, req: ParsedRequest) -> None:
        raw = build_http_request(req)
        self.load_raw(raw)

    def load_raw(self, text: str) -> None:
        normalized = text.replace("\r\n", "\n")
        self._raw_full = text
        self._special_chars_mode = False

        # Determine body highlight language
        if "\n\n" in normalized:
            headers_part, body = normalized.split("\n\n", 1)
            self._headers_part = headers_part
        else:
            headers_part, body = normalized, ""
            self._headers_part = headers_part

        headers: dict[str, str] = {}
        for line in headers_part.split("\n")[1:]:
            if ":" in line:
                name, _, value = line.partition(":")
                headers[name.strip()] = value.strip()
        lang = _detect_language(_get_content_type(headers), body)

        try:
            area = self.query_one("#editor-area", TextArea)
            area.language = None
            area.load_text(normalized)
            # Apply HTTP header highlighting on top of text
            area._highlights = defaultdict(list, _build_http_highlights(normalized))
            area._line_cache.clear()
            area.refresh()
        except Exception:
            pass

    def get_text(self) -> str:
        try:
            raw_area = self.query_one("#editor-area", TextArea).text
        except Exception:
            raw_area = ""

        if self._special_chars_mode:
            return self._decode_special_chars(raw_area)
        return raw_area

    @staticmethod
    def _decode_special_chars(text: str) -> str:
        lines = text.split("\n")
        result = []
        for i, line in enumerate(lines):
            if line.endswith("\\r\\n"):
                result.append(line[:-4] + "\r\n")
            elif line.endswith("\\r"):
                result.append(line[:-2] + "\r")
            elif line.endswith("\\n"):
                result.append(line[:-2] + "\n")
            else:
                if i < len(lines) - 1:
                    result.append(line + "\n")
                else:
                    result.append(line)
        return "".join(result)

    def clear(self) -> None:
        self._raw_full = ""
        self._headers_part = ""
        self._special_chars_mode = False
        self._set_text("")


class ResponseViewer(_BaseHttpWidget):
    """HTTP response viewer panel with header and body highlighting."""

    _textarea_id = "viewer-area"

    def __init__(self, label: str = "Response", **kwargs) -> None:
        super().__init__(**kwargs)
        self._label = label

    def compose(self) -> ComposeResult:
        yield Static(f" {self._label}", classes="viewer-label", id="viewer-label")
        yield TextArea("", read_only=True, id="viewer-area", soft_wrap=False)

    def load_response(self, resp: ParsedResponse) -> None:
        """Display ParsedResponse: full raw HTTP in a single TextArea with _highlights."""
        body = resp.body or ""

        # Build raw HTTP string
        status_line = f"HTTP/1.1 {resp.status} {resp.reason}"
        headers_str = "\r\n".join(f"{k}: {v}" for k, v in resp.headers.items())
        raw = f"{status_line}\r\n{headers_str}\r\n\r\n{body}"

        # Update label: status + size
        try:
            size = len(body.encode("utf-8", errors="replace"))
            size_str = f"{size} B" if size < 1024 else f"{size // 1024} KB"
            ct = _get_content_type(resp.headers)
            lang = _detect_language(ct, body)
            lang_str = f"  [{lang}]" if lang else ""
            label_text = f" {self._label}  ·  {resp.status} {resp.reason}  ·  {size_str}{lang_str}"
            self.query_one("#viewer-label", Static).update(label_text)
        except Exception:
            pass

        try:
            area = self.query_one("#viewer-area", TextArea)
            _load_into_textarea(area, raw)
        except Exception:
            pass

    def load_raw(self, text: str) -> None:
        self._reset_label()
        try:
            area = self.query_one("#viewer-area", TextArea)
            _load_into_textarea(area, text)
        except Exception:
            pass

    def clear(self) -> None:
        self._reset_label()
        self._set_text("")

    def _reset_label(self) -> None:
        try:
            self.query_one("#viewer-label", Static).update(f" {self._label}")
        except Exception:
            pass

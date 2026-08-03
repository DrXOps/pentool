"""InspectorPanel — right sidebar with HTTP request/response details."""

from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from textual.app import ComposeResult
from textual.widget import Widget
from textual.widgets import Static

_CSS = (Path(__file__).parent / "inspector_panel.tcss").read_text(encoding="utf-8")


class InspectorPanel(Widget):
    """Right sidebar with details of the selected request and response."""

    DEFAULT_CSS = _CSS

    def compose(self) -> ComposeResult:
        yield Static("(Select a request)", id="inspector-placeholder")

    def load(self, req, resp=None) -> None:
        widgets = self._build_widgets(req, resp)
        self.app.call_after_refresh(self._apply, widgets)

    def clear(self) -> None:
        """Reset the panel."""
        placeholder = [Static("(Select a request)", id="inspector-placeholder")]
        self.app.call_after_refresh(self._apply, placeholder)

    async def _apply(self, widgets: list[Widget]) -> None:
        await self.remove_children()
        await self.mount(*widgets)

    def _build_widgets(self, req, resp) -> list[Widget]:
        widgets: list[Widget] = []
        req_headers = dict(req.headers) if req.headers else {}

        # Reconstruct full URL if it contains only a path
        url = req.url or ""
        if url and not url.startswith("http://") and not url.startswith("https://"):
            host = req_headers.get("Host", req_headers.get("host", ""))
            if host:
                scheme = "https" if req_headers.get("X-Forwarded-Proto", "") == "https" or "443" in host else "http"
                url = f"{scheme}://{host}{url}"

        self._add_section(widgets, "Request Attributes", {
            "Method":    req.method,
            "URL":       url or "(unknown)",
            "HTTP":      getattr(req, "http_version", "HTTP/1.1"),
            "Body size": f"{len(req.body) if req.body else 0} bytes",
        })
        self._add_section(widgets, "Request Headers", req_headers)

        try:
            parsed_url = urlparse(req.url)
            qparams = {k: ", ".join(v) for k, v in parse_qs(parsed_url.query).items()}
        except Exception:
            qparams = {}
        self._add_section(widgets, "Query Parameters", qparams)

        body_params: dict[str, str] = {}
        if req.body:
            body_text = req.body if isinstance(req.body, str) else req.body.decode("utf-8", errors="replace")
            ct = req_headers.get("Content-Type", req_headers.get("content-type", ""))
            if "application/x-www-form-urlencoded" in ct:
                try:
                    body_params = {k: ", ".join(v) for k, v in parse_qs(body_text).items()}
                except Exception:
                    pass
            elif "application/json" in ct:
                try:
                    d = json.loads(body_text)
                    if isinstance(d, dict):
                        body_params = {k: str(v) for k, v in d.items()}
                except Exception:
                    pass
        self._add_section(widgets, "Body Parameters", body_params)

        cookies: dict[str, str] = {}
        for part in req_headers.get("Cookie", req_headers.get("cookie", "")).split(";"):
            part = part.strip()
            if "=" in part:
                k, v = part.split("=", 1)
                cookies[k.strip()] = v.strip()
        self._add_section(widgets, "Cookies", cookies)

        if resp is not None:
            resp_headers = dict(resp.headers) if hasattr(resp, "headers") and resp.headers else {}
            status = f"HTTP {resp.status}" if hasattr(resp, "status") else "?"
            self._add_section(widgets, f"Response Headers ({status})", resp_headers)
        else:
            self._add_section(widgets, "Response Headers", {})

        return widgets

    @staticmethod
    def _add_section(widgets: list, title: str, items: dict) -> None:
        widgets.append(Static(f" {title}", classes="section-title"))
        if not items:
            widgets.append(Static("  (none)", classes="empty-msg"))
        else:
            for key, value in items.items():
                val_str = str(value)
                if len(val_str) > 55:
                    val_str = val_str[:52] + "…"
                widgets.append(
                    Static(f"  [bold]{key}[/bold]: {val_str}", classes="kv-row", markup=True)
                )

"""Dialog for loading a request from proxy history into Repeater."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING
from urllib.parse import urlparse

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, DataTable, Label

_CSS = (Path(__file__).parent / "load_from_proxy.tcss").read_text(encoding="utf-8")

if TYPE_CHECKING:
    pass


class LoadFromProxyDialog(ModalScreen[str | None]):
    """Modal dialog for selecting a request from proxy history.

    Args:
        requests: List of InterceptedRequest from ProxyServer.

    Returns:
        Raw HTTP request string on selection, None on cancel.
    """

    DEFAULT_CSS = _CSS

    BINDINGS = [
        Binding("escape", "cancel", "Cancel"),
        Binding("enter", "select", "Select"),
    ]

    def __init__(self, requests: list) -> None:
        super().__init__()
        self._requests = requests
        self._selected_raw: str | None = None

    def compose(self) -> ComposeResult:
        with Vertical(id="dialog"):
            yield Label("Load Request from Proxy", id="title")
            yield Label("Double-click or press Enter to select a request", id="hint")
            yield DataTable(
                id="req-table",
                cursor_type="row",
                zebra_stripes=True,
            )
            with Horizontal(id="buttons"):
                yield Button("Load",   variant="primary", id="btn-load")
                yield Button("Cancel", variant="default", id="btn-cancel")

    def on_mount(self) -> None:
        table = self.query_one("#req-table", DataTable)
        table.add_columns("Method", "URL", "Status", "Host")
        for req in self._requests:
            status = str(req.response.status) if req.response else "…"
            url_s = req.url[:60] + "…" if len(req.url) > 60 else req.url
            parsed = urlparse(req.url)
            host = parsed.netloc or req.headers.get("Host", "")
            table.add_row(req.method, url_s, status, host, key=req.id)

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        """Remember the selected request."""
        row_key = str(event.row_key.value) if event.row_key else None
        if row_key is None:
            return
        req = self._find_request(row_key)
        if req is not None:
            self._selected_raw = self._build_raw(req)

    def on_data_table_row_activated(self, event: DataTable.RowActivated) -> None:
        """Double-click — load immediately."""
        self.action_select()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-load":
            self.action_select()
        else:
            self.action_cancel()

    def action_select(self) -> None:
        if self._selected_raw:
            self.dismiss(self._selected_raw)
        else:
            # Take current cursor row
            table = self.query_one("#req-table", DataTable)
            try:
                table.get_row_at(table.cursor_row)
            except Exception:
                self.dismiss(None)
                return
            # row_key — row key, find the corresponding request
            cursor_row_key = None
            for i, (key, _) in enumerate(table._data.items()):
                if i == table.cursor_row:
                    cursor_row_key = str(key)
                    break
            if cursor_row_key:
                req = self._find_request(cursor_row_key)
                if req:
                    self.dismiss(self._build_raw(req))
                    return
            self.dismiss(None)

    def action_cancel(self) -> None:
        self.dismiss(None)

    def _find_request(self, req_id: str) -> object | None:
        for req in self._requests:
            if req.id == req_id:
                return req
        return None

    def _build_raw(self, req: object) -> str:
        """Build raw HTTP request string from InterceptedRequest."""
        try:
            parsed = req.to_parsed_request()  # type: ignore[attr-defined]
            from pentool.utils.parser import build_http_request
            return build_http_request(parsed)
        except Exception:
            return ""

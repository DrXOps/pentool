"""Intruder Auto-Mark dialog — choose which parts to mark with §§."""

from __future__ import annotations

from pathlib import Path

from textual import on
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import Label

from pentool.tui.dialogs.base_dialog import BaseDialog
from pentool.tui.widgets.nice_checkbox import NiceCheckbox as Checkbox
from pentool.tui.widgets.toolbar_button import ToolbarButton


_CSS = (Path(__file__).parent / "intruder_auto_mark.tcss").read_text(encoding="utf-8")


class IntruderAutoMarkDialog(BaseDialog):
    """Dialog choosing what to auto-mark with §§ markers.

    Returns a dict with boolean keys, or None on cancel.
    """

    DEFAULT_CSS = _CSS

    def __init__(self, has_json: bool = False, has_xml: bool = False,
                 has_urlencoded: bool = True, has_query: bool = True,
                 has_cookie: bool = True, has_header: bool = True) -> None:
        super().__init__()
        self._has_json = has_json
        self._has_xml = has_xml
        self._has_urlencoded = has_urlencoded
        self._has_query = has_query
        self._has_cookie = has_cookie
        self._has_header = has_header

    def compose(self) -> ComposeResult:
        with Vertical(id="dialog"):
            yield Label("[bold]Auto-Mark Parameters[/bold]", id="title")

        if self._has_query:
            with Horizontal(classes="row"):
                yield Checkbox("URL query params", value=True, id="mark-query")
        if self._has_urlencoded:
            with Horizontal(classes="row"):
                yield Checkbox("Body (form-urlencoded)", value=True, id="mark-body-form")
        if self._has_cookie:
            with Horizontal(classes="row"):
                yield Checkbox("Cookie params", value=True, id="mark-cookie")

        if self._has_header:
            with Horizontal(classes="row"):
                yield Checkbox("Header params", value=True, id="mark-header")

        if self._has_json:
            with Horizontal(classes="row"):
                yield Checkbox("Body JSON — mark keys", value=True, id="mark-json-keys")
            with Horizontal(classes="row"):
                yield Checkbox("Body JSON — mark values", value=True, id="mark-json-vals")
        if self._has_xml:
            with Horizontal(classes="row"):
                yield Checkbox("Body XML — mark tags", value=True, id="mark-xml-tags")
            with Horizontal(classes="row"):
                yield Checkbox("Body XML — mark content", value=True, id="mark-xml-content")

        with Horizontal(id="buttons"):
            yield ToolbarButton("✔ Mark selected", "btn-mark")
            yield ToolbarButton("✕ Cancel", "btn-cancel")

    @on(ToolbarButton.Pressed, "#btn-mark")
    def _btn_mark(self, _: ToolbarButton.Pressed) -> None:
        result = {}
        result["query"] = self._try_bool("mark-query")
        result["body_form"] = self._try_bool("mark-body-form")
        result["cookie"] = self._try_bool("mark-cookie")
        result["header"] = self._try_bool("mark-header")
        result["json_keys"] = self._try_bool("mark-json-keys")
        result["json_vals"] = self._try_bool("mark-json-vals")
        result["xml_tags"] = self._try_bool("mark-xml-tags")
        result["xml_content"] = self._try_bool("mark-xml-content")
        self.dismiss(result)

    @on(ToolbarButton.Pressed, "#btn-cancel")
    def _btn_cancel(self, _: ToolbarButton.Pressed) -> None:
        self.dismiss(None)

    def _try_bool(self, widget_id: str) -> bool:
        try:
            return bool(self.query_one(f"#{widget_id}", Checkbox).value)
        except Exception:
            return False
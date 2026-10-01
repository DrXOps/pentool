"""Intruder Auto-Mark dialog — choose which parts to mark with §§.

Mirrors the style and layout of ChecksDialog (ModalScreen + Grid + border).
Returns a dict[str, bool] or None on cancel.
"""

from __future__ import annotations

from pathlib import Path

from textual import on
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Grid, Vertical
from textual.screen import ModalScreen
from textual.widgets import Static

from pentool.tui.widgets.nice_checkbox import NiceCheckbox as Checkbox
from pentool.tui.widgets.toolbar_button import ToolbarButton


_CSS = (Path(__file__).parent / "intruder_auto_mark.tcss").read_text(encoding="utf-8")


class IntruderAutoMarkDialog(ModalScreen[dict | None]):
    """Modal dialog for choosing what to auto-mark with §§ markers.

    Returns a dict with boolean keys (only the keys that were offered), or None.
    """

    DEFAULT_CSS = _CSS

    BINDINGS = [
        Binding("escape", "dismiss_dialog", "Close"),
    ]

    def __init__(
        self,
        has_json: bool = False,
        has_xml: bool = False,
        has_urlencoded: bool = True,
        has_query: bool = True,
        has_cookie: bool = True,
        has_header: bool = True,
    ) -> None:
        super().__init__()
        self._has_json = has_json
        self._has_xml = has_xml
        self._has_urlencoded = has_urlencoded
        self._has_query = has_query
        self._has_cookie = has_cookie
        self._has_header = has_header

    def compose(self) -> ComposeResult:
        # All available options — used to know which checkboxes exist
        all_options: list[tuple[str, str]] = []
        if self._has_query:
            all_options.append(("query", "URL query params"))
        if self._has_urlencoded:
            all_options.append(("body_form", "Body (form-urlencoded)"))
        if self._has_json:
            all_options.append(("json_keys", "JSON — mark keys"))
            all_options.append(("json_vals", "JSON — mark values"))
        if self._has_xml:
            all_options.append(("xml_tags", "XML — mark tags"))
            all_options.append(("xml_content", "XML — mark content"))
        if self._has_cookie:
            all_options.append(("cookie", "Cookie params"))
        if self._has_header:
            all_options.append(("header", "Header params"))

        with Vertical(id="dialog"):
            yield Static("Auto-Mark Parameters", id="title")
            yield Static("Choose which parts to mark with §§ markers.", id="hint")
            with Grid(id="checks-grid"):
                for key, label in all_options:
                    yield Checkbox(label, value=True, id=f"mark-{key}", classes="chk")
            with Vertical(id="buttons-row"):
                yield ToolbarButton("Select All",    "btn-select-all")
                yield ToolbarButton("Select None",   "btn-select-none")
                yield ToolbarButton("✔ Mark selected", "btn-mark")
                yield ToolbarButton("✕ Cancel",      "btn-cancel")

    @on(Checkbox.Changed)
    def on_checkbox_changed(self, event: Checkbox.Changed) -> None:
        """Immediately sync any checkbox toggle — no explicit action needed."""

    @on(ToolbarButton.Pressed, "#btn-select-all")
    def on_select_all(self, _: ToolbarButton.Pressed) -> None:
        self._set_all(True)

    @on(ToolbarButton.Pressed, "#btn-select-none")
    def on_select_none(self, _: ToolbarButton.Pressed) -> None:
        self._set_all(False)

    @on(ToolbarButton.Pressed, "#btn-mark")
    def on_mark(self, _: ToolbarButton.Pressed) -> None:
        result: dict[str, bool] = {}
        for key in ("query", "body_form", "cookie", "header",
                     "json_keys", "json_vals", "xml_tags", "xml_content"):
            v = self._try_bool(f"mark-{key}")
            # Only include keys that are present as checkboxes
            if f"mark-{key}" in {w.id for w in self.query(Checkbox)}:
                result[key] = v
        self.dismiss(result)

    @on(ToolbarButton.Pressed, "#btn-cancel")
    def on_cancel(self, _: ToolbarButton.Pressed) -> None:
        self.dismiss(None)

    def _set_all(self, value: bool) -> None:
        for checkbox in self.query(Checkbox):
            if checkbox.id and checkbox.id.startswith("mark-"):
                checkbox.value = value

    def _try_bool(self, widget_id: str) -> bool:
        try:
            return bool(self.query_one(f"#{widget_id}", Checkbox).value)
        except Exception:
            return False

    def action_dismiss_dialog(self) -> None:
        self.dismiss(None)
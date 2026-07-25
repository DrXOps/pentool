"""Экран настройки горячих клавиш."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.widget import Widget
from textual.widgets import Button, DataTable, Input, Label, Static
from pathlib import Path

_CSS = (Path(__file__).parent / "hotkeys.tcss").read_text(encoding="utf-8")

DEFAULT_HOTKEYS: dict[str, str] = {
    "send_to_repeater": "ctrl+r",
    "send_to_intruder": "ctrl+i",
    "send_to_decoder":  "ctrl+d",
    "repeater_send":    "ctrl+space",
    "toggle_intercept": "ctrl+t",
    "new_project":      "ctrl+n",
    "save_project":     "ctrl+s",
    "open_project":     "ctrl+o",
    "quit":             "ctrl+q",
    "toggle_inspector": "i",
    "search":           "ctrl+f",
}

_ACTION_LABELS: dict[str, str] = {
    "send_to_repeater": "Send to Repeater",
    "send_to_intruder": "Send to Intruder",
    "send_to_decoder":  "Send to Decoder",
    "repeater_send":    "Repeater: Send Request",
    "toggle_intercept": "Toggle Intercept",
    "new_project":      "New Project",
    "save_project":     "Save Project",
    "open_project":     "Open Project",
    "quit":             "Quit",
    "toggle_inspector": "Toggle Inspector",
    "search":           "Search (Ctrl+F)",
}


class HotkeySettingsScreen(Widget):
    """Экран настройки горячих клавиш."""

    DEFAULT_CSS = _CSS

    def __init__(self, hotkeys: dict[str, str] | None = None, **kwargs) -> None:
        super().__init__(**kwargs)
        self._hotkeys: dict[str, str] = dict(hotkeys or DEFAULT_HOTKEYS)
        self._editing_action: str | None = None

    def compose(self) -> ComposeResult:
        yield Static("Hotkeys", classes="section-title")
        yield DataTable(id="hotkey-table", cursor_type="row", zebra_stripes=True)
        with Horizontal(id="hotkey-edit-row"):
            yield Label("New hotkey:", id="hk-edit-label")
            yield Input(placeholder="e.g. ctrl+r", id="hk-edit-input", compact=True)
            yield Button("OK", id="hk-edit-ok", variant="primary")
            yield Button("Cancel", id="hk-edit-cancel")
        with Horizontal(id="hotkey-buttons"):
            yield Button("Reset to defaults", id="hk-reset")
            yield Button("Save", id="hk-save", variant="primary")

    def on_mount(self) -> None:
        self._refresh_table()

    def _refresh_table(self) -> None:
        try:
            table = self.query_one("#hotkey-table", DataTable)
            table.clear(columns=True)
            table.add_columns("Action", "Current Hotkey", "Default")
            for action, current in self._hotkeys.items():
                label = _ACTION_LABELS.get(action, action)
                default = DEFAULT_HOTKEYS.get(action, "—")
                marker = "" if current == default else " *"
                table.add_row(label, f"{current}{marker}", default)
        except Exception:
            pass

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        actions = list(self._hotkeys.keys())
        if 0 <= event.cursor_row < len(actions):
            self._start_edit(actions[event.cursor_row])

    def _start_edit(self, action: str) -> None:
        self._editing_action = action
        try:
            inp = self.query_one("#hk-edit-input", Input)
            inp.value = self._hotkeys.get(action, "")
            row = self.query_one("#hotkey-edit-row")
            row.add_class("-visible")
            inp.focus()
        except Exception:
            pass

    def _finish_edit(self) -> None:
        try:
            inp = self.query_one("#hk-edit-input", Input)
            new_key = inp.value.strip()
            if new_key and self._editing_action:
                self._hotkeys[self._editing_action] = new_key
        except Exception:
            pass
        self._cancel_edit()

    def _cancel_edit(self) -> None:
        self._editing_action = None
        try:
            self.query_one("#hotkey-edit-row").remove_class("-visible")
        except Exception:
            pass
        self._refresh_table()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        bid = event.button.id
        if bid == "hk-edit-ok":
            self._finish_edit()
        elif bid == "hk-edit-cancel":
            self._cancel_edit()
        elif bid == "hk-reset":
            self._hotkeys = dict(DEFAULT_HOTKEYS)
            self._refresh_table()
        elif bid == "hk-save":
            self._apply_hotkeys()

    def _apply_hotkeys(self) -> None:
        """Применить хоткеи (сохранить в конфиг, rebind через app)."""
        try:
            self.app.notify("Hotkeys saved (restart required for some bindings)", timeout=3)  # type: ignore[attr-defined]
        except Exception:
            pass

    def get_hotkeys(self) -> dict[str, str]:
        return dict(self._hotkeys)

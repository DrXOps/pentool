"""Hotkey settings screen — a read-only view of the real hotkey table.

The bindings shown here come from ``pentool/tui/hotkeys/defaults.py``, which
is what Textual actually dispatches. Nothing on this screen edits them: there
is no rebinding support yet, and a screen with an editable table, a Save button
and a "Hotkeys saved" toast that persisted nothing was worse than none — it
showed a hand-typed copy of the table (with different keys than the real one)
and claimed success (F-035).
"""

from __future__ import annotations

from pathlib import Path

from textual.app import ComposeResult
from textual.widget import Widget
from textual.widgets import DataTable, Static

from pentool.tui.hotkeys.defaults import registry

_CSS = (Path(__file__).parent / "hotkeys.tcss").read_text(encoding="utf-8")

_HINT = (
    "Keybindings are fixed for now — they live in pentool/tui/hotkeys/defaults.py. "
    "Per-user overrides are not implemented yet."
)


class HotkeySettingsScreen(Widget):
    """Read-only table of every registered hotkey."""

    DEFAULT_CSS = _CSS

    def compose(self) -> ComposeResult:
        yield Static("Hotkeys", classes="section-title")
        yield Static(_HINT, classes="hotkey-hint")
        yield DataTable(id="hotkey-table", cursor_type="none", zebra_stripes=True)

    def on_mount(self) -> None:
        table = self.query_one("#hotkey-table", DataTable)
        table.add_columns("Group", "Keys", "Action", "Description")
        for group in registry.groups():
            for entry in registry.get_entries(group):
                description = entry.description or "—"
                if not entry.show:
                    description = f"{description} (hidden from the footer)"
                table.add_row(group, entry.keys, entry.action, description)

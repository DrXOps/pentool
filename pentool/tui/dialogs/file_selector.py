"""FileSelectorDialog — file/directory chooser dialog with tree navigation."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from pathlib import Path

_CSS = (Path(__file__).parent / "file_selector.tcss").read_text(encoding="utf-8")

import time

from textual import on
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import DataTable, Input, Label, Static

from pentool.tui.widgets.toolbar_button import ToolbarButton


class FileSelectorMode(Enum):
    OPEN = "open"           # select existing file
    SAVE = "save"           # enter new file name
    DIRECTORY = "dir"       # select directory

class FileSelectorDialog(ModalScreen):
    """Tree-based filesystem navigation.

    Returns (via dismiss):
        Absolute path to the selected file/directory, or None if cancelled.
    """

    DEFAULT_CSS = _CSS

    BINDINGS = [
        Binding("escape", "cancel", "Cancel"),
        Binding("enter", "confirm", "OK"),
    ]

    def __init__(
        self,
        mode: FileSelectorMode = FileSelectorMode.OPEN,
        filter_ext: list[str | None] = None,
        title: str = "Select file",
        start_dir: str | None = None,
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        self._mode = mode
        self._filter_ext = filter_ext or []
        self._title = title
        self._current_dir = Path(start_dir) if start_dir else Path.cwd()
        self._entries: list[tuple[str, str, str]] = []  # (name, size, modified)
        self._is_dir_entry: list[bool] = []
        self._sort_col = "name"
        self._sort_reverse = False
        self._selected_path: str | None = None
        self._last_click_time: float = 0.0
        self._last_click_row: int = -1

    def compose(self) -> ComposeResult:
        with Vertical(id="dialog"):
            yield Static(f" {self._title}", id="title-bar")
            with Horizontal(id="path-bar"):
                yield Static(str(self._current_dir), id="path-label")
                yield ToolbarButton("↑ Up", "btn-up")
            yield DataTable(id="file-table", cursor_type="row", zebra_stripes=True)
            with Horizontal(id="bottom-bar"):
                yield Label("File: ")
                yield Input(id="filename-input", placeholder="filename...", compact=True)
            with Horizontal(id="buttons"):
                yield ToolbarButton("OK", "btn-ok")
                yield ToolbarButton("Cancel", "btn-cancel")

    def on_mount(self) -> None:
        table = self.query_one("#file-table", DataTable)
        table.add_columns("Name", "Size", "Modified")
        self._load_directory()

    def _load_directory(self) -> None:
        table = self.query_one("#file-table", DataTable)
        table.clear()
        self._entries = []
        self._is_dir_entry = []

        # Update path label
        try:
            self.query_one("#path-label", Static).update(str(self._current_dir))
        except Exception:
            pass

        entries = []
        try:
            for entry in sorted(self._current_dir.iterdir()):
                try:
                    stat = entry.stat()
                    is_dir = entry.is_dir()
                    size = "-" if is_dir else _format_size(stat.st_size)
                    modified = datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M")
                    # Filter by extension
                    if not is_dir and self._filter_ext:
                        if not any(entry.name.endswith(ext.lstrip("*")) for ext in self._filter_ext):
                            continue
                    prefix = "📁 " if is_dir else "📄 "
                    entries.append((prefix + entry.name, size, modified, is_dir, entry.name))
                except (PermissionError, OSError):
                    continue
        except (PermissionError, OSError):
            pass

        # Sort: directories first
        dirs = [(n, s, m, d, raw) for n, s, m, d, raw in entries if d]
        files = [(n, s, m, d, raw) for n, s, m, d, raw in entries if not d]

        for row_list in (dirs, files):
            for name, size, modified, is_dir, raw_name in row_list:
                table.add_row(name, size, modified)
                self._entries.append((name, size, modified))
                self._is_dir_entry.append(is_dir)

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        """Click — update filename field; double-click — enter folder or select file."""
        row_idx = event.cursor_row
        if 0 <= row_idx < len(self._is_dir_entry):
            entry_name = self._entries[row_idx][0].split(" ", 1)[-1]  # strip emoji
            is_dir = self._is_dir_entry[row_idx]
            entry_path = self._current_dir / entry_name
            self._selected_path = str(entry_path)
            if not is_dir:
                try:
                    self.query_one("#filename-input", Input).value = entry_name
                except Exception:
                    pass

            # Double-click: same row, interval < 500 ms
            now = time.monotonic()
            if row_idx == self._last_click_row and (now - self._last_click_time) < 0.5:
                if is_dir:
                    self._navigate_to(entry_path)
                else:
                    self.action_confirm()
                self._last_click_row = -1
                self._last_click_time = 0.0
            else:
                self._last_click_row = row_idx
                self._last_click_time = now

    def on_data_table_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        pass

    def on_data_table_header_selected(self, event: DataTable.HeaderSelected) -> None:
        """Sort by column header."""
        _col_names = ["Name", "Size", "Modified"]
        col = _col_names[event.column_index] if event.column_index < len(_col_names) else ""
        if not col:
            return
        self._sort_reverse = (self._sort_col == col) and not self._sort_reverse
        self._sort_col = col
        event.data_table.sort(col, reverse=self._sort_reverse)

    def on_key(self, event) -> None:
        if event.key == "enter":
            # If a directory is selected — enter it
            try:
                table = self.query_one("#file-table", DataTable)
                row_idx = table.cursor_row
                if 0 <= row_idx < len(self._is_dir_entry):
                    entry_name = self._entries[row_idx][0].split(" ", 1)[-1]
                    is_dir = self._is_dir_entry[row_idx]
                    if is_dir:
                        self._navigate_to(self._current_dir / entry_name)
                        event.prevent_default()
                        return
            except Exception:
                pass
            self.action_confirm()
            event.prevent_default()

    @on(ToolbarButton.Pressed, "#btn-ok")
    def on_btn_ok(self, _: ToolbarButton.Pressed) -> None:
        self.action_confirm()

    @on(ToolbarButton.Pressed, "#btn-cancel")
    def on_btn_cancel(self, _: ToolbarButton.Pressed) -> None:
        self.action_cancel()

    @on(ToolbarButton.Pressed, "#btn-up")
    def on_btn_up(self, _: ToolbarButton.Pressed) -> None:
        self._navigate_to(self._current_dir.parent)

    def _navigate_to(self, path: Path) -> None:
        if path.is_dir():
            self._current_dir = path
            self._load_directory()

    def action_confirm(self) -> None:
        # Priority: manual input > selected file
        try:
            filename = self.query_one("#filename-input", Input).value.strip()
            if filename:
                path = self._current_dir / filename
                self.dismiss(str(path))
                return
        except Exception:
            pass

        if self._selected_path:
            self.dismiss(self._selected_path)
        else:
            self.dismiss(None)

    def action_cancel(self) -> None:
        self.dismiss(None)

def _format_size(size_bytes: int) -> str:
    """Format file size into human-readable form."""
    if size_bytes < 1024:
        return f"{size_bytes}B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes // 1024}K"
    elif size_bytes < 1024 * 1024 * 1024:
        return f"{size_bytes // (1024 * 1024)}M"
    else:
        return f"{size_bytes // (1024 * 1024 * 1024)}G"

"""PayloadDropZone — drop zone for payload files."""

from __future__ import annotations

from pathlib import Path

from textual.message import Message
from textual.widget import Widget

_CSS = (Path(__file__).parent / "payload_drop_zone.tcss").read_text(encoding="utf-8")


class PayloadDropZone(Widget):
    """Visual drag & drop zone for payload files.

    If native DragDrop (textual-filedrop) is unavailable — shows a hint.
    Integrates with the "Load from file" button.

    Messages:
        PayloadDropZone.PayloadsLoaded — payloads loaded from file.
    """

    DEFAULT_CSS = _CSS

    class PayloadsLoaded(Message):
        """Payloads successfully loaded from file."""
        def __init__(self, payloads: list[str], source_path: str = "") -> None:
            super().__init__()
            self.payloads = payloads
            self.source_path = source_path

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.update_text()

    def update_text(self, count: int = 0) -> None:
        pass  # count argument kept for backward API compatibility

    def render(self) -> str:
        return "  Drop .txt / .yaml payload file here\n  (or use 'Load from file' button)"

    def load_from_path(self, path: str) -> None:
        from pentool.api.intruder_api import load_payloads_from_file
        payloads = load_payloads_from_file(path)
        if payloads:
            self.post_message(self.PayloadsLoaded(payloads, source_path=path))

    def on_click(self) -> None:
        """Click on the zone — open FileSelectorDialog as an alternative to DragDrop."""
        from pentool.tui.dialogs.file_selector import FileSelectorDialog, FileSelectorMode

        def _on_selected(path: str | None) -> None:
            if path:
                self.load_from_path(path)

        try:
            self.app.push_screen(
                FileSelectorDialog(
                    mode=FileSelectorMode.OPEN,
                    filter_ext=["*.txt", "*.yaml", "*.yml"],
                    title="Select payload file",
                ),
                _on_selected,
            )
        except Exception:
            pass

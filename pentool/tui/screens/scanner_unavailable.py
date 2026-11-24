"""Fallback shown in place of the Scanner module when the PRO package isn't installed.

Scanner (pentool/modules/scanner/, pentool/api/scanner_api.py,
pentool/tui/screens/scanner/) is a PRO-only module distributed separately —
see pentool.core.license.download_pro_package. A bare `pip install pentool`
does not include it, so pentool.tui.screens imports this instead and the
rest of the TUI (all FREE modules) still starts normally.
"""

from __future__ import annotations

from pathlib import Path

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widget import Widget
from textual.widgets import Static


class ScannerUnavailableScreen(Widget):
    """Drop-in replacement for ScannerScreen when the PRO package is missing."""

    DEFAULT_CSS = (Path(__file__).parent / "scanner_unavailable.tcss").read_text(encoding="utf-8")

    def __init__(self, **kwargs) -> None:
        # ScannerScreen.__init__ accepts arbitrary **kwargs (e.g. id=...);
        # match that signature so app.py's ScannerScreen(id="screen-scanner")
        # works unchanged regardless of which class this name resolves to.
        super().__init__(**kwargs)

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Static("🔒 Scanner is a PRO feature", markup=False)
            yield Static("")
            yield Static("Have a key? Open Settings → License, paste it and press Activate.")
            yield Static("")
            yield Static("No key yet? Ask support@pentool.pro for a 14-day trial key.")
            yield Static("")
            yield Static("The rest of Pentool keeps working without PRO.")
